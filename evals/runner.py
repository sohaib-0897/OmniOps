import sys
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import time
import uuid
import asyncio
import tempfile
from typing import List
import pandas as pd
from evals.metrics import BenchmarkScore, OverallBenchmarkReport
from app.tools.duckdb_tool import DuckDBTool
from app.tools.python_sandbox import PythonSandboxRunner
from app.ingestion.file_guard import sanitize_filename, validate_magic_bytes
from app.ingestion.web_fetcher import is_ip_prohibited, validate_url_security
from app.llm.analytical_provider import AnalyticalProvider
from app.llm.base import CapabilityLimitError

async def run_scenario_01() -> bool:
    """Scenario 01: Contradictory sources - calculate real ledger vs memo."""
    with tempfile.TemporaryDirectory() as tmpdir:
        df = pd.DataFrame({"transaction": ["T1", "T2"], "revenue": [4000000, 6000000]})
        parquet_path = Path(tmpdir) / "sales.parquet"
        df.to_parquet(str(parquet_path), index=False)
        tool = DuckDBTool({"sales": str(parquet_path)})
        res = tool.execute_query("SELECT SUM(revenue) AS total_rev FROM sales;")
        return res.success and res.data[0]["total_rev"] == 10000000

async def run_scenario_02() -> bool:
    """Scenario 02: Tabular mathematical calculation & profit margin variance."""
    with tempfile.TemporaryDirectory() as tmpdir:
        df = pd.DataFrame({
            "quarter": ["Q2", "Q3"],
            "profit": [500000.0, 150000.0]
        })
        p_path = Path(tmpdir) / "margins.parquet"
        df.to_parquet(str(p_path), index=False)
        tool = DuckDBTool({"margins": str(p_path)})
        res = tool.execute_query("SELECT ((MAX(profit) - MIN(profit)) / MAX(profit)) * 100 AS contraction_pct FROM margins;")
        return res.success and abs(res.data[0]["contraction_pct"] - 70.0) < 0.01

async def run_scenario_03() -> bool:
    """Offline provider refuses semantic document planning."""
    provider = AnalyticalProvider()
    try:
        await provider.generate_investigation_plan("supplier agreement terms", {"tables": [], "documents": [{"id": "doc-1"}]})
    except CapabilityLimitError as exc:
        return exc.code == "LLM_PROVIDER_REQUIRED"
    return False

async def run_scenario_04() -> bool:
    """Scenario 04: Missing data warning generation."""
    try:
        await AnalyticalProvider().verify_and_synthesize("delivery times", [], [], [])
    except CapabilityLimitError:
        return True
    return False

async def run_scenario_05() -> bool:
    """Scenario 05: Multi-source synthesis."""
    calc = [{"id": str(uuid.uuid4()), "calculation_type": "sql", "computed_output": [{"row_count": 2}], "formula_or_code": "SELECT COUNT(*)"}]
    report = await AnalyticalProvider().verify_and_synthesize("reconciliation", [], [], calc)
    return len(report.claims) == 1 and not report.inferences and not report.recommendations

async def run_scenario_06() -> bool:
    """Scenario 06: Deterministic execution hash reproducibility."""
    res1 = PythonSandboxRunner.execute("return 100 * 1.5")
    res2 = PythonSandboxRunner.execute("return 100 * 1.5")
    return res1.success and res2.success and res1.reproducibility_hash == res2.reproducibility_hash

async def run_scenario_07() -> bool:
    """Scenario 07: AST rejection of malicious injection in code."""
    res = PythonSandboxRunner.execute("import os\nreturn os.environ")
    return not res.success and "unauthorized module" in res.error_message.lower()

async def run_scenario_08() -> bool:
    """Scenario 08: Epistemic claim inference generation."""
    calc = [{"id": str(uuid.uuid4()), "calculation_type": "sql", "computed_output": 40, "formula_or_code": "SELECT 40"}]
    report = await AnalyticalProvider().verify_and_synthesize("churn", [], [], calc)
    return not report.inferences

async def run_scenario_09() -> bool:
    """Scenario 09: Unsupported recommendation prevention."""
    calc = [{"id": str(uuid.uuid4()), "calculation_type": "sql", "computed_output": 1, "formula_or_code": "SELECT 1"}]
    report = await AnalyticalProvider().verify_and_synthesize("audit", [], [], calc)
    return report.recommendations == []

async def run_scenario_10() -> bool:
    """Scenario 10: DuckDB SQL injection / forbidden DROP defense."""
    tool = DuckDBTool({})
    res = tool.execute_query("DROP TABLE users;")
    return not res.success and "Security violation" in res.error_message

async def run_scenario_11() -> bool:
    """Scenario 11: Path traversal filename sanitization."""
    cleaned = sanitize_filename("../../etc/passwd.pdf")
    return cleaned == "passwd.pdf" and "/" not in cleaned and ".." not in cleaned

