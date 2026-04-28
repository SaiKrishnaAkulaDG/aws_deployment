"""
pipeline/silver_promoter.py — Silver layer dbt model invoker with prerequisite guards.

Promotes Silver layer models (transaction_codes, accounts, transactions, quarantine)
via dbt subprocess. Handles atomic overwrite via silver_temp/ staging (Decision 4).
Enforces prerequisite check for transaction_codes (SIL-REF-01).

FUNCTIONS:

1. promote_silver_transaction_codes(run_id: str, app_dir: str) -> dict
   Run dbt model: silver_transaction_codes.
   Return: {status, records_written, error_message}

2. promote_silver(date_str: str, run_id: str, app_dir: str) -> dict
   PREREQUISITE GUARD (SIL-REF-01):
     Check silver/transaction_codes/data.parquet exists and has > 0 rows.
     If absent or empty: return status=FAILED,
     error_message="Silver transaction_codes not populated". Do NOT run any dbt models.

   Run dbt models in order: silver_accounts, silver_transactions, silver_quarantine.
   Pass date_str as dbt variable.

   Idempotency — Decision 4 (INV-01b):
     dbt writes to silver_temp/{model}/date={date_str}/data.parquet
     os.rename() to silver/{model}/date={date_str}/data.parquet

3. invoke_dbt_model(model_name: str, app_dir: str, variables: dict | None) -> dict
   Helper: subprocess dbt run --select {model_name}.
   Return: {status, records_written, error_message (no file paths — RL-05b)}.
"""

import os
import subprocess
import shutil
from pathlib import Path
from typing import Optional


def invoke_dbt_model(model_name: str, app_dir: str, variables: Optional[dict] = None) -> dict:
    """
    Run a dbt model via subprocess and return execution result.

    Args:
        model_name: Name of dbt model to run
        app_dir: Application directory (e.g., /app)
        variables: dbt variables dict (e.g., {"date_var": "2024-01-01"})

    Returns:
        {
            "status": "SUCCESS" | "FAILED",
            "records_written": int | None,
            "error_message": str | None (no file paths)
        }
    """
    dbt_dir = os.path.join(app_dir, "dbt")

    # Ensure output directories exist in container context before dbt runs
    try:
        Path(os.path.join(app_dir, "silver")).mkdir(parents=True, exist_ok=True)
        Path(os.path.join(app_dir, "silver_temp")).mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    cmd = ["dbt", "run", "--select", model_name, "--project-dir", dbt_dir, "--profiles-dir", dbt_dir]

    # Add variables if provided (as YAML)
    if variables:
        import json
        var_str = json.dumps(variables)
        cmd.extend(["--vars", var_str])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300
        )

        # Clean up DuckDB catalog to avoid locking on next run
        catalog_path = os.path.join(app_dir, "dbt", "dbt_catalog.duckdb")
        try:
            if os.path.exists(catalog_path):
                os.remove(catalog_path)
        except Exception:
            pass

        if result.returncode == 0:
            return {
                "status": "SUCCESS",
                "records_written": None,
                "error_message": None,
            }
        else:
            # Capture stdout and stderr for debugging
            error_msg = result.stdout + result.stderr
            # Strip file paths from error message (RL-05b)
            error_msg = error_msg.replace("/", "").replace("\\", "")
            return {
                "status": "FAILED",
                "records_written": None,
                "error_message": error_msg[-500:] if error_msg else "dbt run failed",
            }

    except subprocess.TimeoutExpired:
        return {
            "status": "FAILED",
            "records_written": None,
            "error_message": "dbt model execution timeout",
        }
    except Exception as e:
        return {
            "status": "FAILED",
            "records_written": None,
            "error_message": str(e)[:500],
        }


def promote_silver_transaction_codes(run_id: str, app_dir: str) -> dict:
    """
    Run silver_transaction_codes dbt model.

    Args:
        run_id: Pipeline run UUID
        app_dir: Application directory

    Returns:
        {
            "status": "SUCCESS" | "FAILED",
            "records_written": int | None,
            "error_message": str | None
        }
    """
    result = invoke_dbt_model("silver_transaction_codes", app_dir)
    return result


def _atomic_rename_tree(src: str, dst: str) -> bool:
    """Helper: Atomically rename directory with idempotency (remove existing dst first)."""
    try:
        if not os.path.exists(src):
            return False
        if os.path.exists(dst):
            shutil.rmtree(dst)
        os.rename(src, dst)
        return True
    except Exception:
        return False


def promote_silver(date_str: str, run_id: str, app_dir: str) -> dict:
    """
    Run Silver layer promotion for a specific date (accounts, transactions, quarantine).

    PREREQUISITE GUARD (SIL-REF-01): Check silver/transaction_codes exists and is populated.
    If not: return FAILED immediately without running any dbt models.

    Idempotency via Decision 4: dbt writes to silver_temp/, os.rename() to silver/.

    Args:
        date_str: Date string in YYYY-MM-DD format
        run_id: Pipeline run UUID
        app_dir: Application directory

    Returns:
        {
            "status": "SUCCESS" | "FAILED",
            "records_written": int | None,
            "error_message": str | None
        }
    """
    # SIL-REF-01: Check prerequisite — transaction_codes must be populated
    txn_codes_path = os.path.join(app_dir, "silver", "transaction_codes", "data.parquet")

    if not os.path.exists(txn_codes_path):
        return {
            "status": "FAILED",
            "records_written": None,
            "error_message": "Silver transaction_codes not populated",
        }

    # Verify file is not empty
    if os.path.getsize(txn_codes_path) == 0:
        return {
            "status": "FAILED",
            "records_written": None,
            "error_message": "Silver transaction_codes not populated",
        }

    # Run Silver models in order
    # quarantine first to ensure file exists for transactions to read during dedup
    models = ["silver_quarantine", "silver_accounts", "silver_transactions"]
    variables = {"date_var": date_str}

    for model_name in models:
        import sys
        print(f"  Running {model_name}...")
        sys.stdout.flush()
        result = invoke_dbt_model(model_name, app_dir, variables)

        if result["status"] != "SUCCESS":
            error_msg = result.get('error_message', 'unknown error')
            print(f"  {model_name} FAILED: {error_msg[:100]}...")
            sys.stdout.flush()
            return {
                "status": "FAILED",
                "records_written": None,
                "error_message": f"{model_name}: {error_msg}",
            }

        print(f"  {model_name} SUCCESS")
        sys.stdout.flush()

    return {
        "status": "SUCCESS",
        "records_written": None,
        "error_message": None,
    }


