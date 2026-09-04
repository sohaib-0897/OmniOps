import os
import re
import time
import hashlib
import json
import duckdb
import pyarrow.parquet as pq
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

FORBIDDEN_SQL_KEYWORDS = [
    r"\bINSTALL\b", r"\bLOAD\b", r"\bATTACH\b", r"\bDETACH\b",
    r"\bCOPY\b", r"\bEXPORT\b", r"\bIMPORT\b",
    r"\bDROP\b", r"\bDELETE\b", r"\bUPDATE\b", r"\bINSERT\b", r"\bALTER\b",
    r"\bCREATE\s+SECRET\b", r"\bread_csv\b", r"\bread_parquet\b", r"\bread_json\b"
]

class DuckDBToolResult(BaseModel):
    success: bool
    data: Optional[List[Dict[str, Any]]] = None
    columns: Optional[List[str]] = None
    row_count: int = 0
    duration_ms: int = 0
    error_message: Optional[str] = None
    reproducibility_hash: Optional[str] = None

class DuckDBTool:
    """Secure vectorized SQL execution tool against registered workspace datasets."""

    def __init__(self, table_parquet_map: Dict[str, str]):
        """
        table_parquet_map: dict mapping table_name -> absolute parquet file path
        """
        self.table_parquet_map = table_parquet_map

    def _validate_sql_security(self, sql_query: str) -> None:
        """Reject dangerous SQL commands and arbitrary file readers."""
        for pattern in FORBIDDEN_SQL_KEYWORDS:
            if re.search(pattern, sql_query, re.IGNORECASE):
                raise ValueError(f"Security violation: SQL query contains forbidden operation matching '{pattern}'")

    def execute_query(self, sql_query: str, max_rows: int = 500) -> DuckDBToolResult:
        """Execute read-only SQL query against registered parquet tables."""
        start_time = time.time()
        try:
            self._validate_sql_security(sql_query)

            # Initialize ephemeral, secure in-memory DuckDB connection
            # Strict sandbox: disable external filesystem/network access
            con = duckdb.connect(database=":memory:", config={"enable_external_access": False})
            
            try:
                # Register authorized in-memory Arrow tables
                registered_names = []
                for table_name, parquet_path in self.table_parquet_map.items():
                    clean_name = re.sub(r"[^a-zA-Z0-9_]", "_", table_name)
                    if os.path.exists(str(parquet_path)):
                        arrow_table = pq.read_table(str(parquet_path))
                        con.register(clean_name, arrow_table)
                        registered_names.append(clean_name)
                        # DuckDB retains the Arrow object while registered. It
                        # must be explicitly unregistered before the temporary
                        # parquet directory is removed on Windows.
                        del arrow_table

                # Execute user query
                cursor = con.execute(sql_query)
                columns = [desc[0] for desc in cursor.description] if cursor.description else []
                rows = cursor.fetchmany(max_rows)
                
                duration_ms = int((time.time() - start_time) * 1000)
                
                # Format into JSON-safe dict rows
                raw_dict_rows = [dict(zip(columns, row)) for row in rows]
                dict_rows = json.loads(json.dumps(raw_dict_rows, default=str))
                
                # Compute deterministic reproducibility hash
                hash_input = json.dumps(
                    {"sql": sql_query.strip(), "rows": dict_rows[:10]}, 
                    sort_keys=True, 
                    default=str
                )
                repro_hash = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
                
                return DuckDBToolResult(
                    success=True,
                    data=dict_rows,
                    columns=columns,
                    row_count=len(dict_rows),
                    duration_ms=duration_ms,
                    reproducibility_hash=repro_hash
                )
            finally:
                for name in locals().get("registered_names", []):
                    try:
                        con.unregister(name)
                    except Exception:
                        pass
                con.close()

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return DuckDBToolResult(
                success=False,
                data=None,
                columns=None,
                row_count=0,
                duration_ms=duration_ms,
                error_message=str(e),
                reproducibility_hash=None
            )
