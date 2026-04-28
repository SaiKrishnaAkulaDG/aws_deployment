-- Silver Accounts: Latest account record per account_id (SIL-A-01)
-- Deduplicates Bronze accounts by selecting rank 1 from ROW_NUMBER() ordered by _ingested_at DESC
-- INV-04: _pipeline_run_id is non-null (enforced via schema test)
-- Metadata: _source_file, _bronze_ingested_at (Bronze timestamp), _record_valid_from (Silver timestamp)

{{ config(
    materialized='external',
    location='/app/silver/accounts/data.parquet',
    file_format='parquet'
) }}

with ranked_accounts as (
    select
        account_id,
        customer_name,
        account_status,
        credit_limit,
        current_balance,
        open_date,
        billing_cycle_start,
        billing_cycle_end,
        _pipeline_run_id,
        _ingested_at,
        _source_file,
        row_number() over (partition by account_id order by _ingested_at desc) as rn
    from read_parquet('/app/bronze/accounts/date=*/data.parquet')
)

select
    account_id,
    customer_name,
    account_status,
    credit_limit,
    current_balance,
    open_date,
    billing_cycle_start,
    billing_cycle_end,
    _pipeline_run_id,
    _source_file,
    _ingested_at as _bronze_ingested_at,
    current_timestamp as _record_valid_from
from ranked_accounts
where rn = 1
