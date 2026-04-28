#!/bin/bash
# run_pipeline_and_sync.sh — Run historical pipeline and sync parquet files to local directory

set -e

echo "=========================================="
echo "Credit Card Transactions Lake"
echo "Pipeline Execution + File Sync"
echo "=========================================="
echo

# Get start/end dates from arguments or use defaults
START_DATE="${1:-2024-01-01}"
END_DATE="${2:-2024-01-06}"

echo "Running pipeline: $START_DATE to $END_DATE"
echo

# Run the pipeline in Docker
docker compose run --rm pipeline python pipeline/pipeline_historical.py \
    --start-date "$START_DATE" \
    --end-date "$END_DATE"

echo
echo "=========================================="
echo "Pipeline execution complete. Syncing files..."
echo "=========================================="
echo

# Sync parquet files from Docker to local
bash tools/sync_parquet_files.sh

echo
echo "=========================================="
echo "READY: All files synced to local project"
echo "=========================================="
echo
echo "Updated files:"
echo "  bronze/transactions/date=*/data.parquet"
echo "  bronze/accounts/date=*/data.parquet"
echo "  silver/transactions/date=*/data.parquet"
echo "  silver/accounts/data.parquet"
echo "  gold/daily_summary/data.parquet"
echo "  gold/weekly_summary/data.parquet"
echo "  pipeline/run_log.parquet"
echo "  pipeline/control.parquet"
echo
