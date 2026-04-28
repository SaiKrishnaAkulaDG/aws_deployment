# Design Document: UNRESOLVABLE_ACCOUNT_ID Treatment

**Status:** ✅ Implemented in S3
**Location:** silver_transactions.sql (lines 66-69) and silver_quarantine.sql (comment line 7)
**Version:** 1.0

---

## Executive Summary

**UNRESOLVABLE_ACCOUNT_ID is the ONLY rejection condition that produces a Silver record rather than a quarantine record.**

A transaction with an unknown account is flagged as `_is_resolvable = false` in Silver, NOT rejected to quarantine. This reflects a deliberate design decision: an unknown account may be a timing issue (account delta not yet received) rather than a genuine data error.

---

## Design Rationale

### Why NOT Quarantine Unknown Accounts?

**1. Timing Issue vs Data Error**
- ✅ Expected: Account CSV arrives late, but transactions for it already received
- ❌ Not expected: Account never arrives in any form
- **Treatment**: Keep transaction with flag, not quarantine

**2. Self-Healing Pipeline**
```
Day 1: Transaction for account_id=999 arrives
  → Account CSV not yet available
  → Flagged: _is_resolvable = false
  → Written to silver_transactions (not quarantined)

Day 2: Account CSV for account_id=999 arrives
  → Silver accounts layer updated
  → Gold layer can now include account_id=999
  → No backfill needed (data already in Silver)
```

**3. Backfill vs Hard Rejection**
- ✅ Soft flag (_is_resolvable=false): Requires backfill pipeline to resolve
- ❌ Hard quarantine: Requires manual correction and re-ingestion
- **Philosophy**: Give data a chance; mark as suspicious but keep it

---

## Implementation

### Code Location 1: silver_transactions.sql (Lines 66-69)

```sql
-- Add sign assignment, resolvability flag, and promotion timestamp
signed_transactions as (
    select
        ...
        case
            when sa.account_id is not null then true
            else false
        end as _is_resolvable,  -- ← Flag unknown accounts
        ...
    from valid_transactions vt
    left join silver_accounts sa on vt.account_id = sa.account_id
)
```

**Semantics:**
- `LEFT JOIN` to silver_accounts ensures all transactions kept
- If account_id not in silver_accounts → _is_resolvable = false
- If account_id in silver_accounts → _is_resolvable = true

### Code Location 2: silver_quarantine.sql (Line 7)

```sql
-- Note: UNRESOLVABLE_ACCOUNT_ID is NOT quarantined but flagged 
-- in silver_transactions with _is_resolvable=false
```

**Clarification:** This explicit comment documents the design decision so future maintainers understand why UNRESOLVABLE_ACCOUNT_ID is absent from quarantine rules.

---

## Rejection Rules Comparison

### What GETS Quarantined (Hard Rejects)

**Transactions:**
1. NULL_REQUIRED_FIELD: Missing transaction_id, account_id, amount, etc.
2. INVALID_AMOUNT: amount ≤ 0 or non-numeric
3. DUPLICATE_TRANSACTION_ID: Same ID appears twice
4. INVALID_TRANSACTION_CODE: Code not in reference table
5. INVALID_CHANNEL: Not in ('ONLINE', 'IN_STORE')

**Accounts:**
1. NULL_REQUIRED_FIELD: Missing account_id, status, limits, dates
2. INVALID_ACCOUNT_STATUS: Not in ('ACTIVE', 'SUSPENDED', 'CLOSED')

### What DOESN'T Get Quarantined (Soft Flags)

**UNRESOLVABLE_ACCOUNT_ID:**
- account_id exists AND is not null AND is valid
- BUT account_id not found in silver_accounts
- **Action**: Write to silver_transactions with `_is_resolvable=false`
- **Gold Impact**: Excluded from aggregations (filter WHERE _is_resolvable=true)

---

## Data Flow Diagrams

### Normal Path (Resolvable Account)

