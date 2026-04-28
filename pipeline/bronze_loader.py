"""
pipeline/bronze_loader.py — CSV ingestion into Bronze layer with idempotency.

Reads source CSV, validates schema, checks for existing Bronze partition (row count idempotency),
and writes to bronze/{entity}/date=YYYY-MM-DD/data.parquet with audit columns.

Audit columns added to every row:
  - _pipeline_run_id: UUIDv4 identifying the pipeline invocation (INV-04 GLOBAL)
  - _ingested_at: Current UTC datetime ISO string
  - _source_file: Basename of source file (no directory path)
"""

import pandas as pd
import duckdb
from pathlib import Path
from typing import Optional
from datetime import datetime


# Expected schemas for each entity (matching actual CSV files)
EXPECTED_SCHEMAS = {
    "transactions": {
        "transaction_id", "account_id", "transaction_date", "amount",
        "transaction_code", "merchant_name", "channel"
    },
    "accounts": {
        "account_id", "customer_name", "account_status", "credit_limit",
        "current_balance", "open_date", "billing_cycle_start", "billing_cycle_end"
    },
    "transaction_codes": {
        "transaction_code", "description", "debit_credit_indicator",
        "transaction_type", "affects_balance"
    },
}


def _get_source_path(entity: str, date_str: str, source_dir: str) -> Path:
    """Determine source file path. transaction_codes has no date suffix."""
    if entity == "transaction_codes":
        return Path(source_dir) / f"{entity}.csv"
    return Path(source_dir) / f"{entity}_{date_str}.csv"


def _validate_schema(df: pd.DataFrame, entity: str) -> tuple[bool, Optional[str]]:
    """Validate CSV schema against expected columns."""
    expected = EXPECTED_SCHEMAS.get(entity)
    if not expected:
        return False, f"Unknown entity: {entity}"

    actual = set(df.columns)
    if actual != expected:
        missing = expected - actual
        extra = actual - expected
        msg = f"Schema mismatch for {entity}"
        if missing:
            msg += f"; missing: {missing}"
        if extra:
            msg += f"; extra: {extra}"
        return False, msg

    return True, None


def _count_parquet_rows(parquet_path: Path) -> int:
    """Count rows in a Parquet file. Return 0 if file absent."""
    if not parquet_path.exists():
        return 0
    conn = duckdb.connect()
    result = conn.execute(f"SELECT COUNT(*) FROM read_parquet('{parquet_path}')").fetchone()[0]
    conn.close()
    return result


def _get_bronze_path(entity: str, date_str: str, bronze_dir: str) -> Path:
    """Get target Bronze Parquet path: bronze/{entity}/date={date_str}/data.parquet (INV-10)."""
    return Path(bronze_dir) / entity / f"date={date_str}" / "data.parquet"


def _add_audit_columns(df: pd.DataFrame, run_id: str, source_file: str) -> pd.DataFrame:
    """Add audit columns to every row (INV-04 GLOBAL, INV-08)."""
    df["_pipeline_run_id"] = run_id
    df["_ingested_at"] = datetime.utcnow().isoformat()
    df["_source_file"] = source_file
    return df


def _delete_partition(parquet_path: Path) -> None:
    """Delete partition directory and all contents."""
    if parquet_path.exists():
        import shutil
        shutil.rmtree(parquet_path.parent)


def load_bronze(entity: str, date_str: str, run_id: str,
                source_dir: str, bronze_dir: str) -> dict:
    """
    Ingest one source CSV file into a Bronze Parquet partition.

    Args:
        entity: "transactions", "accounts", or "transaction_codes"
        date_str: YYYY-MM-DD (ignored for transaction_codes)
        run_id: UUIDv4 identifying this pipeline invocation
        source_dir: Path to source directory
        bronze_dir: Path to bronze directory

    Returns:
        {
            "status": "SUCCESS" | "FAILED" | "SKIPPED",
            "records_processed": int | None,
            "records_written": int | None,
            "error_message": str | None,
            "entity": str,
            "date_str": str
        }
    """
    source_path = _get_source_path(entity, date_str, source_dir)
    bronze_path = _get_bronze_path(entity, date_str, bronze_dir)

    # Check: source file absent → SKIPPED (GAP-INV-02, OQ-1)
    if not source_path.exists():
        return {
            "status": "SKIPPED",
            "records_processed": None,
            "records_written": None,
            "error_message": None,
            "entity": entity,
            "date_str": date_str,
        }

    try:
        # Read CSV
        df = pd.read_csv(source_path)
        records_processed = len(df)

        # Validate schema (S1B-schema)
        valid, schema_error = _validate_schema(df, entity)
        if not valid:
            return {
                "status": "FAILED",
                "records_processed": records_processed,
                "records_written": None,
                "error_message": schema_error,
                "entity": entity,
                "date_str": date_str,
            }

        # Idempotency check (Decision 3, INV-01a)
        existing_count = _count_parquet_rows(bronze_path)
        if existing_count == records_processed and bronze_path.exists():
            # Partition exists + row count matches → SUCCESS immediately (no rewrite)
            return {
                "status": "SUCCESS",
                "records_processed": records_processed,
                "records_written": existing_count,
                "error_message": None,
                "entity": entity,
                "date_str": date_str,
            }

        # Row count mismatch → delete partition and re-ingest (S1B-03)
        if bronze_path.exists():
            _delete_partition(bronze_path)

        # Add audit columns (INV-04 GLOBAL, INV-08)
        source_filename = source_path.name
        df = _add_audit_columns(df, run_id, source_filename)

        # Write Parquet to target path (S1B-parquet)
        bronze_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(bronze_path, index=False)

        records_written = len(df)

        return {
            "status": "SUCCESS",
            "records_processed": records_processed,
            "records_written": records_written,
            "error_message": None,
            "entity": entity,
            "date_str": date_str,
        }

    except Exception as e:
        return {
            "status": "FAILED",
            "records_processed": None,
            "records_written": None,
            "error_message": str(e),
            "entity": entity,
            "date_str": date_str,
        }
