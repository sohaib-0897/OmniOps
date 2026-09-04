import pytest
from app.tools.duckdb_tool import DuckDBTool

def test_duckdb_prohibits_file_access_and_admin_commands():
    tool = DuckDBTool({})

    # 1. Prohibit INSTALL / LOAD
    res1 = tool.execute_query("INSTALL httpfs; LOAD httpfs;")
    assert res1.success is False
    assert "Security violation" in res1.error_message

    # 2. Prohibit ATTACH
    res2 = tool.execute_query("ATTACH 'database.db' AS db;")
    assert res2.success is False
    assert "Security violation" in res2.error_message

    # 3. Prohibit read_parquet arbitrary disk access
    res3 = tool.execute_query("SELECT * FROM read_parquet('/etc/passwd');")
    assert res3.success is False
    assert "Security violation" in res3.error_message

    # 4. Prohibit DROP / DELETE / UPDATE mutating commands
    res4 = tool.execute_query("DROP TABLE users;")
    assert res4.success is False
    assert "Security violation" in res4.error_message

    # 5. Prohibit COPY abuse
    res5 = tool.execute_query("COPY users TO '/tmp/dump.csv';")
    assert res5.success is False
    assert "Security violation" in res5.error_message

def test_duckdb_complex_types_and_json_serialization():
    import tempfile
    import json
    from pathlib import Path
    import pandas as pd

    with tempfile.TemporaryDirectory() as tmpdir:
        df = pd.DataFrame({
            "event_time": [pd.Timestamp("2026-08-28 12:00:00"), pd.Timestamp("2026-08-29 15:30:00")],
            "event_date": [pd.to_datetime("2026-08-28").date(), pd.to_datetime("2026-08-29").date()],
            "revenue": [12345.67, 98765.43],
            "notes": [None, "Verified transaction"]
        })
        p_path = Path(tmpdir) / "transactions.parquet"
        df.to_parquet(str(p_path), index=False)

        tool = DuckDBTool({"transactions": str(p_path)})
        res = tool.execute_query("SELECT event_time, event_date, revenue, notes FROM transactions;")
        assert res.success is True
        assert len(res.data) == 2

        # Verify json serialization succeeds without TypeError
        serialized = json.dumps(res.data, default=str)
        assert "2026-08-28" in serialized
        assert "12345.67" in serialized