```
Bronze Transaction
  ├─ account_id = 123
  └─ Valid (not null, not duplicate, valid code, valid channel)
       ↓
Silver Accounts (has account_id 123)
       ↓
silver_transactions
  └─ _is_resolvable = true
       ↓
Gold Layer
  └─ Included in aggregations
```

### Unresolvable Path (Unknown Account)

```
Bronze Transaction
  ├─ account_id = 999
  └─ Valid (not null, not duplicate, valid code, valid channel)
       ↓
Silver Accounts (NO account_id 999)
       ↓
silver_transactions
  └─ _is_resolvable = false  ← FLAGGED, not quarantined
       ↓
Gold Layer
  └─ EXCLUDED (WHERE _is_resolvable = true filters it out)
       ↓
Backfill Pipeline (Future - S5+)
  └─ Handles late-arriving accounts and re-processes Gold
```

### Hard Reject Path (Invalid Transaction)

```
Bronze Transaction
  ├─ amount = -50 (invalid)
  └─ OR channel = 'INVALID'
  └─ OR amount is null
       ↓
silver_quarantine
  └─ _rejection_reason = 'INVALID_AMOUNT' or 'INVALID_CHANNEL'
       ↓
NOT in silver_transactions (excluded by quarantine join)
       ↓
NOT in gold layer (never reaches aggregations)
       ↓
Manual Review Required (data correction, re-ingest)
```

---

## Session 5 Implications (Gold Layer)

### Gold Layer Filtering

All Gold models must filter unresolvable transactions:

```sql
-- gold_daily_summary.sql
SELECT
    transaction_date,
    SUM(_signed_amount) as total,
    COUNT(*) as count,
    ...
FROM {{ ref('silver_transactions') }}
WHERE _is_resolvable = true  -- ← Exclude unresolvable
GROUP BY transaction_date
```

### Impact on Results

**Example with unresolvable accounts:**

```
Bronze Transactions (all dates): 1000 rows
  ├─ 950 rows: resolvable (account exists)
  └─ 50 rows: unresolvable (account_id not found)

Silver Transactions: 1000 rows
  ├─ 950 rows: _is_resolvable = true
  └─ 50 rows: _is_resolvable = false

Gold Daily Summary: 950 rows
  └─ Only resolvable transactions aggregated
```

**Reporting:**
- Management sees Gold totals: 950 transactions
- Analysts see Silver: "but 50 more exist, unresolvable"
- Backfill pipeline: Resolves the 50 when accounts arrive

---

## Session 5+ Future Extension: Backfill Pipeline

### When to Run Backfill

```
Trigger: New accounts arrive that match unresolvable account_ids

Process:
1. Query: SELECT DISTINCT account_id 
         FROM silver_transactions 
         WHERE _is_resolvable = false

2. Check: Do these account_ids now exist in silver_accounts?

3. If yes:
   a. Mark those transactions as _is_resolvable = true (update Silver)
   b. Re-run Gold aggregations for affected dates
   c. Gold totals increase to include newly-resolvable transactions

4. If no:
   a. Keep flagged, wait for accounts to arrive
   b. Generate report: "X unresolvable accounts still waiting"
```

### Backfill Implementation (Out of Scope for S1-S4)

```python
# Pseudo-code for future backfill_resolver.py
def resolve_unresolvable_transactions(app_dir, run_id):
    """
    Find transactions with unresolvable accounts that are now resolvable.
    Update Silver and re-compute Gold for affected dates.
    """
    # Find unresolvable transactions
    unresolvable_df = query_silver(
        "SELECT DISTINCT account_id FROM silver_transactions WHERE _is_resolvable = false"
    )
    
    # Check if accounts now exist
    silver_accounts = query_silver("SELECT account_id FROM silver_accounts")
    now_resolvable = unresolvable_df[unresolvable_df['account_id'].isin(silver_accounts)]
    
    if len(now_resolvable) > 0:
        # Update Silver: mark these transactions as resolvable
        # Re-run Gold for affected dates
        # Log backfill run
        print(f"Resolved {len(now_resolvable)} previously unresolvable transactions")
    else:
        print("No newly-resolvable transactions found")
```

