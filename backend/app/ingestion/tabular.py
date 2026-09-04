import re
import uuid
from pathlib import Path
from typing import Dict, Any, List, Tuple
import pandas as pd
import pyarrow.parquet as pq
from app.core.config import settings

def clean_table_name(filename: str, sheet_name: str = "") -> str:
    """Derive clean, SQL-friendly table identifier."""
    stem = Path(filename).stem
    combined = f"{stem}_{sheet_name}" if sheet_name else stem
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", combined).lower()
    cleaned = re.sub(r"_{2,}", "_", cleaned).strip("_")
    if not cleaned or cleaned[0].isdigit():
        cleaned = f"t_{cleaned}"
    return cleaned[:63]  # Standard SQL identifier limit

def profile_dataframe(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Compute detailed column metadata, statistics, and sample values."""
    schema_stats = []
    total_rows = len(df)
    
    for col in df.columns:
        col_series = df[col]
        col_type = str(col_series.dtype)
        null_count = int(col_series.isnull().sum())
        null_pct = round((null_count / total_rows * 100), 2) if total_rows > 0 else 0.0
        unique_count = int(col_series.nunique(dropna=True))
        
        # Get up to 3 non-null sample values
        non_null_samples = col_series.dropna().head(3).tolist()
        sample_values = [str(val) for val in non_null_samples]
        
        stat_item = {
            "name": str(col),
            "type": col_type,
            "null_count": null_count,
            "null_percentage": null_pct,
            "unique_count": unique_count,
            "sample_values": sample_values,
        }
        
        # Min/Max for numeric / datetime
        if pd.api.types.is_numeric_dtype(col_series) and not col_series.dropna().empty:
            stat_item["min"] = float(col_series.min())
            stat_item["max"] = float(col_series.max())
            stat_item["mean"] = round(float(col_series.mean()), 2)
        elif pd.api.types.is_datetime64_any_dtype(col_series) and not col_series.dropna().empty:
            stat_item["min"] = str(col_series.min())
            stat_item["max"] = str(col_series.max())
            
        schema_stats.append(stat_item)
    return schema_stats

def process_tabular_file(
    file_path: str,
    workspace_id: uuid.UUID,
    original_filename: str
) -> List[Dict[str, Any]]:
    """Convert CSV or Excel file to Parquet datasets and compute schemas."""
    path = Path(file_path)
    ext = path.suffix.lower()
    results = []
    
    workspace_parquet_dir = settings.PARQUET_DIR / str(workspace_id)
    workspace_parquet_dir.mkdir(parents=True, exist_ok=True)
    
    if ext in [".csv", ".tsv", ".txt"]:
        sep = "\t" if ext == ".tsv" else ","
        try:
            df = pd.read_csv(file_path, sep=sep, low_memory=False, encoding_errors="replace")
        except Exception:
            df = pd.read_csv(file_path, sep=None, engine="python", encoding_errors="replace")
            
        # Clean column names
        df.columns = [re.sub(r"[^a-zA-Z0-9_]", "_", str(c)).strip("_") for c in df.columns]
        table_name = clean_table_name(original_filename)
        parquet_path = workspace_parquet_dir / f"{table_name}.parquet"
        
        df.to_parquet(str(parquet_path), index=False, engine="pyarrow")
        schema_def = profile_dataframe(df)
        
        results.append({
            "table_name": table_name,
            "row_count": len(df),
            "column_count": len(df.columns),
            "schema_definition": schema_def,
            "parquet_storage_path": str(parquet_path),
        })
        
    elif ext in [".xlsx", ".xls"]:
        excel_file = pd.ExcelFile(file_path)
        for sheet_name in excel_file.sheet_names:
            df = pd.read_excel(excel_file, sheet_name=sheet_name)
            if df.empty:
                continue
                
            df.columns = [re.sub(r"[^a-zA-Z0-9_]", "_", str(c)).strip("_") for c in df.columns]
            table_name = clean_table_name(original_filename, sheet_name if len(excel_file.sheet_names) > 1 else "")
            parquet_path = workspace_parquet_dir / f"{table_name}.parquet"
            
            df.to_parquet(str(parquet_path), index=False, engine="pyarrow")
            schema_def = profile_dataframe(df)
            
            results.append({
                "table_name": table_name,
                "row_count": len(df),
                "column_count": len(df.columns),
                "schema_definition": schema_def,
                "parquet_storage_path": str(parquet_path),
            })
            
    return results
