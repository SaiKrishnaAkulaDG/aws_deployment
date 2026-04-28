# Credit Card Transactions Lake

A Medallion architecture pipeline (Bronze → Silver → Gold) for daily credit card transaction CSV ingestion, quality enforcement, and auditable aggregation.

## Methodology

- **PBVI:** v4.3
- **BCE:** v1.7

## Entry Points

### Historical Pipeline
Process a date range of transaction files (e.g., 2024-01-01 to 2024-01-06):

```bash
docker compose run --rm pipeline python pipeline/pipeline_historical.py \
  --start-date 2024-01-01 --end-date 2024-01-06
```

### Incremental Pipeline
Process the next date after the current watermark:

```bash
docker compose run --rm pipeline python pipeline/pipeline_incremental.py
```

## Architecture Layers

- **Bronze:** Raw CSV ingestion with row count verification and idempotency
- **Silver:** dbt-based transformation, validation, and deduplication
- **Gold:** dbt-based aggregation and summary tables
- **Quarantine:** Invalid records with rejection reasons

## Audit Trail

Every record carries a `_pipeline_run_id` (UUIDv4) linking it to a run log entry, enabling full traceability from Gold aggregations back to source files.

## Data Directory Structure

```
source/          # Read-only source CSV files
pipeline/        # Run log, control table, entry point scripts
bronze/          # Raw ingested data by date partition
silver/          # Transformed, validated data
gold/            # Aggregated summary tables
quarantine/      # Rejected records with reasons
```

## Stack

- **Python:** 3.11
- **dbt-core:** 1.7.x
- **dbt-duckdb:** 1.7.x (DuckDB adapter)
- **DuckDB:** Embedded (no separate server)
- **Storage:** Parquet files on local filesystem
- **Orchestration:** Docker Compose (all services local)

## Running Verification

```bash
docker compose build && \
docker compose run --rm pipeline python -c "import duckdb; print('duckdb ok')" && \
docker compose run --rm pipeline dbt debug --project-dir /app/dbt --profiles-dir /app/dbt && \
bash tools/challenge.sh --check
```
# aws_deployment