---

## Testing Strategy

### Unit Test: Resolvable Account

```python
# Test that _is_resolvable=true when account exists
result = run_dbt_model("silver_transactions", vars={"date_var": "2024-01-01"})
resolvable_count = query(
    "SELECT COUNT(*) FROM result WHERE _is_resolvable = true"
)
assert resolvable_count > 0
```

### Unit Test: Unresolvable Account

```python
# Insert transaction with unknown account_id
bronze_transactions.insert(
    transaction_id=9999,
    account_id=999_999,  # Doesn't exist in accounts
    amount=100
)

result = run_dbt_model("silver_transactions", ...)
unresolvable = query(
    "SELECT * FROM result WHERE account_id = 999999"
)
assert unresolvable[0]['_is_resolvable'] == False
assert unresolvable[0]['transaction_id'] == 9999  # Still present
```

### Integration Test: Gold Filtering

```python
# Verify Gold layer excludes unresolvable
silver_count = query("SELECT COUNT(*) FROM silver_transactions")
gold_count = query("SELECT COUNT(*) FROM gold_daily_summary")

# Should have fewer or equal rows in Gold
assert gold_count <= silver_count

# Check that unresolvable is filtered
unresolvable = query("SELECT COUNT(*) FROM silver_transactions WHERE _is_resolvable = false")
if unresolvable > 0:
    assert gold_count == (silver_count - unresolvable)
```

---

## Documentation for Data Analysts

### Q: Why does Silver have more transactions than Gold?

**A:** Unresolvable transactions are in Silver but excluded from Gold.

**Example:**
```
Silver Transactions: 1000 rows
  ├─ 950 rows with _is_resolvable = true
  └─ 50 rows with _is_resolvable = false (account not found)

Gold Daily Summary: 950 rows (only resolvable)

Difference: 50 rows with unknown accounts
```

### Q: What do I do about unresolvable transactions?

**A:** Monitor and wait. These are likely late-arriving accounts.

**Action Plan:**
1. **Now**: Track which account_ids are unresolvable
2. **Wait**: For accounts CSV to include these IDs
3. **Later**: Backfill process auto-resolves when accounts arrive
4. **Report**: Any account_ids that never arrive (possible data error)

### Q: Why not just quarantine them?

**A:** Quarantine is for errors that need manual fixing. Unresolvable accounts are timing issues that may self-resolve.

**Philosophy:**
- ✅ Quarantine: amount=0, duplicate IDs, invalid codes → requires action
- ⚠️ Flag: account not found → might arrive tomorrow

---

## Audit Trail

| Session | Decision | Evidence |
|---------|----------|----------|
| S3 | UNRESOLVABLE_ACCOUNT_ID NOT quarantined | silver_transactions.sql line 66-69 |
| S3 | Flagged with _is_resolvable = false | LEFT JOIN to silver_accounts |
| S3 | Design documented | silver_quarantine.sql comment line 7 |
| S5+ | Gold filters WHERE _is_resolvable = true | Planned in gold_builder.py |

---

## Summary

**UNRESOLVABLE_ACCOUNT_ID Treatment:**

| Aspect | Implementation |
|--------|-----------------|
| Detection | `LEFT JOIN silver_accounts` in silver_transactions |
| Flag | `_is_resolvable = false` |
| Quarantine? | ❌ No — kept in Silver |
| Gold Impact | 🚫 Excluded from aggregations |
| Resolution | ⏳ Backfill pipeline (future) |
| Root Cause | Timing issue (late-arriving account) |
| Risk Level | 🟡 Medium (known issue, monitored) |

This design allows the pipeline to be resilient to delays in account data while maintaining data quality and auditability.
