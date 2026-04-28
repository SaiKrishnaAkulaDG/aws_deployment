-- Gold — Weekly Account Transaction Aggregates
--
-- One record per account per ISO week (Monday to Sunday).
-- Only includes accounts with at least one resolvable transaction in the week.
-- Aggregates transactions by type: PURCHASE (count & avg), PAYMENT/FEE/INTEREST (sums).
--
-- AGGREGATION LOGIC:
--   1. Filter Silver transactions where _is_resolvable = true
--   2. Group by account_id and ISO week (Monday = week_start)
--   3. Compute: PURCHASE count & average amount
--   4. Compute: PAYMENT, FEE, INTEREST amounts (sums by type)
--   5. Join to Silver Accounts to get closing_balance (current account balance)
--   6. Only include account+week combinations with resolvable transactions
--
-- CONSTRAINTS: GOLD-W-01 (unique account+week), GOLD-W-05 (closing_balance non-null via INNER JOIN)
-- MATERIALIZATION: external (non-partitioned, overwrites on re-run)
--
{{
  config(
    materialized='external',
    location='/app/gold/weekly_account_summary/data.parquet'
  )
}}

with filtered_transactions as (
  select
    st.account_id,
    st.transaction_date,
    stc.transaction_type,
    st._signed_amount,
    st._pipeline_run_id
  from read_parquet('/app/silver/transactions/date=*/data.parquet') st
  left join read_parquet('/app/silver/transaction_codes/data.parquet') stc
    on st.transaction_code = stc.transaction_code
  where st._is_resolvable = true
),

weekly_grouped as (
  select
    account_id,
    date_trunc('week', cast(transaction_date as date)) as week_start_date,
    cast(date_add(date_trunc('week', cast(transaction_date as date)), interval 6 day) as date) as week_end_date,
    sum(case when transaction_type = 'PURCHASE' then 1 else 0 end) as total_purchases,
    avg(case when transaction_type = 'PURCHASE' then _signed_amount else null end) as avg_purchase_amount,
    sum(case when transaction_type = 'PAYMENT' then _signed_amount else 0 end) as total_payments,
    sum(case when transaction_type = 'FEE' then _signed_amount else 0 end) as total_fees,
    sum(case when transaction_type = 'INTEREST' then _signed_amount else 0 end) as total_interest,
    max(_pipeline_run_id) as _pipeline_run_id
  from filtered_transactions
  group by account_id, date_trunc('week', cast(transaction_date as date))
)

select
  wg.week_start_date,
  wg.week_end_date,
  wg.account_id,
  wg.total_purchases,
  wg.avg_purchase_amount,
  wg.total_payments,
  wg.total_fees,
  wg.total_interest,
  sa.current_balance as closing_balance,
  current_timestamp as _computed_at,
  wg._pipeline_run_id
from weekly_grouped wg
inner join read_parquet('/app/silver/accounts/data.parquet') sa on wg.account_id = sa.account_id
order by wg.week_start_date, wg.account_id
