import os
import uuid
import pandas as pd
import pytest
from app.ingestion.tabular import process_tabular_file, clean_table_name, profile_dataframe
from app.tools.duckdb_tool import DuckDBTool
from app.core.config import settings

def test_clean_table_name():
    assert clean_table_name("Q3 2026 Sales Report.xlsx", "Sheet1") == "q3_2026_sales_report_sheet1"
    assert clean_table_name("123_data.csv") == "t_123_data"
    assert clean_table_name("user-churn--rate.csv") == "user_churn_rate"

def test_tabular_parquet_and_duckdb_execution(tmp_path):
    # 1. Create sample sales CSV
    df = pd.DataFrame({
        "quarter": ["Q1", "Q2", "Q3"],
        "revenue": [1000000.0, 1200000.0, 800000.0],
        "cost": [600000.0, 700000.0, 650000.0]
    })
    csv_file = tmp_path / "sales_summary.csv"
    df.to_csv(csv_file, index=False)

    workspace_id = uuid.uuid4()
    results = process_tabular_file(str(csv_file), workspace_id, "sales_summary.csv")
    
    assert len(results) == 1
    table_meta = results[0]
    assert table_meta["row_count"] == 3
    assert table_meta["column_count"] == 3
    assert os.path.exists(table_meta["parquet_storage_path"])

    # 2. Run DuckDB Tool
    tool = DuckDBTool({table_meta["table_name"]: table_meta["parquet_storage_path"]})
    
    # Valid Aggregation Query
    query = f"SELECT quarter, revenue - cost AS profit FROM {table_meta['table_name']} ORDER BY profit DESC;"
    res = tool.execute_query(query)
    
    assert res.success is True
    assert len(res.data) == 3
    assert res.data[0]["quarter"] == "Q2"
    assert res.data[0]["profit"] == 500000.0
    assert res.reproducibility_hash is not None

    # 3. Forbidden SQL Security Check (Prohibit DROP / read_csv / INSTALL)
    forbidden_queries = [
        f"DROP TABLE {table_meta['table_name']};",
        "SELECT * FROM read_csv('/etc/passwd');",
        "INSTALL httpfs;",
        "ATTACH 'database.db';",
        "COPY sales TO '/tmp/out.csv';"
    ]
    for bad_sql in forbidden_queries:
        bad_res = tool.execute_query(bad_sql)
        assert bad_res.success is False
        assert "Security violation" in bad_res.error_message

def test_tabular_reupload_upsert(tmp_path):
    workspace_id = uuid.uuid4()
    
    # Version 1 of dataset
    df1 = pd.DataFrame({"col_a": [1, 2], "col_b": [10, 20]})
    file_v1 = tmp_path / "dataset.csv"
    df1.to_csv(file_v1, index=False)
    
    res1 = process_tabular_file(str(file_v1), workspace_id, "dataset.csv")
    assert res1[0]["row_count"] == 2
    
    # Version 2 of dataset (re-upload with more rows & new column)
    df2 = pd.DataFrame({"col_a": [1, 2, 3], "col_b": [10, 20, 30], "col_c": [100, 200, 300]})
    file_v2 = tmp_path / "dataset.csv"
    df2.to_csv(file_v2, index=False)
    
    res2 = process_tabular_file(str(file_v2), workspace_id, "dataset.csv")
    assert res2[0]["row_count"] == 3
    assert res2[0]["column_count"] == 3
    
    # Verify DuckDB can query the updated parquet immediately
    tool = DuckDBTool({res2[0]["table_name"]: res2[0]["parquet_storage_path"]})
    q_res = tool.execute_query(f"SELECT SUM(col_c) AS total_c FROM {res2[0]['table_name']};")
    assert q_res.success is True
    assert q_res.data[0]["total_c"] == 600
