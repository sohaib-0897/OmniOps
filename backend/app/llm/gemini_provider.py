import asyncio
import json
from typing import Any, Dict, List, Optional

import httpx

from app.llm.base import (
    BaseLLMClient,
    EpistemicClaim,
    InferenceItem,
    PlanOutput,
    PlannedTask,
    ProviderError,
    ProviderState,
    RecommendationItem,
    SynthesisReport,
    ToolDecision,
)


class GeminiProvider(BaseLLMClient):
    """Google Gemini REST API provider using structured JSON outputs."""

    MAX_ATTEMPTS = 5
    REQUEST_TIMEOUT_SECONDS = 15.0
    RETRY_BUDGET_SECONDS = 90.0
    MAX_RETRY_AFTER_SECONDS = 30.0

    def __init__(self, api_key: str, model: str = "gemini-3.8-flash"):
        self.api_key = api_key
        self.model = model
        self.endpoint = "https://generativelanguage.googleapis.com/v1beta/interactions"

    @staticmethod
    def _error_code(response: httpx.Response) -> Optional[str]:
        try:
            body = response.json()
        except (TypeError, ValueError):
            return None
        error = body.get("error") if isinstance(body, dict) else None
        code = error.get("code") if isinstance(error, dict) else None
        return code if isinstance(code, str) else None

    @classmethod
    def _retry_delay(cls, response: Optional[httpx.Response], attempt: int) -> float:
        if response is not None:
            retry_after = response.headers.get("retry-after")
            if retry_after:
                try:
                    return min(max(float(retry_after), 1.0), cls.MAX_RETRY_AFTER_SECONDS)
                except ValueError:
                    pass
        return float(2 ** attempt)

    async def _call_gemini(self, system_instruction: str, prompt: str) -> str:
        headers = {"Content-Type": "application/json", "x-goog-api-key": self.api_key}
        payload = {
            "model": self.model,
            "system_instruction": system_instruction,
            "input": prompt,
            "response_format": {"type": "text", "mime_type": "application/json"},
        }

        loop = asyncio.get_running_loop()
        retry_deadline = loop.time() + self.RETRY_BUDGET_SECONDS

        async def sleep_before_retry(response: Optional[httpx.Response], attempt: int) -> bool:
            # Reserve one full request timeout so this provider call remains
            # inside the durable worker's 120-second lease.
            remaining = retry_deadline - loop.time() - self.REQUEST_TIMEOUT_SECONDS
            if remaining <= 0:
                return False
            await asyncio.sleep(min(self._retry_delay(response, attempt), remaining))
            return True

        async with httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT_SECONDS, trust_env=False) as client:
            for attempt in range(self.MAX_ATTEMPTS):
                try:
                    resp = await client.post(self.endpoint, headers=headers, json=payload)
                except httpx.TimeoutException as exc:
                    if attempt == self.MAX_ATTEMPTS - 1 or not await sleep_before_retry(None, attempt):
                        raise ProviderError(
                            ProviderState.TIMEOUT,
                            "PROVIDER_TIMEOUT",
                            "Gemini timed out after bounded retries.",
                        ) from exc
                    continue
                except httpx.TransportError as exc:
                    if attempt == self.MAX_ATTEMPTS - 1 or not await sleep_before_retry(None, attempt):
                        raise ProviderError(
                            ProviderState.UNAVAILABLE,
                            "PROVIDER_UNAVAILABLE",
                            "Gemini transport remained unavailable after bounded retries.",
                        ) from exc
                    continue
                if resp.status_code in (401, 403):
                    raise ProviderError(ProviderState.AUTHENTICATION_FAILED, "PROVIDER_AUTH_FAILED", "Gemini authentication failed.")
                if resp.status_code == 429:
                    if self._error_code(resp) == "quota_exceeded":
                        raise ProviderError(
                            ProviderState.RATE_LIMITED,
                            "PROVIDER_QUOTA_EXCEEDED",
                            "Gemini project quota is exhausted.",
                        )
                    if attempt < self.MAX_ATTEMPTS - 1 and await sleep_before_retry(resp, attempt):
                        continue
                    raise ProviderError(ProviderState.RATE_LIMITED, "PROVIDER_RATE_LIMITED", "Gemini rate limit reached after bounded retries.")
                if resp.status_code == 408:
                    if attempt < self.MAX_ATTEMPTS - 1 and await sleep_before_retry(resp, attempt):
                        continue
                    raise ProviderError(ProviderState.TIMEOUT, "PROVIDER_TIMEOUT", "Gemini timed out after bounded retries.")
                if resp.status_code >= 500:
                    if attempt < self.MAX_ATTEMPTS - 1 and await sleep_before_retry(resp, attempt):
                        continue
                    raise ProviderError(ProviderState.UNAVAILABLE, "PROVIDER_UNAVAILABLE", f"Gemini returned HTTP {resp.status_code} after bounded retries.")
                if resp.status_code != 200:
                    raise ProviderError(ProviderState.UNAVAILABLE, "PROVIDER_UNAVAILABLE", f"Gemini returned HTTP {resp.status_code}.")
                try:
                    data = resp.json()
                except (TypeError, ValueError) as exc:
                    raise ProviderError(
                        ProviderState.MALFORMED_RESPONSE,
                        "PROVIDER_RESPONSE_INVALID",
                        "Gemini returned malformed interaction output.",
                    ) from exc
                if not isinstance(data, dict):
                    raise ProviderError(
                        ProviderState.MALFORMED_RESPONSE,
                        "PROVIDER_RESPONSE_INVALID",
                        "Gemini returned malformed interaction output.",
                    )
                return self._response_text(data)
        raise ProviderError(ProviderState.UNAVAILABLE, "PROVIDER_UNAVAILABLE", "Gemini retry loop ended without a response.")

    @staticmethod
    def _response_text(data: Dict[str, Any]) -> str:
        output_text = data.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()
        for step in data.get("steps", []):
            for content in step.get("content", []) if isinstance(step, dict) else []:
                if isinstance(content, dict) and isinstance(content.get("text"), str) and content["text"].strip():
                    return content["text"].strip()
        raise ProviderError(
            ProviderState.MALFORMED_RESPONSE,
            "PROVIDER_RESPONSE_INVALID",
            "Gemini returned empty interaction output.",
        )

    async def generate_investigation_plan(
        self,
        objective: str,
        catalog_summary: Dict[str, Any]
    ) -> PlanOutput:
        sys_inst = "Plan only actions supported by the supplied data catalog."
        prompt = f"""Objective: {objective}

Available Catalog:
{json.dumps(catalog_summary, indent=2)}

Generate a structured investigation DAG in JSON:
{{
  "reasoning_summary": "High level strategy",
  "tasks": [
    {{
      "id": "TASK-1",
      "title": "Task title",
      "description": "Specific query or action",
      "target_modality": "tabular" | "document" | "audio" | "image" | "sandbox",
      "expected_output": "Concrete output expected"
    }}
  ]
}}"""
        raw_json = await self._call_gemini(sys_inst, prompt)
        data = json.loads(raw_json)
        return PlanOutput(
            reasoning_summary=data.get("reasoning_summary", "Plan formulated by Gemini model."),
            tasks=[PlannedTask(**t) for t in data.get("tasks", [])]
        )

    async def decide_next_action(
        self,
        objective: str,
        current_task: PlannedTask,
        prior_observations: List[Dict[str, Any]],
        available_tools: List[Dict[str, Any]]
    ) -> ToolDecision:
        sys_inst = "You are an autonomous analytical tool executor. Choose tools carefully and avoid syntax errors."
        prompt = f"""Objective: {objective}
Current Sub-Task: {current_task.id} - {current_task.title}
Task Description: {current_task.description}
Modality: {current_task.target_modality}

Prior Observations:
{json.dumps(prior_observations[-3:], indent=2, default=str)}

Available Tools:
{json.dumps(available_tools, indent=2)}

Respond in valid JSON:
{{
  "tool_name": "tool_name",
  "arguments": {{ "arg1": "val1" }},
  "user_activity_summary": "Active progress summary for UI",
  "thought_process": "Chain of thought reasoning"
}}"""
        raw_json = await self._call_gemini(sys_inst, prompt)
        data = json.loads(raw_json)
        return ToolDecision(
            tool_name=data.get("tool_name", "hybrid_document_search"),
            arguments=data.get("arguments", {}),
            user_activity_summary=data.get("user_activity_summary", f"Executing {data.get('tool_name')} for {current_task.title}"),
            thought_process=data.get("thought_process")
        )

    async def verify_and_synthesize(
        self,
        objective: str,
        observations: List[Dict[str, Any]],
        evidence_items: List[Dict[str, Any]],
        calculations: List[Dict[str, Any]]
    ) -> SynthesisReport:
        sys_inst = "Return evidence-linked proposals; the application validates every reference."
        prompt = f"""Objective: {objective}

Discovered Evidence Snippets:
{json.dumps(evidence_items, indent=2, default=str)}

Computed Calculations:
{json.dumps(calculations, indent=2, default=str)}

Step Observations:
{json.dumps(observations, indent=2, default=str)}

Respond in valid JSON:
{{
  "executive_summary": "Executive briefing answering the objective.",
  "key_findings": [
    {{
      "title": "Finding title",
      "detail": "Finding detail",
      "claim_id": "CLM-001"
    }}
  ],
  "claims": [
    {{
      "claim_id": "CLM-001",
      "statement": "Empirical or calculated statement",
      "epistemic_type": "fact" | "calculation" | "inference" | "recommendation",
      "confidence_score": null,
      "citations": ["evidence_id_1"],
      "calculation_ids": ["calculation_id_1"],
      "calculation_summary": "Formula or code if calculation",
      "supporting_claims": []
    }}
  ],
  "inferences": [
    {{"inference_id": "INF-001", "statement": "Derived statement", "supporting_claim_ids": ["CLM-001"]}}
  ],
  "recommendations": [
    {{
      "recommendation_id": "REC-001",
      "title": "Strategy title",
      "action": "Concrete operational action",
      "priority": "high" | "medium" | "low",
      "supported_by_claims": ["CLM-001"]
    }}
  ],
  "missing_data_warnings": [],
  "contradictions": []
}}"""
        raw_json = await self._call_gemini(sys_inst, prompt)
        data = json.loads(raw_json)
        return SynthesisReport(
            executive_summary=data.get("executive_summary", "Synthesis completed."),
            key_findings=data.get("key_findings", []),
            claims=[EpistemicClaim(**c) for c in data.get("claims", [])],
            inferences=[InferenceItem(**i) for i in data.get("inferences", [])],
            recommendations=[RecommendationItem(**r) for r in data.get("recommendations", [])],
            missing_data_warnings=data.get("missing_data_warnings", []),
            contradictions=data.get("contradictions", [])
        )
