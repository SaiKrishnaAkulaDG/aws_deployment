-- Silver Transactions: Validated and enriched transaction records from Bronze
--
-- PROMOTION LOGIC:
--   1. Read Bronze transactions for the specified date
--   2. Exclude records already in quarantine (deduplication guard)
--   3. Join with Silver Transaction Codes to get debit_credit_indicator
--   4. Apply sign to amount based on DR (positive) / CR (negative)
--   5. Flag account_id resolvability against Silver Accounts (unresolved = false, not quarantined)
--   6. Timestamp promotion with current_timestamp
--
-- PARTITIONING: date=YYYY-MM-DD (inherited from Bronze source date)
-- IDEMPOTENCY: Re-running same date produces identical results (external materialization overwrites)
-- DEDUPLICATION: transaction_id uniqueness enforced across all partitions (SIL-T-02)
--
-- AUDIT COLUMNS:
--   _signed_amount: Amount with sign (DR=+, CR=-) — used in Gold aggregations
--   _is_resolvable: False if account_id not in Silver Accounts — excluded from Gold until backfilled
--   _pipeline_run_id: Execution identifier (INV-04 — non-null, enforced by test)
--   _bronze_ingested_at: Carried from Bronze ingestion timestamp
--   _source_file: Carried from Bronze source filename
--   _promoted_at: UTC timestamp when record entered Silver layer
--
-- CONSTRAINTS: SIL-T-02 (unique tx_id), SIL-T-08 (resolvability), INV-04 (non-null run_id)

{{ config(
    materialized='external',
    location='/app/silver/transactions/date={{ var("date_var", "2024-01-01") }}/data.parquet',
    file_format='parquet'
) }}

with bronze_transactions as (
    select * from read_parquet('/app/bronze/transactions/date={{ var("date_var", "2024-01-01") }}/data.parquet')
),

silver_accounts as (
    select distinct account_id from read_parquet('/app/silver/accounts/data.parquet')
),

silver_transaction_codes as (
    select transaction_code, debit_credit_indicator from read_parquet('/app/silver/transaction_codes/data.parquet')
),

quarantine_transaction_ids as (
    select distinct transaction_id from read_parquet('/app/silver/quarantine/data.parquet')
    where record_type = 'TRANSACTION' and transaction_id is not null
),

-- Filter out quarantine records and join for sign assignment
valid_transactions as (
    select
        bt.transaction_id,
        bt.account_id,
        bt.transaction_date,
        bt.amount,
        bt.transaction_code,
        bt.merchant_name,
        bt.channel,
        stc.debit_credit_indicator,
        bt._pipeline_run_id,
        bt._ingested_at as _bronze_ingested_at,
        bt._source_file
    from bronze_transactions bt
    left join silver_transaction_codes stc on bt.transaction_code = stc.transaction_code
    where bt.transaction_id not in (select transaction_id from quarantine_transaction_ids)
),

-- Add sign assignment, resolvability flag, and promotion timestamp
signed_transactions as (
    select
        vt.transaction_id,
        vt.account_id,
        vt.transaction_date,
        vt.amount,
        vt.transaction_code,
        vt.merchant_name,
        vt.channel,
        vt.debit_credit_indicator,
        case
            when vt.debit_credit_indicator = 'DR' then try_cast(vt.amount as decimal)
            else -try_cast(vt.amount as decimal)
        end as _signed_amount,
        case
            when sa.account_id is not null then true
            else false
        end as _is_resolvable,
        vt._pipeline_run_id,
        vt._bronze_ingested_at,
        vt._source_file,
        current_timestamp as _promoted_at
    from valid_transactions vt
    left join silver_accounts sa on vt.account_id = sa.account_id
)

select
    transaction_id,
    account_id,
    transaction_date,
    amount,
    transaction_code,
    merchant_name,
    channel,
    debit_credit_indicator,
    _signed_amount,
    _is_resolvable,
    _pipeline_run_id,
    _bronze_ingested_at,
    _source_file,
    _promoted_at
from signed_transactions
