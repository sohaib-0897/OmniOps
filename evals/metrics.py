from typing import List, Dict, Any, Optional
from pydantic import BaseModel

class BenchmarkScore(BaseModel):
    scenario_id: str
    scenario_name: str
    passed: bool
    factual_precision: Optional[float] = None
    citation_precision: Optional[float] = None
    hallucination_rate: Optional[float] = None
    latency_ms: int
    notes: str

class OverallBenchmarkReport(BaseModel):
    total_scenarios: int
    passed_scenarios: int
    mean_factual_precision: Optional[float] = None
    mean_citation_precision: Optional[float] = None
    mean_hallucination_rate: Optional[float] = None
    mean_latency_ms: float
    scores: List[BenchmarkScore]

def calculate_precision(true_positives: int, false_positives: int) -> float:
    total = true_positives + false_positives
    if total == 0:
        return 1.0
    return round(true_positives / total, 4)
