#!/bin/bash
# force_sync_parquet.sh — FORCE copy parquet files from Docker container to local filesystem
# Solves Windows bind mount sync issues where file modifications don't reflect locally

set -e

CONTAINER_NAME="cc_pipeline"
LOCAL_PROJECT_DIR="."

echo "=========================================="
echo "FORCE SYNC: Copying Parquet Files"
echo "From Docker to Local Filesystem"
echo "=========================================="
echo

# Start container if not running
if ! docker ps | grep -q "$CONTAINER_NAME"; then
    echo "[Starting Container...]"
    docker compose up -d
    sleep 3
fi

echo "[Copying Bronze Layer...]"
# Delete local and recopy from Docker
rm -rf "$LOCAL_PROJECT_DIR/bronze/transactions" "$LOCAL_PROJECT_DIR/bronze/accounts" "$LOCAL_PROJECT_DIR/bronze/transaction_codes"
docker cp "$CONTAINER_NAME:/app/bronze/transactions" "$LOCAL_PROJECT_DIR/bronze/"
docker cp "$CONTAINER_NAME:/app/bronze/accounts" "$LOCAL_PROJECT_DIR/bronze/"
docker cp "$CONTAINER_NAME:/app/bronze/transaction_codes" "$LOCAL_PROJECT_DIR/bronze/"

echo "[Copying Silver Layer...]"
rm -rf "$LOCAL_PROJECT_DIR/silver/transactions" "$LOCAL_PROJECT_DIR/silver/accounts" "$LOCAL_PROJECT_DIR/silver/transaction_codes"
docker cp "$CONTAINER_NAME:/app/silver/transactions" "$LOCAL_PROJECT_DIR/silver/"
docker cp "$CONTAINER_NAME:/app/silver/accounts" "$LOCAL_PROJECT_DIR/silver/"
docker cp "$CONTAINER_NAME:/app/silver/transaction_codes" "$LOCAL_PROJECT_DIR/silver/"

echo "[Copying Quarantine...]"
rm -rf "$LOCAL_PROJECT_DIR/quarantine"
docker cp "$CONTAINER_NAME:/app/quarantine" "$LOCAL_PROJECT_DIR/"

echo "[Copying Gold Layer...]"
rm -rf "$LOCAL_PROJECT_DIR/gold/daily_summary" "$LOCAL_PROJECT_DIR/gold/weekly_summary"
docker cp "$CONTAINER_NAME:/app/gold/daily_summary" "$LOCAL_PROJECT_DIR/gold/"
docker cp "$CONTAINER_NAME:/app/gold/weekly_summary" "$LOCAL_PROJECT_DIR/gold/"

echo "[Copying Pipeline Files...]"
docker cp "$CONTAINER_NAME:/app/pipeline/run_log.parquet" "$LOCAL_PROJECT_DIR/pipeline/"
docker cp "$CONTAINER_NAME:/app/pipeline/control.parquet" "$LOCAL_PROJECT_DIR/pipeline/"

echo
echo "=========================================="
echo "VERIFICATION: Check file modification times"
echo "=========================================="
echo

ls -lh "$LOCAL_PROJECT_DIR/gold/daily_summary/data.parquet" 2>/dev/null && echo "Gold Daily: UPDATED" || echo "Gold Daily: MISSING"
ls -lh "$LOCAL_PROJECT_DIR/silver/transactions/date=2024-01-01/data.parquet" 2>/dev/null && echo "Silver TX: UPDATED" || echo "Silver TX: MISSING"

echo
echo "=========================================="
echo "SUCCESS: All files FORCE SYNCED"
echo "File Explorer should now show TODAY'S DATE"
echo "Parquet Viewer will see correct data"
echo "=========================================="
echo