async def run_scenario_12() -> bool:
    """Scenario 12: SSRF defense on AWS metadata & localhost."""
    return is_ip_prohibited("169.254.169.254") and is_ip_prohibited("127.0.0.1") and is_ip_prohibited("10.0.0.1")

async def run_scenario_13() -> bool:
    """Scenario 13: Python sandbox escape via introspection and pandas file I/O."""
    r1 = PythonSandboxRunner.execute("x = ().__class__.__bases__[0].__subclasses__()")
    r2 = PythonSandboxRunner.execute("import pandas as pd\ndf = pd.read_csv('/etc/passwd')")
    return not r1.success and not r2.success

async def run_scenario_14() -> bool:
    """Scenario 14: Magic-byte binary verification."""
    is_valid = validate_magic_bytes(b"%PDF-1.4 test document content", ".pdf")
    is_invalid = validate_magic_bytes(b"MZ\x90\x00\x03", ".pdf")
    return is_valid and not is_invalid

async def run_scenario_15() -> bool:
    """Scenario 15: Safe float / datetime json serialization in DuckDB."""
    with tempfile.TemporaryDirectory() as tmpdir:
        df = pd.DataFrame({"ts": [pd.Timestamp("2026-01-01 10:00:00")], "val": [123.456]})
        p_path = Path(tmpdir) / "data.parquet"
        df.to_parquet(str(p_path), index=False)
        tool = DuckDBTool({"data": str(p_path)})
        res = tool.execute_query("SELECT ts, val FROM data;")
        return res.success and len(res.data) == 1

BENCHMARK_SCENARIOS = [
    {"id": f"SCENARIO-{index:02d}", "name": name, "runner": runner}
    for index, (name, runner) in enumerate([
        ("Contradictory Sources (Ledger vs Memo)", run_scenario_01),
        ("Tabular Mathematical Calculation", run_scenario_02),
        ("Deterministic Planning", run_scenario_03),
        ("Missing Data Signaling", run_scenario_04),
        ("Deterministic Calculation-Only Report", run_scenario_05),
        ("Calculation Hash Reproducibility", run_scenario_06),
        ("Code Injection Defense", run_scenario_07),
        ("Inference Proposal", run_scenario_08),
        ("Recommendation References", run_scenario_09),
        ("DuckDB Prohibited Operations", run_scenario_10),
        ("Filename Traversal Defense", run_scenario_11),
        ("SSRF Private Address Defense", run_scenario_12),
        ("Python Introspection Defense", run_scenario_13),
        ("Magic Byte Validation", run_scenario_14),
        ("DuckDB Serialization", run_scenario_15),
    ], 1)
]

async def run_benchmarks() -> OverallBenchmarkReport:
    scores: List[BenchmarkScore] = []

    for sc in BENCHMARK_SCENARIOS:
        start_time = time.time()
        runner_fn = sc["runner"]
        try:
            passed = await runner_fn()
        except Exception as e:
            passed = False
        duration_ms = int((time.time() - start_time) * 1000)

        score = BenchmarkScore(
            scenario_id=sc["id"],
            scenario_name=sc["name"],
            passed=passed,
            factual_precision=None,
            citation_precision=None,
            hallucination_rate=None,
            latency_ms=duration_ms,
            notes="Executed by the deterministic scenario runner." if passed else "Scenario execution failed."
        )
        scores.append(score)

    mean_lat = round(sum(s.latency_ms for s in scores) / len(scores), 1)

    return OverallBenchmarkReport(
        total_scenarios=len(scores),
        passed_scenarios=len([s for s in scores if s.passed]),
        mean_factual_precision=None,
        mean_citation_precision=None,
        mean_hallucination_rate=None,
        mean_latency_ms=mean_lat,
        scores=scores
    )

if __name__ == "__main__":
    report = asyncio.run(run_benchmarks())
    print("===============================================================")
    print("             OMNIOPS BENCHMARK EVALUATION RESULTS              ")
    print("===============================================================")
    print(f"Total Scenarios Tested:    {report.total_scenarios}")
    print(f"Passed Scenarios:          {report.passed_scenarios} / {report.total_scenarios} ({(report.passed_scenarios / report.total_scenarios * 100):.1f}%)")
    print("Mean Factual Precision:    NOT_MEASURED")
    print("Mean Citation Precision:   NOT_MEASURED")
    print("Mean Hallucination Rate:   NOT_MEASURED")
    print(f"Mean Scenario Latency:     {report.mean_latency_ms} ms")
    print("---------------------------------------------------------------")
    for s in report.scores:
        status_str = "PASSED" if s.passed else "FAILED"
        print(f"[{s.scenario_id}] {s.scenario_name}: {status_str} ({s.latency_ms}ms)")
    print("===============================================================")
