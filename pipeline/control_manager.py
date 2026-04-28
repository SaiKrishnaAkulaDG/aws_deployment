"""
pipeline/control_manager.py — Watermark and control table management.

Manages pipeline state via pipeline/control.parquet. Tracks the most recent date for which
all layers completed successfully (last_processed_date), along with metadata about when
the watermark was last updated (updated_at) and the specific pipeline run responsible
for advancing it (updated_by_run_id).

Control table schema:
  - last_processed_date: YYYY-MM-DD of the most recent successful full pipeline run
  - updated_at: ISO 8601 datetime when the watermark was last advanced
  - updated_by_run_id: UUIDv4 of the pipeline run that advanced the watermark
"""

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta


def _create_control_schema() -> pa.Schema:
    """Define the control table schema."""
    return pa.schema([
        ("last_processed_date", pa.string()),
        ("updated_at", pa.string()),
        ("updated_by_run_id", pa.string()),
    ])


def get_watermark(pipeline_dir: str) -> Optional[str]:
    """
    Read watermark from pipeline/control.parquet.

    Returns the most recent date for which all layers completed successfully (last_processed_date).

    Args:
        pipeline_dir: Path to pipeline directory

    Returns:
        Watermark date as YYYY-MM-DD string, or None if control.parquet absent (cold start).
        Cold start (None return) is not an error at module level — caller handles via RuntimeError (R-01).
    """
    control_path = Path(pipeline_dir) / "control.parquet"

    if not control_path.exists():
        return None

    table = pq.read_table(control_path)
    df = table.to_pandas()

    if df.empty:
        return None

    # Get the most recent watermark (last row represents latest state)
    last_processed_date = df["last_processed_date"].iloc[-1]
    return str(last_processed_date)


def set_watermark(date_str: str, run_id: str, pipeline_dir: str) -> None:
    """
    Write watermark to pipeline/control.parquet.

    Called ONLY as the final operation in a fully successful pipeline run (INV-02).

    Args:
        date_str: Date string in YYYY-MM-DD format (last_processed_date)
        run_id: UUIDv4 of the pipeline run advancing the watermark
        pipeline_dir: Path to pipeline directory
    """
    control_path = Path(pipeline_dir) / "control.parquet"
    control_path.parent.mkdir(parents=True, exist_ok=True)

    # Create record with enhanced watermark metadata
    record = {
        "last_processed_date": date_str,
        "updated_at": datetime.utcnow().isoformat(),
        "updated_by_run_id": run_id,
    }

    # Create DataFrame and write to Parquet with schema
    df = pd.DataFrame([record])
    schema = _create_control_schema()
    table = pa.Table.from_pandas(df, schema=schema)
    pq.write_table(table, control_path)


def get_next_date(pipeline_dir: str) -> Optional[str]:
    """
    Get the next date to process (current watermark + 1 day).

    Returns the date that should be processed next based on the last_processed_date.

    Args:
        pipeline_dir: Path to pipeline directory

    Returns:
        Next date as YYYY-MM-DD string, or None if no watermark exists (cold start).
    """
    watermark = get_watermark(pipeline_dir)

    if watermark is None:
        return None

    # Parse date and add 1 day
    current = datetime.strptime(watermark, "%Y-%m-%d")
    next_date = current + timedelta(days=1)

    return next_date.strftime("%Y-%m-%d")
