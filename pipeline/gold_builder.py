"""
gold_builder.py — Gold Layer dbt Model Invoker

Invokes Gold dbt models (gold_daily_summary, gold_weekly_account_summary) via subprocess.
Returns structured result dict to pipeline orchestrators.

Invariants enforced:
- S1B-dbt-silver-gold: All transformation logic in dbt models, Python is invoker only
- GAP-INV-05: External materialization overwrites (no append)
- INV-01d: Idempotent rerun produces identical output
- RL-05b: Error messages stripped of file paths before returning
- Single stateable purpose: invoke Gold dbt models
"""

import subprocess
import json
import os


def invoke_dbt_gold_model(model_name: str, app_dir: str, variables: dict = None) -> dict:
    """
    Invoke a dbt Gold model via subprocess.

    Args:
        model_name: dbt model name (e.g., 'gold_daily_summary')
        app_dir: Application root directory (/app in container)
        variables: Optional dict of dbt variables to pass as JSON

    Returns:
        {
            'status': 'SUCCESS' | 'FAILED',
            'records_written': None,
            'error_message': str | None
        }
    """
    dbt_dir = os.path.join(app_dir, 'dbt')

    cmd = [
        'dbt', 'run',
        '--select', model_name,
        '--project-dir', dbt_dir,
        '--profiles-dir', dbt_dir
    ]

    if variables:
        cmd.extend(['--vars', json.dumps(variables)])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300
        )

        if result.returncode == 0:
            return {
                'status': 'SUCCESS',
                'records_written': None,
                'error_message': None
            }
        else:
            # Concatenate stdout and stderr, strip paths (RL-05b)
            error_output = (result.stdout + result.stderr).replace('/', '').replace('\\', '')
            return {
                'status': 'FAILED',
                'records_written': None,
                'error_message': error_output
            }

    except subprocess.TimeoutExpired:
        return {
            'status': 'FAILED',
            'records_written': None,
            'error_message': f'dbt {model_name} timeout after 300 seconds'
        }
    except Exception as e:
        return {
            'status': 'FAILED',
            'records_written': None,
            'error_message': str(e).replace('/', '').replace('\\', '')
        }


def promote_gold(date_str: str, run_id: str, app_dir: str) -> dict:
    """
    Invoke Gold dbt models for a given date.

    Runs models in order:
    1. gold_daily_summary
    2. gold_weekly_account_summary

    Both models read from Silver layer exclusively (S1B-gold-source).
    External materialization handles overwrites (GAP-INV-05).

    Args:
        date_str: Date string for partitioning (ISO 8601, e.g., '2024-01-01')
        run_id: Pipeline run identifier (UUIDv4)
        app_dir: Application root directory (/app in container)

    Returns:
        {
            'status': 'SUCCESS' | 'FAILED',
            'records_written': None,
            'error_message': str | None
        }
    """
    models = ['gold_daily_summary', 'gold_weekly_account_summary']
    variables = {'date_var': date_str}

    # Run each model in sequence
    for model in models:
        result = invoke_dbt_gold_model(model, app_dir, variables)

        # Short-circuit on first failure
        if result['status'] == 'FAILED':
            return result

    # All models succeeded
    return {
        'status': 'SUCCESS',
        'records_written': None,
        'error_message': None
    }
