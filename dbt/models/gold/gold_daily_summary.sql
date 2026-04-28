-- Gold — Daily Transaction Summary
--
-- One aggregated record per calendar day (transaction_date) from resolvable Silver transactions.
-- Provides comprehensive daily metrics: transaction counts, amounts, channel breakdown, and type analysis.
--
-- AGGREGATION LOGIC:
--   1. Filter Silver transactions where _is_resolvable = true
--   2. Group by transaction_date to create one record per day
--   3. Compute: total count, total signed amount, channel breakdown (ONLINE vs IN_STORE)
--   4. Compute: transaction type breakdown (count & sum per type) as STRUCT
--   5. Track: _pipeline_run_id, _computed_at timestamp, source period (min/max transaction_date)
--
-- CONSTRAINTS: GOLD-D-01 (unique transaction_date), INV-04 (non-null _pipeline_run_id)
-- MATERIALIZATION: external (non-partitioned, overwrites on re-run)
--
{{
  config(
    materialized='external',
    location='/app/gold/daily_summary/data.parquet'
  )
}}

with filtered_transactions as (
  select
    st.transaction_date,
    st.channel,
    st._signed_amount,
    st._pipeline_run_id,
    stc.transaction_type
  from read_parquet('/app/silver/transactions/date=*/data.parquet') st
  left join read_parquet('/app/silver/transaction_codes/data.parquet') stc
    on st.transaction_code = stc.transaction_code
  where st._is_resolvable = true
)

select
  ft.transaction_date,
  count(*) as total_transactions,
  sum(ft._signed_amount) as total_signed_amount,
  sum(case when ft.channel = 'ONLINE' then 1 else 0 end) as online_transactions,
  sum(case when ft.channel = 'IN_STORE' then 1 else 0 end) as instore_transactions,
  json_object(
    'PURCHASE', json_object('count', sum(case when ft.transaction_type = 'PURCHASE' then 1 else 0 end), 'sum', sum(case when ft.transaction_type = 'PURCHASE' then ft._signed_amount else 0 end)),
    'PAYMENT', json_object('count', sum(case when ft.transaction_type = 'PAYMENT' then 1 else 0 end), 'sum', sum(case when ft.transaction_type = 'PAYMENT' then ft._signed_amount else 0 end)),
    'FEE', json_object('count', sum(case when ft.transaction_type = 'FEE' then 1 else 0 end), 'sum', sum(case when ft.transaction_type = 'FEE' then ft._signed_amount else 0 end)),
    'INTEREST', json_object('count', sum(case when ft.transaction_type = 'INTEREST' then 1 else 0 end), 'sum', sum(case when ft.transaction_type = 'INTEREST' then ft._signed_amount else 0 end)),
    'REFUND', json_object('count', sum(case when ft.transaction_type = 'REFUND' then 1 else 0 end), 'sum', sum(case when ft.transaction_type = 'REFUND' then ft._signed_amount else 0 end))
  ) as transactions_by_type,
  current_timestamp as _computed_at,
  max(ft._pipeline_run_id) as _pipeline_run_id,
  min(ft.transaction_date) as _source_period_start,
  max(ft.transaction_date) as _source_period_end
from filtered_transactions ft
group by ft.transaction_date
order by ft.transaction_date
