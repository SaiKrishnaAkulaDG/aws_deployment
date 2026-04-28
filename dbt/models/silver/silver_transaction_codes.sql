-- Silver Transaction Codes: Pass-through transformation from Bronze
-- Materialized as external Parquet at /app/silver/transaction_codes/data.parquet
-- INV-04: _pipeline_run_id is non-null (enforced via schema test)

{{ config(
    materialized='external',
    location='/app/silver/transaction_codes/data.parquet',
    file_format='parquet'
) }}

select distinct
    transaction_code,
    description,
    debit_credit_indicator,
    transaction_type,
    affects_balance,
    _pipeline_run_id,
    _ingested_at,
    _source_file
from read_parquet('/app/bronze/transaction_codes/date=*/data.parquet')
