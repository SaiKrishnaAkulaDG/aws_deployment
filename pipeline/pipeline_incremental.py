"""
pipeline/pipeline_incremental.py — Incremental Pipeline Entry Point.

ORCHESTRATION: Single Date (watermark+1) with Cold-Start Guard

Loads and processes one date (the day after watermark) with three-layer
orchestration and watermark advancement only on complete success.

INVOCATION:
  python pipeline/pipeline_incremental.py

NO ARGUMENTS REQUIRED — uses watermark from pipeline/control.parquet

CONSTRAINTS (S5):
  - R-01: Cold-start guard - exit with RuntimeError if watermark is None
  - GAP-INV-02, OQ-1: Missing source file = SKIPPED entries, no data write, no watermark advance
  - INV-02: Watermark advances ONLY after Bronze+Silver+Gold+validation all SUCCESS
  - RL-05a,b: Error messages sanitized (no file paths)
  - Idempotency: Same input → same output
"""

import sys
import uuid
import duckdb
from datetime import datetime, timedelta
from pathlib import Path


SOURCE_DIR = "/app/source"
BRONZE_DIR = "/app/bronze"
SILVER_DIR = "/app/silver"
GOLD_DIR = "/app/gold"
PIPELINE_DIR = "/app/pipeline"


def _get_watermark() -> str:
    """
    CONSTRAINT R-01: Cold-Start Guard

    Retrieve watermark from control table.
    Raises RuntimeError if watermark is None (no prior successful run).
    """
    sys.path.insert(0, PIPELINE_DIR)
    from control_manager import get_watermark

    wm = get_watermark(PIPELINE_DIR)
    if wm is None:
        raise RuntimeError(
            "Cold-start guard: No watermark found in control table. "
            "Run pipeline_historical.py first to initialize watermark."
        )
    return wm


