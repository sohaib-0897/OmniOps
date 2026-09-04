import re
from typing import Dict, Any, List

from app.llm.base import (
    BaseLLMClient, PlanOutput, PlannedTask, ToolDecision, SynthesisReport,
    EpistemicClaim, CapabilityLimitError,
)


class AnalyticalProvider(BaseLLMClient):
    """Deterministic structured-data provider; never performs semantic reasoning."""

    async def generate_investigation_plan(self, objective: str, catalog_summary: Dict[str, Any]) -> PlanOutput:
        tables = catalog_summary.get("tables", [])
        if not tables:
            raise CapabilityLimitError(
                "The deterministic engine requires tabular data; semantic analysis needs an LLM provider."
            )
        tasks = []
        for index, table in enumerate(tables, 1):
            name = table.get("name")
            if not name or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                continue
            tasks.append(PlannedTask(
                id=f"TASK-{index}", title=f"Profile tabular dataset: {name}",
                description="Compute a deterministic row count from the registered table.",
                target_modality="tabular", expected_output=f"A reproducible row count for '{name}'.",
            ))
        if not tasks:
            raise CapabilityLimitError("No safely addressable tabular datasets are available.")
        return PlanOutput(
            reasoning_summary="Deterministic table profiling only; no semantic conclusions will be generated.",
            tasks=tasks,
        )

    async def decide_next_action(
        self, objective: str, current_task: PlannedTask,
        prior_observations: List[Dict[str, Any]], available_tools: List[Dict[str, Any]],
    ) -> ToolDecision:
        match = re.search(r"Profile tabular dataset:\s*([A-Za-z_][A-Za-z0-9_]*)", current_task.title)
        if current_task.target_modality != "tabular" or not match:
            raise CapabilityLimitError("The deterministic engine cannot perform semantic tool selection.")
        table_name = match.group(1)
        return ToolDecision(
            tool_name="tabular_sql_query",
            arguments={"sql_query": f'SELECT COUNT(*) AS row_count FROM "{table_name}"'},
            user_activity_summary=f"Computing a deterministic row count for '{table_name}'.",
        )

    async def verify_and_synthesize(
        self, objective: str, observations: List[Dict[str, Any]],
        evidence_items: List[Dict[str, Any]], calculations: List[Dict[str, Any]],
    ) -> SynthesisReport:
        if not calculations:
            raise CapabilityLimitError("No successful deterministic calculations are available to report.")
        claims, findings = [], []
        for index, calc in enumerate(calculations, 1):
            calc_id = str(calc.get("id", ""))
            if not calc_id or "computed_output" not in calc:
                continue
            claim_id = f"CLM-{index:03d}"
            output = calc["computed_output"]
            claims.append(EpistemicClaim(
                claim_id=claim_id,
                statement=f"Deterministic calculation {calc_id} returned: {output!r}",
                epistemic_type="calculation", confidence_score=None,
                calculation_ids=[calc_id], calculation_summary=str(calc.get("formula_or_code", "")),
            ))
            findings.append({"title": "Deterministic calculation", "detail": str(output), "claim_id": claim_id})
        if not claims:
            raise CapabilityLimitError("Calculation records were incomplete; no claims were produced.")
        return SynthesisReport(
            executive_summary="Only reproducible structured-data calculations are reported. Semantic interpretation was not performed.",
            key_findings=findings, claims=claims, recommendations=[],
            missing_data_warnings=["LLM_PROVIDER_REQUIRED for semantic analysis, inference, or recommendations."],
        )
