import json
import logging
from typing import Dict, Any, List, Optional
import httpx
from app.llm.base import (
    BaseLLMClient,
    PlanOutput,
    PlannedTask,
    ToolDecision,
    SynthesisReport,
    EpistemicClaim,
    RecommendationItem, InferenceItem, ProviderError, ProviderState
)

logger = logging.getLogger(__name__)

class GeminiProvider(BaseLLMClient):
    """Google Gemini REST API provider using structured JSON outputs."""

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        self.api_key = api_key
        self.model = model
        self.endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    async def _call_gemini(self, system_instruction: str, prompt: str) -> str:
        headers = {"Content-Type": "application/json"}
        payload = {
            "system_instruction": {
                "parts": [{"text": system_instruction}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.1
            }
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(self.endpoint, headers=headers, json=payload)
            if resp.status_code in (401, 403):
                raise ProviderError(ProviderState.AUTHENTICATION_FAILED, "PROVIDER_AUTHENTICATION_FAILED", "Gemini authentication failed.")
            if resp.status_code == 429:
                raise ProviderError(ProviderState.RATE_LIMITED, "PROVIDER_RATE_LIMITED", "Gemini rate limit reached.")
            if resp.status_code != 200:
                raise ProviderError(ProviderState.UNAVAILABLE, "PROVIDER_UNAVAILABLE", f"Gemini returned HTTP {resp.status_code}.")
            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates or "content" not in candidates[0]:
                raise ValueError(f"Gemini returned empty candidate response: {data}")
            return candidates[0]["content"]["parts"][0]["text"]

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