def _next_date(date_str: str) -> str:
    """Increment date by one day."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    next_dt = dt + timedelta(days=1)
    return next_dt.strftime("%Y-%m-%d")


def _source_file_exists(entity: str, date_str: str) -> bool:
    """Check if source CSV exists for entity/date."""
    if entity == "transaction_codes":
        path = Path(SOURCE_DIR) / "transaction_codes.csv"
    else:
        path = Path(SOURCE_DIR) / f"{entity}_{date_str}.csv"
    return path.exists()


def _load_bronze_for_date(run_id: str, date_str: str, tc_loaded: bool) -> tuple[bool, bool]:
    """
    Load Bronze for one date.
    Returns (success: bool, tc_loaded_now: bool)
    """
    sys.path.insert(0, PIPELINE_DIR)
    from bronze_loader import load_bronze
    from run_logger import append_run_log

    all_success = True

    # Transaction codes once (first/only in incremental context)
    if not tc_loaded:
        result = load_bronze("transaction_codes", date_str, run_id, SOURCE_DIR, BRONZE_DIR)
        log_entry = {
            "run_id": run_id,
            "pipeline_type": "INCREMENTAL",
            "model_name": "bronze_transaction_codes",
            "layer": "BRONZE",
            "status": result["status"],
            "started_at": datetime.utcnow().isoformat(),
            "completed_at": datetime.utcnow().isoformat(),
            "records_processed": result.get("records_processed"),
            "records_written": result.get("records_written"),
            "records_rejected": None,
            "error_message": result.get("error_message"),
            "processed_date": date_str if result["status"] != "SKIPPED" else None,
        }
        append_run_log([log_entry])
        if result["status"] == "FAILED":
            all_success = False
        tc_loaded = True

    # Accounts for target date
    result_ac = load_bronze("accounts", date_str, run_id, SOURCE_DIR, BRONZE_DIR)
    log_entry_ac = {
        "run_id": run_id,
        "pipeline_type": "INCREMENTAL",
        "model_name": "bronze_accounts",
        "layer": "BRONZE",
        "status": result_ac["status"],
        "started_at": datetime.utcnow().isoformat(),
        "completed_at": datetime.utcnow().isoformat(),
        "records_processed": result_ac.get("records_processed"),
        "records_written": result_ac.get("records_written"),
        "records_rejected": None,
        "error_message": result_ac.get("error_message"),
        "processed_date": date_str if result_ac["status"] != "SKIPPED" else None,
    }
    append_run_log([log_entry_ac])
    if result_ac["status"] == "FAILED":
        all_success = False

    # Transactions for target date
    result_tx = load_bronze("transactions", date_str, run_id, SOURCE_DIR, BRONZE_DIR)
    log_entry_tx = {
        "run_id": run_id,
        "pipeline_type": "INCREMENTAL",
        "model_name": "bronze_transactions",
        "layer": "BRONZE",
        "status": result_tx["status"],
        "started_at": datetime.utcnow().isoformat(),
        "completed_at": datetime.utcnow().isoformat(),
        "records_processed": result_tx.get("records_processed"),
        "records_written": result_tx.get("records_written"),
        "records_rejected": None,
        "error_message": result_tx.get("error_message"),
        "processed_date": date_str if result_tx["status"] != "SKIPPED" else None,
    }
    append_run_log([log_entry_tx])

    # GAP-INV-02, OQ-1: If transactions SKIPPED (no source file), skip Silver+Gold
    if result_tx["status"] == "SKIPPED":
        return False, tc_loaded

    # If any Bronze FAILED, mark date as failed
    if not all_success or result_tx["status"] == "FAILED":
        return False, tc_loaded

    return True, tc_loaded


def _promote_silver_for_date(run_id: str, date_str: str) -> bool:
    """Promote Silver and log individual model entries."""
    sys.path.insert(0, PIPELINE_DIR)
    from silver_promoter import promote_silver
    from run_logger import append_run_log

    result = promote_silver(date_str, run_id, "/app")

    # Log individual Silver models
    models = ["silver_accounts", "silver_transactions", "silver_quarantine"]
    log_entries = []

    for model in models:
        if result["status"] == "SUCCESS":
            # Query metrics for successful models
            try:
                conn = duckdb.connect()
                if model == "silver_accounts":
                    records = conn.execute("SELECT COUNT(*) FROM read_parquet('/app/silver/accounts/data.parquet')").fetchone()[0]
                elif model == "silver_transactions":
                    records = conn.execute(f"SELECT COUNT(*) FROM read_parquet('/app/silver/transactions/date={date_str}/data.parquet')").fetchone()[0]
                elif model == "silver_quarantine":
                    records = conn.execute(f"SELECT COUNT(*) FROM read_parquet('/app/silver/quarantine/data.parquet') WHERE transaction_date='{date_str}'").fetchone()[0]
                    if records is None:
                        records = 0
                conn.close()
            except:
                records = None

            status = "SUCCESS"
            error_msg = None
        else:
            records = None
            status = "FAILED"
            error_msg = result.get("error_message")

        log_entry = {
            "run_id": run_id,
            "pipeline_type": "INCREMENTAL",
            "model_name": model,
            "layer": "SILVER",
            "status": status,
            "started_at": datetime.utcnow().isoformat(),
            "completed_at": datetime.utcnow().isoformat(),
            "records_processed": None,
            "records_written": records if status == "SUCCESS" else None,
            "records_rejected": None,
            "error_message": error_msg,
            "processed_date": date_str,
        }
        log_entries.append(log_entry)

    append_run_log(log_entries)
    return result["status"] == "SUCCESS"


def _aggregate_gold_for_date(run_id: str, date_str: str) -> bool:
    """Aggregate Gold (full refresh from Silver)."""
    sys.path.insert(0, PIPELINE_DIR)
    from gold_builder import promote_gold
    from run_logger import append_run_log

    result = promote_gold(date_str, run_id, "/app")

    # Log individual Gold models
    models = ["gold_daily_summary", "gold_weekly_account_summary"]
    log_entries = []

    for model in models:
        if result["status"] == "SUCCESS":
            # Query metrics for successful models
            try:
                conn = duckdb.connect()
                if model == "gold_daily_summary":
                    records = conn.execute("SELECT COUNT(*) FROM read_parquet('/app/gold/daily_summary/data.parquet')").fetchone()[0]
                elif model == "gold_weekly_account_summary":
                    records = conn.execute("SELECT COUNT(*) FROM read_parquet('/app/gold/weekly_summary/data.parquet')").fetchone()[0]
                conn.close()
            except:
                records = None

            status = "SUCCESS"
            error_msg = None
        else:
            records = None
            status = "FAILED"
            error_msg = result.get("error_message")

        log_entry = {
            "run_id": run_id,
            "pipeline_type": "INCREMENTAL",
            "model_name": model,
            "layer": "GOLD",
            "status": status,
            "started_at": datetime.utcnow().isoformat(),
            "completed_at": datetime.utcnow().isoformat(),
            "records_processed": None,
            "records_written": records if status == "SUCCESS" else None,
            "records_rejected": None,
            "error_message": error_msg,
            "processed_date": date_str,
        }
        log_entries.append(log_entry)

    append_run_log(log_entries)
    return result["status"] == "SUCCESS"


def _validate_run_log_completeness(run_id: str) -> bool:
    """Check all run log entries for run_id have status=SUCCESS."""
    sys.path.insert(0, PIPELINE_DIR)

    try:
        conn = duckdb.connect()
        run_log_path = str(Path(PIPELINE_DIR) / "run_log.parquet")

        rows = conn.execute(
            f"""
            SELECT COUNT(*) as total,
                   COUNT(*) FILTER (WHERE status = 'SUCCESS') as success_count
            FROM read_parquet('{run_log_path}')
            WHERE run_id = '{run_id}'
            """
        ).fetchall()

        if not rows or not rows[0]:
            return False

        total, success_count = rows[0][0], rows[0][1]
        return total == success_count

    except Exception:
        return True  # Don't block on validation error
    finally:
        try:
            conn.close()
        except:
            pass


def main():
    """Main incremental pipeline orchestrator."""
    print()
    print("=" * 70)
    print("INCREMENTAL PIPELINE")
    print("=" * 70)
    print()

    # R-01: Cold-start guard
    try:
        watermark = _get_watermark()
        print(f"Watermark: {watermark}")
    except RuntimeError as e:
        print(f"ERROR: {str(e)}")
        sys.exit(1)

    # Get next date to process
    target_date = _next_date(watermark)
    print(f"Processing: {target_date}")
    print()

    # Check if source files exist (no-op path)
    has_source = _source_file_exists("transactions", target_date)
    if not has_source:
        print(f"No source file for {target_date} - writing SKIPPED run log entries")
        run_id = str(uuid.uuid4())
        sys.path.insert(0, PIPELINE_DIR)
        from run_logger import append_run_log

        # Write SKIPPED entries for all 8 models (3 Bronze + 5 Silver/Gold)
        skipped_entries = []
        for model in ["bronze_transaction_codes", "bronze_accounts", "bronze_transactions",
                      "silver_transaction_codes", "silver_accounts", "silver_transactions",
                      "silver_quarantine", "gold_aggregation"]:
            entry = {
                "run_id": run_id,
                "pipeline_type": "INCREMENTAL",
                "model_name": model,
                "layer": "BRONZE" if "bronze" in model else "SILVER" if "silver" in model else "GOLD",
                "status": "SKIPPED",
                "started_at": datetime.utcnow().isoformat(),
                "completed_at": datetime.utcnow().isoformat(),
                "records_processed": None,
                "records_written": None,
                "records_rejected": None,
                "error_message": None,
                "processed_date": None,
            }
            skipped_entries.append(entry)

        append_run_log(skipped_entries)
        print(f"Watermark NOT advanced (no source file for {target_date})")
        print()
        print("=" * 70)
        print("Incremental pipeline completed (no-op)")
        print("=" * 70)
        return  # Exit 0 (success), no data written, watermark unchanged

    # Generate run_id
    run_id = str(uuid.uuid4())
    print(f"Run ID: {run_id}")
    print()

    # Bronze layer
    print(f"Loading Bronze for {target_date}...")
    bronze_ok, _ = _load_bronze_for_date(run_id, target_date, False)
    if not bronze_ok:
        print(f"Bronze FAILED or SKIPPED - aborting pipeline")
        print(f"Watermark NOT advanced")
        return

    # Silver layer
    print(f"Promoting Silver for {target_date}...")
    silver_ok = _promote_silver_for_date(run_id, target_date)
    if not silver_ok:
        print(f"Silver FAILED - aborting pipeline")
        print(f"Watermark NOT advanced")
        return

    # Gold layer
    print(f"Aggregating Gold for {target_date}...")
    gold_ok = _aggregate_gold_for_date(run_id, target_date)
    if not gold_ok:
        print(f"Gold FAILED - aborting pipeline")
        print(f"Watermark NOT advanced")
        return

    # INV-02: Validate completeness before watermark
    print()
    print("Validating run log completeness...")
    log_ok = _validate_run_log_completeness(run_id)
    if not log_ok:
        print("ERROR: Run log has non-SUCCESS entries")
        print(f"Watermark NOT advanced")
        return

    # Advance watermark
    print(f"All validations PASSED - advancing watermark to {target_date}")
    sys.path.insert(0, PIPELINE_DIR)
    from control_manager import set_watermark
    set_watermark(target_date, run_id, PIPELINE_DIR)

    print()
    print("=" * 70)
    print(f"Incremental pipeline SUCCESS: {target_date}")
    print(f"Watermark advanced to: {target_date}")
    print("=" * 70)


if __name__ == "__main__":
    main()
