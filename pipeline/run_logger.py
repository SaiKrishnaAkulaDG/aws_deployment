"""
pipeline/run_logger.py — Append-only run log writer for the Credit Card Transactions Lake.

Writes to pipeline/run_log.parquet. One row per model per invocation.
Captures pipeline execution metadata: run_id, pipeline_type, model_name, layer,
timestamps, status, metrics, and optional error_message.

Schema:
  - run_id: UUIDv4 identifying the pipeline invocation
  - pipeline_type: HISTORICAL or INCREMENTAL
  - model_name: Name of the model (e.g., bronze_transactions, silver_accounts)
  - layer: BRONZE, SILVER, or GOLD
  - started_at: ISO 8601 datetime when execution started
  - completed_at: ISO 8601 datetime when execution completed
  - status: SUCCESS, FAILED, or SKIPPED
  - records_processed: Number of records read/processed
  - records_written: Number of records written
  - records_rejected: Number of records rejected (Silver layer only; NULL for Bronze/Gold)
  - error_message: Sanitized error details on failure; NULL on success
  - processed_date: YYYY-MM-DD of the data being processed; NULL for SKIPPED
"""

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pathlib import Path
from typing import Optional


RUN_LOG_PATH = Path("/app/pipeline/run_log.parquet")


def _clean_error_message(msg: Optional[str]) -> Optional[str]:
    """Strip path separators from error message to avoid exposing sensitive paths (RL-05b)."""
    if msg is None:
        return None
    return msg.replace("/", "").replace("\\", "")


def _get_existing_records() -> list[dict]:
    """Read existing run log records. Return empty list if file absent."""
    if not RUN_LOG_PATH.exists():
        return []
    table = pq.read_table(RUN_LOG_PATH)
    return table.to_pandas().to_dict("records")


def _create_schema() -> pa.Schema:
    """Define the run log schema."""
    return pa.schema([
        ("run_id", pa.string()),
        ("pipeline_type", pa.string()),
        ("model_name", pa.string()),
        ("layer", pa.string()),
        ("started_at", pa.string()),
        ("completed_at", pa.string()),
        ("status", pa.string()),
        ("records_processed", pa.int64()),
        ("records_written", pa.int64()),
        ("records_rejected", pa.int64()),
        ("error_message", pa.string()),
        ("processed_date", pa.string()),
    ])


def _enforce_constraints(records: list[dict]) -> None:
    """
    Enforce field-level constraints per RL-04, RL-05a, RL-05b.

    - RL-04: records_rejected must be NULL for Bronze and Gold layers (Silver only)
    - RL-05a: error_message must be NULL on SUCCESS
    - RL-05b: Strip path separators from error_message to avoid exposing sensitive paths
    """
    silver_layer = "SILVER"

    for record in records:
        layer = record.get("layer", "")

        # RL-04: records_rejected must be null for non-Silver layers
        if layer != silver_layer:
            record["records_rejected"] = None

        # RL-05a: error_message must be null on SUCCESS
        if record.get("status") == "SUCCESS":
            record["error_message"] = None
        else:
            # RL-05b: strip path separators from error_message
            if record.get("error_message"):
                record["error_message"] = _clean_error_message(record["error_message"])


def append_run_log(records: list[dict]) -> None:
    """
    Append records to pipeline/run_log.parquet.

    Creates file on first write with correct schema. Never modifies existing rows.
    Logically append-only: reads existing, appends new, overwrites file atomically.

    Args:
        records: List of dicts with run_id, pipeline_type, model_name, layer,
                 started_at, completed_at, status, records_processed, records_written,
                 records_rejected, error_message, processed_date.
    """
    # Enforce constraints before writing
    _enforce_constraints(records)

    # Read existing records
    existing = _get_existing_records()

    # Combine: existing + new (logically append-only)
    all_records = existing + records

    # Convert to DataFrame
    df = pd.DataFrame(all_records)

    # Ensure correct column order and types
    column_order = [
        "run_id", "pipeline_type", "model_name", "layer",
        "started_at", "completed_at", "status",
        "records_processed", "records_written", "records_rejected",
        "error_message", "processed_date"
    ]
    df = df[column_order]

    # Convert to PyArrow table with schema
    schema = _create_schema()
    table = pa.Table.from_pandas(df, schema=schema)

    # Write (overwrite file to implement logical append-only semantics)
    RUN_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, RUN_LOG_PATH)


def get_run_log() -> pd.DataFrame:
    """
    Read pipeline/run_log.parquet.

    Returns:
        DataFrame with all run log records, or empty DataFrame if file absent.
    """
    if not RUN_LOG_PATH.exists():
        return pd.DataFrame()

    table = pq.read_table(RUN_LOG_PATH)
    return table.to_pandas()
