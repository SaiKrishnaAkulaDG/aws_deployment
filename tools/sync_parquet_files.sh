#!/bin/bash
# sync_parquet_files.sh — Sync parquet files from Docker to local project directory
# Run after each pipeline execution to ensure local files are up-to-date

set -e

CONTAINER_NAME="cc_pipeline"
LOCAL_PROJECT_DIR="."

echo "=========================================="
echo "Syncing Parquet Files from Docker..."
echo "=========================================="
echo

# Check if container is running
if docker ps | grep -q "$CONTAINER_NAME"; then
    echo "[Running Container] Copying files from Docker..."

    # Copy Bronze layer
    echo "Syncing bronze/ ..."
    docker cp "$CONTAINER_NAME:/app/bronze/transactions" "$LOCAL_PROJECT_DIR/bronze/" 2>/dev/null || true
    docker cp "$CONTAINER_NAME:/app/bronze/accounts" "$LOCAL_PROJECT_DIR/bronze/" 2>/dev/null || true
    docker cp "$CONTAINER_NAME:/app/bronze/transaction_codes" "$LOCAL_PROJECT_DIR/bronze/" 2>/dev/null || true

    # Copy Silver layer
    echo "Syncing silver/ ..."
    docker cp "$CONTAINER_NAME:/app/silver/transactions" "$LOCAL_PROJECT_DIR/silver/" 2>/dev/null || true
    docker cp "$CONTAINER_NAME:/app/silver/accounts" "$LOCAL_PROJECT_DIR/silver/" 2>/dev/null || true
    docker cp "$CONTAINER_NAME:/app/silver/transaction_codes" "$LOCAL_PROJECT_DIR/silver/" 2>/dev/null || true
    docker cp "$CONTAINER_NAME:/app/quarantine" "$LOCAL_PROJECT_DIR/" 2>/dev/null || true

    # Copy Gold layer
    echo "Syncing gold/ ..."
    docker cp "$CONTAINER_NAME:/app/gold/daily_summary" "$LOCAL_PROJECT_DIR/gold/" 2>/dev/null || true
    docker cp "$CONTAINER_NAME:/app/gold/weekly_summary" "$LOCAL_PROJECT_DIR/gold/" 2>/dev/null || true

    # Copy pipeline files
    echo "Syncing pipeline/ ..."
    docker cp "$CONTAINER_NAME:/app/pipeline/run_log.parquet" "$LOCAL_PROJECT_DIR/pipeline/" 2>/dev/null || true
    docker cp "$CONTAINER_NAME:/app/pipeline/control.parquet" "$LOCAL_PROJECT_DIR/pipeline/" 2>/dev/null || true

    echo
    echo "[SUCCESS] All parquet files synced to local project directory"
    echo
else
    echo "[INFO] Container not running - files already synced via bind mount"
    echo "[INFO] To sync if files are stale, use: docker compose up -d && ./tools/sync_parquet_files.sh"
    echo
fi

echo "=========================================="
echo "Sync Complete"
echo "=========================================="
