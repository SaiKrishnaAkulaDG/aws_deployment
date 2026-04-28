-- Silver Quarantine: Transaction and Account rejection rules
-- Transaction rules: NULL_REQUIRED_FIELD, INVALID_AMOUNT, DUPLICATE_TRANSACTION_ID, INVALID_TRANSACTION_CODE, INVALID_CHANNEL
-- Account rules: NULL_REQUIRED_FIELD, INVALID_ACCOUNT_STATUS
-- Retains ALL original Bronze columns unchanged (SIL-Q-03)
-- INV-04: _pipeline_run_id is non-null (enforced via schema test)
-- _rejected_at: timestamp when record was rejected
-- Note: UNRESOLVABLE_ACCOUNT_ID is NOT quarantined but flagged in silver_transactions with _is_resolvable=false

{{ config(
    materialized='external',
    location='/app/silver/quarantine/data.parquet',
    file_format='parquet'
) }}

with bronze_transactions as (
    select
        *,
        'TRANSACTION' as record_type
    from read_parquet('/app/bronze/transactions/date=*/data.parquet')
),

bronze_accounts as (
    select
        *,
        'ACCOUNT' as record_type
    from read_parquet('/app/bronze/accounts/date=*/data.parquet')
),

silver_transaction_codes as (
    select distinct transaction_code from read_parquet('/app/silver/transaction_codes/data.parquet')
),

-- ===== TRANSACTION REJECTION RULES =====

-- Transaction Rule 1: NULL_REQUIRED_FIELD
txn_null_required_fields as (
    select *
    from bronze_transactions
    where transaction_id is null
        or transaction_id = ''
        or account_id is null
        or account_id = ''
        or transaction_date is null
        or transaction_date = ''
        or amount is null
        or transaction_code is null
        or transaction_code = ''
        or channel is null
        or channel = ''
),

-- Transaction Rule 2: INVALID_AMOUNT (amount <= 0 or non-numeric)
txn_invalid_amount as (
    select *
    from bronze_transactions
    where transaction_id not in (select coalesce(transaction_id, '') from txn_null_required_fields)
        and amount is not null
        and (try_cast(amount as decimal) <= 0 or try_cast(amount as decimal) is null)
),

-- Transaction Rule 3: DUPLICATE_TRANSACTION_ID
txn_duplicate_ids as (
    select transaction_id
    from bronze_transactions
    where transaction_id is not null and transaction_id != ''
    group by transaction_id
    having count(*) > 1
),

txn_duplicate_transactions as (
    select *
    from bronze_transactions
    where transaction_id not in (select coalesce(transaction_id, '') from txn_null_required_fields)
        and (try_cast(amount as decimal) > 0 or amount is null)
        and transaction_id in (select transaction_id from txn_duplicate_ids)
),

-- Transaction Rule 4: INVALID_TRANSACTION_CODE
txn_invalid_transaction_code as (
    select *
    from bronze_transactions
    where transaction_id not in (select coalesce(transaction_id, '') from txn_null_required_fields)
        and (try_cast(amount as decimal) > 0 or amount is null)
        and transaction_id not in (select transaction_id from txn_duplicate_ids)
        and transaction_code not in (select transaction_code from silver_transaction_codes)
),

-- Transaction Rule 5: INVALID_CHANNEL (must be ONLINE or IN_STORE)
txn_invalid_channel as (
    select *
    from bronze_transactions
    where transaction_id not in (select coalesce(transaction_id, '') from txn_null_required_fields)
        and (try_cast(amount as decimal) > 0 or amount is null)
        and transaction_id not in (select transaction_id from txn_duplicate_ids)
        and transaction_code in (select transaction_code from silver_transaction_codes)
        and channel not in ('ONLINE', 'IN_STORE')
),

-- ===== ACCOUNT REJECTION RULES =====

-- Account Rule 1: NULL_REQUIRED_FIELD
acct_null_required_fields as (
    select *
    from bronze_accounts
    where account_id is null
        or account_id = ''
        or open_date is null
        or open_date = ''
        or credit_limit is null
        or current_balance is null
        or billing_cycle_start is null
        or billing_cycle_end is null
        or account_status is null
        or account_status = ''
),

-- Account Rule 2: INVALID_ACCOUNT_STATUS (must be ACTIVE, SUSPENDED, or CLOSED)
acct_invalid_account_status as (
    select *
    from bronze_accounts
    where account_id not in (select coalesce(account_id, '') from acct_null_required_fields)
        and account_status not in ('ACTIVE', 'SUSPENDED', 'CLOSED')
),

-- ===== COMBINE ALL REJECTIONS =====

txn_rejections_combined as (
    select *, 'NULL_REQUIRED_FIELD' as _rejection_reason from txn_null_required_fields
    union all
    select *, 'INVALID_AMOUNT' as _rejection_reason from txn_invalid_amount
    union all
    select *, 'DUPLICATE_TRANSACTION_ID' as _rejection_reason from txn_duplicate_transactions
    union all
    select *, 'INVALID_TRANSACTION_CODE' as _rejection_reason from txn_invalid_transaction_code
    union all
    select *, 'INVALID_CHANNEL' as _rejection_reason from txn_invalid_channel
),

acct_rejections_combined as (
    select *, 'NULL_REQUIRED_FIELD' as _rejection_reason from acct_null_required_fields
    union all
    select *, 'INVALID_ACCOUNT_STATUS' as _rejection_reason from acct_invalid_account_status
),

-- Deduplicate transactions by transaction_id, keeping first rejection reason
txn_rejections_deduped as (
    select
        *,
        row_number() over (partition by transaction_id order by _rejection_reason) as rn
    from txn_rejections_combined
),

-- Deduplicate accounts by account_id, keeping first rejection reason
acct_rejections_deduped as (
    select
        *,
        row_number() over (partition by account_id order by _rejection_reason) as rn
    from acct_rejections_combined
),

-- Final transaction quarantine records with nulls for account columns
txn_final as (
    select
        transaction_id,
        account_id,
        transaction_date,
        amount,
        transaction_code,
        merchant_name,
        channel,
        null as customer_name,
        null as account_status,
        null as credit_limit,
        null as current_balance,
        null as open_date,
        null as billing_cycle_start,
        null as billing_cycle_end,
        _pipeline_run_id,
        _ingested_at,
        _source_file,
        _rejection_reason,
        current_timestamp as _rejected_at,
        record_type
    from txn_rejections_deduped
    where rn = 1
),

-- Final account quarantine records with nulls for transaction columns
acct_final as (
    select
        null as transaction_id,
        account_id,
        null as transaction_date,
        null as amount,
        null as transaction_code,
        null as merchant_name,
        null as channel,
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
        _rejection_reason,
        current_timestamp as _rejected_at,
        record_type
    from acct_rejections_deduped
    where rn = 1
)

select
    transaction_id,
    account_id,
    transaction_date,
    amount,
    transaction_code,
    merchant_name,
    channel,
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
    _rejection_reason,
    _rejected_at,
    record_type
from txn_final

union all

select
    transaction_id,
    account_id,
    transaction_date,
    amount,
    transaction_code,
    merchant_name,
    channel,
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
    _rejection_reason,
    _rejected_at,
    record_type
from acct_final
