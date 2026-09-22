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
from app.core.config import settings

logger = logging.getLogger(__name__)

class OpenAIProvider(BaseLLMClient):
    """OpenAI API provider utilizing structured JSON completions via HTTPX."""

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        self.api_key = api_key
        self.model = model
        self.endpoint = "https://api.openai.com/v1/chat/completions"

    async def _call_openai(self, messages: List[Dict[str, str]], response_format: Optional[Dict[str, str]] = None) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1
        }
        if response_format:
            payload["response_format"] = response_format

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(self.endpoint, headers=headers, json=payload)
            if resp.status_code in (401, 403):
                raise ProviderError(ProviderState.AUTHENTICATION_FAILED, "PROVIDER_AUTH_FAILED", "OpenAI authentication failed.")
            if resp.status_code == 429:
                raise ProviderError(ProviderState.RATE_LIMITED, "PROVIDER_RATE_LIMITED", "OpenAI rate limit reached.")
            if resp.status_code != 200:
                raise ProviderError(ProviderState.UNAVAILABLE, "PROVIDER_UNAVAILABLE", f"OpenAI returned HTTP {resp.status_code}.")
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    async def generate_investigation_plan(
        self,
        objective: str,
        catalog_summary: Dict[str, Any]
    ) -> PlanOutput:
        prompt = f"""You are OmniOps Lead Autonomous Business Intelligence Agent.
Objective: {objective}

Available Workspace Data Catalog:
{json.dumps(catalog_summary, indent=2)}

Create a structured investigation plan with 2 to 4 discrete, verifiable tasks to solve this objective.
Respond in valid JSON matching this schema:
{{
  "reasoning_summary": "High level strategy",
  "tasks": [
    {{
      "id": "TASK-1",
      "title": "Task title",
      "description": "Specific query or retrieval to perform",
      "target_modality": "tabular" | "document" | "audio" | "image" | "sandbox",
      "expected_output": "What concrete evidence or calculation will be produced"
    }}
  ]
}}"""
        messages = [
            {"role": "system", "content": "Plan only actions supported by the supplied data catalog."},
            {"role": "user", "content": prompt}
        ]
        raw_json = await self._call_openai(messages, response_format={"type": "json_object"})
        data = json.loads(raw_json)
        return PlanOutput(
            reasoning_summary=data.get("reasoning_summary", "Plan formulated by OpenAI model."),
            tasks=[PlannedTask(**t) for t in data.get("tasks", [])]
        )

    async def decide_next_action(
        self,
        objective: str,
        current_task: PlannedTask,
        prior_observations: List[Dict[str, Any]],
        available_tools: List[Dict[str, Any]]
    ) -> ToolDecision:
        prompt = f"""Objective: {objective}
Current Sub-Task: {current_task.id} - {current_task.title}
Task Description: {current_task.description}
Modality: {current_task.target_modality}

Prior Step Observations:
{json.dumps(prior_observations[-3:], indent=2, default=str)}

Available Tools:
{json.dumps(available_tools, indent=2)}

Select the best tool and specify its arguments.
For tabular queries: use 'tabular_sql_query' with valid SQL.
For documents: use 'hybrid_document_search' with 'query' and 'top_k'.
For calculations: use 'sandboxed_python_exec' with 'code' and 'input_data'.

Respond in valid JSON matching this schema:
{{
  "tool_name": "tool_name",
  "arguments": {{ "arg1": "val1" }},
  "user_activity_summary": "User-facing active status message in natural language",
  "thought_process": "Internal chain of thought reasoning"
}}"""
        messages = [
            {"role": "system", "content": "You are an autonomous analytical tool executor. Choose tools carefully and avoid syntax errors."},
            {"role": "user", "content": prompt}
        ]
        raw_json = await self._call_openai(messages, response_format={"type": "json_object"})
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
        prompt = f"""Objective: {objective}

Discovered Evidence Snippets:
{json.dumps(evidence_items, indent=2, default=str)}

Computed Calculations:
{json.dumps(calculations, indent=2, default=str)}

Step Observations:
{json.dumps(observations, indent=2, default=str)}

Perform epistemic verification and synthesize the final executive report.
Every empirical fact must cite an exact evidence item ID.
Every calculation must reference its calculation formula or computed output.
Respond in valid JSON matching this schema:
{{
  "executive_summary": "Crisp executive briefing answering the core objective.",
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
    {"inference_id": "INF-001", "statement": "Derived statement", "supporting_claim_ids": ["CLM-001"]}
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
        messages = [
            {"role": "system", "content": "Return evidence-linked proposals; the application validates every reference."},
            {"role": "user", "content": prompt}
        ]
        raw_json = await self._call_openai(messages, response_format={"type": "json_object"})
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
