# INVARIANTS.md — Credit Card Transactions Lake

## Changelog
| Version | Date | Author | Change |
|---|---|---|---|
| v1.0 | 2026-04-10 | Krishna | Greenfield — Initial. 48 invariants across 11 groups. |

---

## Authorship and Sign-Off

**Engineer:** Krishna
**Date:** 2026-04-10
**Status:** SIGNED OFF — ready for Phase 3

All invariants in this document have been:
- Authored by the engineer (authorship rule observed)
- Challenged against all five tests: goal vs. constraint, enforcement scope,
  bundling, coverage, harm and detectability, complexity accumulation
- Checked for sufficiency against ARCHITECTURE.md section by section
- Checked against the Step 0 data touch point map (33 touch points)
- Open questions OQ-1, OQ-2, OQ-3 resolved before sign-off

---

## Scope Classification Key

**GLOBAL:** Applies to every task in the system regardless of feature area.
Embedded in Claude.md Section 2.

**TASK-SCOPED:** Applies only when specific components or features are touched.
Embedded inline in the CC prompt of each relevant task in EXECUTION_PLAN.md.

---

## Implementation Guidance Register

The following were proposed as invariants but reclassified. They will be
embedded in task CC prompts in EXECUTION_PLAN.md at Phase 3.

| Original ID | Reason | Destination |
|---|---|---|
| INV-03 | Duplicate of INV-02 | Dropped |
| INV-07 | Detectable through normal execution | bronze_loader.py, silver_promoter.py, gold_builder.py, pipeline.py task prompts |
| INV-10 | Path convention — violation immediately visible | bronze_loader.py task prompt |
| INV-12 | Verification command for INV-08, not invariant | bronze_loader.py verification command |
| SIL-T-06 | Detectable through code review | silver_promoter.py task prompt |
| SIL-Q-03 | Detectable through Bronze comparison | silver_promoter.py quarantine write task prompt |
| SIL-Q-04 | Out of scope — no promotion path exists | ARCHITECTURE.md Section 9 |
| SIL-REF-02 | No update path in incremental run | silver_promoter.py incremental task prompt |
| RL-03 | Field-level recording specification | run_logger.py task prompt |
| RL-04 | Field-level constraint — detectable immediately | run_logger.py task prompt |
| RL-05a | Detectable immediately through query | run_logger.py task prompt |
| Decision 4 atomic rename | Deployment constraint — detectable | Docker Compose config task prompt |
| S1B-schema-evolution | Fixed schema for this exercise | ARCHITECTURE.md Section 7 |

---

## Group 1 — Pipeline Operational Invariants

---

### INV-01a
**Condition:** Re-running the Bronze ingestion on the same source file must
produce identical Bronze partition row counts and content.

- **Category:** Operational
- **Scope:** TASK-SCOPED — bronze_loader.py
- **Why this matters:** Duplicate Bronze records inflate Silver row counts,
  break the SIL-T-01 mass conservation check, and produce inflated Gold
  aggregations with no error signal.
- **Enforcement points:**
  - bronze_loader.py — row count verification before ingestion decision;
    skip if partition exists and row counts match source CSV

---

### INV-01b
**Condition:** Re-running Silver promotion for the same date must produce
identical Silver and Quarantine partition row counts and content.

- **Category:** Operational
- **Scope:** TASK-SCOPED — silver_promoter.py
- **Why this matters:** Non-idempotent Silver promotion introduces duplicate
  transaction records or inconsistent Quarantine state, producing wrong Gold
  aggregations silently. Silver and Quarantine are recomputed atomically —
  they cannot be idempotent independently.
- **Enforcement points:**
  - silver_promoter.py — atomic overwrite strategy: delete existing partition,
    recompute from Bronze, write to temp path, atomic rename to replace
- **Verification advisory:** Two verification commands required in Phase 3 —
  one for Silver row count, one for Quarantine row count.

---

### INV-01d
**Condition:** Re-running Gold computation for the same date must produce
identical Gold output row counts and content.

- **Category:** Operational
- **Scope:** TASK-SCOPED — gold_builder.py
- **Why this matters:** Non-idempotent Gold computation produces wrong analyst
  outputs on rerun. Analysts acting on doubled aggregations make incorrect
  decisions with no visible data error.
- **Enforcement points:**
  - gold_builder.py — full recomputation and replace on each run (see GAP-INV-05)

---

### INV-02
**Condition:** The pipeline control watermark must advance only after Bronze,
Silver, and Gold all complete successfully for a given date. If any stage
fails, the watermark must not advance and the date must remain reprocessable.

- **Category:** Operational
- **Scope:** TASK-SCOPED — control_manager.py
- **Why this matters:** A watermark advancing on partial success marks a date
  as processed when Gold aggregations may be absent or incomplete. Subsequent
  incremental runs skip that date, leaving a permanent gap in Gold output.
- **Enforcement points:**
  - control_manager.py — watermark write is the final operation; executes
    only after all stage result objects return SUCCESS
  - pipeline.py — evaluates stage result objects before calling
    control_manager.py

---

### INV-06
**Condition:** Source files in source/ must never be modified or deleted by
the pipeline. They are read-only inputs.

- **Category:** Operational
- **Scope:** TASK-SCOPED — bronze_loader.py
- **Why this matters:** Modified or deleted source files destroy the ability
  to re-run the historical pipeline correctly. The reproducibility guarantee
  depends on source files remaining unchanged.
- **Enforcement points:**
  - bronze_loader.py — opens source CSV files in read-only mode; no write
    or delete path exists for source/ in any module

---

## Group 2 — Audit Trail and Traceability Invariants

---

### INV-04
**Condition:** Every record in Bronze, Silver, Quarantine, and Gold must carry
a non-null _pipeline_run_id.

- **Category:** Data Correctness
- **Scope:** GLOBAL — applies to every write in every layer
- **Why this matters:** A null _pipeline_run_id breaks the audit trail
  completely. An analyst cannot trace a Gold aggregate back to the pipeline
  run that produced it, the Silver records that fed it, or the Bronze source
  that originated it. The entire traceability guarantee collapses.
- **Enforcement points:**
  - bronze_loader.py — generates UUIDv4 run_id at pipeline start; adds
    _pipeline_run_id to every Bronze record written
  - silver_promoter.py — propagates run_id to every Silver and Quarantine
    record written
  - gold_builder.py — propagates run_id to every Gold record written

---

### INV-05a
**Condition:** For any _pipeline_run_id present in Bronze, Silver, or Gold,
a corresponding run log entry must exist with status = SUCCESS.

- **Category:** Data Correctness
- **Scope:** TASK-SCOPED — run_logger.py
- **Why this matters:** A run_id in a data layer with no SUCCESS run log entry
  means the data was produced by an unaudited run. An analyst tracing a
  suspicious Gold aggregate has no evidence to verify the producing run's
  behaviour.
- **Enforcement points:**
  - run_logger.py — records SUCCESS entry for every model after successful
    execution; pipeline.py passes structured result objects to run_logger.py

---

### INV-05b
**Condition:** For any pipeline invocation that produces no data writes
(no source file available for watermark + 1), all run log entries for that
invocation must carry status = SKIPPED. That run_id must not appear in any
data layer.

- **Category:** Data Correctness
- **Scope:** TASK-SCOPED — run_logger.py
- **Why this matters:** A SKIPPED run_id appearing in a data layer indicates
  data was written without a valid execution record — an audit trail violation.
  SKIPPED invocations must produce run log evidence without producing data.
- **Enforcement points:**
  - run_logger.py — writes SKIPPED entries for all models on no-op invocation
  - pipeline.py — exits without writing to any data layer on missing source
    file; passes SKIPPED result to run_logger.py

---

### RL-01a
**Condition:** Every pipeline run must append at least one entry to the run
log — one row per model per invocation.

- **Category:** Operational
- **Scope:** TASK-SCOPED — run_logger.py
- **Why this matters:** A pipeline invocation with no run log entry is
  unauditable. An analyst cannot verify what ran, what succeeded, or what
  failed. No run log entry means no audit trail for that invocation.
- **Enforcement points:**
  - run_logger.py — appends one row per model per invocation regardless of
    outcome; called by pipeline.py after each stage completes

---

### RL-01b
**Condition:** Existing run log entries must never be modified or overwritten
after being written. The run log is append-only.

- **Category:** Operational
- **Scope:** TASK-SCOPED — run_logger.py
- **Why this matters:** An overwritten run log entry destroys the audit trail
  for a prior run permanently. An analyst tracing a prior run's behaviour has
  no recourse. Partial failures are preserved intentionally — the run log is
  the only record of what went wrong.
- **Enforcement points:**
  - run_logger.py — appends to Parquet directly; no delete, truncate, or
    overwrite path exists in run_logger.py

---

### RL-02
**Condition:** Each run_id must uniquely identify a single pipeline invocation.
No two invocations may share the same run_id.

- **Category:** Data Correctness
- **Scope:** TASK-SCOPED — pipeline.py
- **Why this matters:** A non-unique run_id makes the audit chain ambiguous.
  An analyst joining Gold records to the run log on run_id cannot determine
  which invocation produced which records. INV-05a and INV-05b both depend
  on run_id uniqueness to be enforceable.
- **Enforcement points:**
  - pipeline.py — generates UUIDv4 at invocation start; UUID collision
    resistance satisfies this invariant by design (OQ-3 resolution)

---

### RL-05b
**Condition:** error_message on failure must never contain file paths,
credentials, or internal system details — only a sanitised description of
what failed.

- **Category:** Security
- **Scope:** TASK-SCOPED — run_logger.py
- **Why this matters:** File paths or credentials exposed in the run log
  constitute a security violation. The run log is queryable by analysts via
  DuckDB CLI — any sensitive content in error_message is accessible to all
  run log readers.
- **Enforcement points:**
  - run_logger.py — error_message populated from module result object;
    each module must sanitise error content before returning it
  - All modules — error handling must strip file paths, credentials, and
    internal detail before constructing error_message

---

## Group 3 — Bronze Layer Invariants

---

### INV-08
**Condition:** Bronze ingestion must preserve source data exactly as received,
including malformed records, null values, and duplicates. No filtering,
transformation, or enrichment beyond audit columns.

- **Category:** Data Correctness
- **Scope:** TASK-SCOPED — bronze_loader.py
- **Why this matters:** Filtering in Bronze destroys the immutable raw record.
  The Silver + Quarantine mass conservation check (SIL-T-01) depends on Bronze
  being a complete, unmodified copy of the source. Filtered Bronze makes
  SIL-T-01 unverifiable.
- **Enforcement points:**
  - bronze_loader.py — reads source CSV and writes to Parquet without any
    filtering, type coercion, or transformation beyond appending audit columns

---

### INV-09
**Condition:** Bronze partitions are immutable after initial write. Once
written, a partition must never be overwritten, modified, or deleted.
The only permitted exception is defined in S1B-03.

- **Category:** Data Correctness
- **Scope:** TASK-SCOPED — bronze_loader.py
- **Why this matters:** An overwritten Bronze partition destroys the
  immutable raw record permanently. The audit trail from Gold back to source
  CSV depends on Bronze being the unchanged original. After overwrite, this
  traceability is unrecoverable.
- **Enforcement points:**
  - bronze_loader.py — skip path (row count match) never deletes; delete
    path exists only for row count mismatch (S1B-03 exception)

---

### S1B-03
**Condition:** A Bronze partition may only be deleted and reprocessed if its
row count does not match the source CSV row count. A partition whose row count
matches its source file must never be deleted or reprocessed. This is the only
permitted exception to INV-09.

- **Category:** Data Correctness
- **Scope:** TASK-SCOPED — bronze_loader.py
- **Why this matters:** Deleting a complete, correct Bronze partition destroys
  valid immutable data permanently. This exception exists only to correct
  partial writes — a partition that exists but is incomplete (row count
  mismatch) must be corrected. A complete partition must never be disturbed.
- **Enforcement points:**
  - bronze_loader.py — row count check gates every delete decision; delete
    is only reachable if row count check returns mismatch

---

### S1B-schema
**Condition:** The schema of every source CSV file must exactly match the
expected schema for that entity — correct column names, data types, and
column order. Any deviation must cause bronze_loader.py to return FAILED
and must prevent any data from being written to Bronze for that file.

- **Category:** Data Correctness
- **Scope:** TASK-SCOPED — bronze_loader.py
- **Why this matters:** A schema mismatch produces silent data corruption.
  A shifted column maps the wrong field to the wrong name — amount loaded
  as transaction_code, transaction_date loaded as account_id. Silver then
  computes _signed_amount from the wrong value with no error signal. Silent
  corruption is worse than an explicit failure.
- **Enforcement points:**
  - bronze_loader.py — schema validation check before any ingestion; returns
    FAILED immediately on mismatch without writing any records to Bronze

---

### S1B-bronze-python
**Condition:** Bronze ingestion must be implemented exclusively in Python
using DuckDB directly. No dbt model may read from source CSV files or write
to Bronze partitions.

- **Category:** Data Correctness
- **Scope:** TASK-SCOPED — bronze_loader.py, dbt project
- **Why this matters:** dbt loading Bronze bypasses audit column generation
  (bronze_loader.py adds _source_file, _ingested_at, _pipeline_run_id).
  Bronze records without audit columns violate INV-04 and break the entire
  traceability chain from Gold back to source.
- **Enforcement points:**
  - bronze_loader.py — sole component that reads source/ and writes to bronze/
  - dbt project configuration — no dbt model declares source/ paths as
    sources or bronze/ paths as output targets

---

## Group 4 — Silver Layer Invariants — Transactions

---

### SIL-T-01
**Condition:** Every Bronze transaction record must result in exactly one
outcome: either promoted to Silver or written to Quarantine. Silver row count
plus Quarantine row count must equal Bronze row count for each date partition.

- **Category:** Data Correctness
- **Scope:** TASK-SCOPED — silver_promoter.py
- **Why this matters:** A record that falls through the promotion logic
  produces silent data loss. Gold aggregations are computed from an incomplete
  Silver layer with no error signal. The mass conservation equation is the
  only mechanism that detects this class of failure.
- **Enforcement points:**
  - silver_promoter.py — every record from Bronze must enter exactly one of
    two code paths: promotion to Silver or write to Quarantine

---

### SIL-T-02
**Condition:** No transaction_id may appear more than once across all Silver
transaction partitions.

- **Category:** Data Correctness
- **Scope:** TASK-SCOPED — silver_promoter.py
- **Why this matters:** Duplicate transaction_ids in Silver inflate Gold
  daily and weekly aggregations. total_signed_amount and total_transactions
  in Gold are both wrong, and the inflation is not detectable from Gold
  output alone.
- **Enforcement points:**
  - silver_promoter.py — cross-partition deduplication check before promotion;
    a transaction_id already present in any Silver partition is rejected to
    Quarantine (see GAP-INV-07)

---

### SIL-T-04
**Condition:** Every promoted Silver transaction must have a valid
transaction_code present in Silver transaction_codes at promotion time.

- **Category:** Data Correctness
- **Scope:** TASK-SCOPED — silver_promoter.py
- **Why this matters:** An invalid transaction_code means no valid
  debit_credit_indicator exists for that record. Sign assignment fails and
  _signed_amount is null, violating SIL-T-05 and producing a null value
  that propagates into Gold aggregations.
- **Enforcement points:**
  - silver_promoter.py — INVALID_TRANSACTION_CODE rejection rule; join
    to Silver transaction_codes before promotion; reject to Quarantine
    if no match found

---

### SIL-T-05
**Condition:** The _signed_amount must be non-null for every Silver
transaction record.

- **Category:** Data Correctness
- **Scope:** TASK-SCOPED — silver_promoter.py
- **Why this matters:** A null _signed_amount is silently excluded from
  Gold aggregations — total_signed_amount in Gold daily_summary is wrong
  with no error signal. Every promoted record must have sign applied before
  reaching Gold.
- **Enforcement points:**
  - silver_promoter.py — sign assignment step joins to Silver
    transaction_codes and applies debit_credit_indicator; null _signed_amount
    after this step is a promotion failure

---

### SIL-T-07
**Condition:** Records failing NULL_REQUIRED_FIELD, INVALID_AMOUNT,
INVALID_TRANSACTION_CODE, or INVALID_CHANNEL checks must be written to
Quarantine and must never appear in Silver.

- **Category:** Data Correctness
- **Scope:** TASK-SCOPED — silver_promoter.py
- **Why this matters:** A bad record in Silver corrupts Gold aggregations.
  A null required field or invalid amount in Silver produces wrong
  _signed_amount or wrong transaction counts in Gold. These failures are
  not detectable from Gold output alone.
- **Enforcement points:**
  - silver_promoter.py — four rejection rules applied in sequence before
    promotion; failed records routed to Quarantine with the correct
    rejection reason code
- **Verification advisory:** Four verification commands required in Phase 3 —
  one per rejection rule.

---

### SIL-T-08
**Condition:** Records with an unknown account_id must not be quarantined.
They must be written to Silver with _is_resolvable = false.

- **Category:** Data Correctness
- **Scope:** TASK-SCOPED — silver_promoter.py
- **Why this matters:** Quarantining an unresolvable record permanently
  loses a transaction that may be valid — the account delta file for that
  day may not yet have arrived. The flag-and-retain approach preserves the
  record for future backfill resolution. Quarantine is irreversible in this
  system (backfill out of scope).
- **Enforcement points:**
  - silver_promoter.py — UNRESOLVABLE_ACCOUNT_ID is the only rejection
    condition that routes to Silver rather than Quarantine; _is_resolvable
    set to false; record excluded from Gold via GOLD-D-02

---

### GAP-INV-07
**Condition:** A transaction_id that already exists in any Silver partition
must be rejected to Quarantine with rejection reason DUPLICATE_TRANSACTION_ID.
It must never overwrite or replace an existing Silver record.

- **Category:** Data Correctness
- **Scope:** TASK-SCOPED — silver_promoter.py
- **Why this matters:** A duplicate transaction_id overwriting an existing
  Silver record corrupts the audit trail — the original _signed_amount,
  _promoted_at, and _pipeline_run_id for that transaction are destroyed.
  The overwrite is not detectable after the fact. SIL-T-02 (no duplicates
  in Silver) is the outcome this invariant enforces.
- **Enforcement points:**
  - silver_promoter.py — cross-partition dedup check runs before promotion;
    any transaction_id found in existing Silver partitions is routed to
    Quarantine with DUPLICATE_TRANSACTION_ID

---

## Group 5 — Silver Layer Invariants — Accounts

---

### SIL-A-01
**Condition:** Silver Accounts must contain exactly one current record per
account_id at all times.

- **Category:** Data Correctness
- **Scope:** TASK-SCOPED — silver_promoter.py
- **Why this matters:** Duplicate account records produce ambiguous
  closing_balance values in Gold weekly_account_summary. gold_builder.py
  cannot determine which account record is current, producing wrong or
  non-deterministic closing_balance values.
- **Enforcement points:**
  - silver_promoter.py — upsert logic on account_id key; incoming record
    replaces existing record for the same account_id; no history retained

---

### GAP-INV-04
**Condition:** If no accounts delta file exists for a given date, Silver
Accounts must remain unchanged. The absence of an accounts delta file must
not be treated as an error condition and must not trigger any upsert
operation against Silver Accounts.

- **Category:** Operational
- **Scope:** TASK-SCOPED — bronze_loader.py, silver_promoter.py
- **Why this matters:** An accounts delta file is absent when no accounts
  changed that day — this is normal and expected behaviour. An error on
  missing file blocks the pipeline indefinitely. An incorrect upsert on an
  empty input corrupts Silver Accounts state, causing all transactions for
  that day to be flagged _is_resolvable = false and excluded from Gold.
- **Enforcement points:**
  - bronze_loader.py — detects missing accounts file; records SKIPPED for
    accounts Bronze model; does not create an empty partition
  - silver_promoter.py — checks for new Bronze accounts partition before
    running upsert; skips upsert entirely if no new partition exists

---

## Group 6 — Silver Layer Invariants — Quarantine

---

### SIL-Q-01
**Condition:** Every record written to Quarantine must carry a non-null
_rejection_reason.

- **Category:** Data Correctness
- **Scope:** TASK-SCOPED — silver_promoter.py
- **Why this matters:** A Quarantine record with no rejection reason is
  unactionable. An analyst cannot determine why the record was rejected,
  whether it is correctable, or which rejection rule it violated. Quarantine
  without rejection reasons is not an audit trail — it is a discard bin.
- **Enforcement points:**
  - silver_promoter.py — _rejection_reason set before every Quarantine write;
    no Quarantine write path exists without a rejection reason code

---

### SIL-Q-02
**Condition:** Every _rejection_reason value must belong to the predefined
rejection code list: NULL_REQUIRED_FIELD, INVALID_AMOUNT,
DUPLICATE_TRANSACTION_ID, INVALID_TRANSACTION_CODE, INVALID_CHANNEL,
INVALID_ACCOUNT_STATUS.

- **Category:** Data Correctness
- **Scope:** TASK-SCOPED — silver_promoter.py
- **Why this matters:** An undocumented rejection code cannot be acted on.
  Downstream processes that read Quarantine to assess data quality failures
  depend on the code list being exhaustive and stable. A rejection code
  outside the predefined list indicates a bug in rejection logic.
- **Enforcement points:**
  - silver_promoter.py — rejection reason codes are constants from a
    predefined enum or constant set; no free-text rejection reason is
    ever written

---

## Group 7 — Silver Layer Invariants — Reference Data

---

### SIL-REF-01
**Condition:** Silver transaction_codes must be populated before any
transaction Silver promotion runs. If the reference table is empty,
silver_promoter.py must stop and record FAILED in the run log.

- **Category:** Operational
- **Scope:** TASK-SCOPED — silver_promoter.py
- **Why this matters:** Transaction Codes is the authoritative source for
  sign logic and transaction code validation. If the reference table is
  absent, every transaction fails INVALID_TRANSACTION_CODE and lands in
  Quarantine. The pipeline appears to run successfully while producing an
  empty Silver transactions layer — a silent correctness failure.
- **Enforcement points:**
  - silver_promoter.py — explicit prerequisite guard checks Silver
    transaction_codes row count before any transaction promotion; returns
    FAILED immediately if count is zero

---

## Group 8 — Gold Layer Invariants — Daily Summary

---

### GOLD-D-01
**Condition:** Gold daily_summary must contain exactly one record per
distinct transaction_date present in Silver transactions where
_is_resolvable = true.

- **Category:** Data Correctness
- **Scope:** TASK-SCOPED — gold_builder.py
- **Why this matters:** Duplicate date rows in Gold daily_summary produce
  double-counted aggregations. An analyst summing total_signed_amount across
  dates gets an inflated total with no visible error. Financial reporting
  based on this output is incorrect.
- **Enforcement points:**
  - gold_builder.py — daily summary dbt model groups by transaction_date;
    full recomputation and replace on each run (GAP-INV-05) prevents
    append-on-rerun duplicates

---

### GOLD-D-02
**Condition:** Only Silver transactions with _is_resolvable = true may
contribute to any Gold aggregation. Records with _is_resolvable = false
must be excluded from all Gold computations. Applies to both daily_summary
and weekly_account_summary.

- **Category:** Data Correctness
- **Scope:** TASK-SCOPED — gold_builder.py
- **Why this matters:** Unresolvable records have no known account context.
  Including them in Gold aggregations inflates totals with data whose account
  attribution is unknown. The inflation is not detectable from Gold output
  alone — it appears as normal transaction data.
- **Enforcement points:**
  - gold_builder.py — all dbt Gold models apply WHERE _is_resolvable = true
    filter; no Gold model reads unresolvable records

---

### GOLD-D-03
**Condition:** total_signed_amount in Gold daily_summary must equal
SUM(_signed_amount) from Silver transactions for that transaction_date
where _is_resolvable = true.

- **Category:** Data Correctness
- **Scope:** TASK-SCOPED — gold_builder.py
- **Why this matters:** Wrong financial totals are acted on by risk teams
  making credit decisions. An incorrect total_signed_amount in Gold
  daily_summary is a financial reporting error. The harm is significant and
  the deviation is not detectable without explicit cross-layer verification.
- **Enforcement points:**
  - gold_builder.py — daily summary dbt model computes SUM(_signed_amount)
    from Silver transactions filtered to _is_resolvable = true

---

### GOLD-D-04
**Condition:** total_transactions in Gold daily_summary must equal COUNT(*)
from Silver transactions for that transaction_date where _is_resolvable = true.

- **Category:** Data Correctness
- **Scope:** TASK-SCOPED — gold_builder.py
- **Why this matters:** Wrong transaction counts produce incorrect volume
  metrics used in risk and operations reporting. total_transactions and
  total_signed_amount have independent failure modes — one can be wrong
  while the other is correct.
- **Enforcement points:**
  - gold_builder.py — daily summary dbt model computes COUNT(*) from Silver
    transactions filtered to _is_resolvable = true

---

## Group 9 — Gold Layer Invariants — Weekly Account Summary

---

### GOLD-W-01
**Condition:** Gold weekly_account_summary must contain exactly one record
per account_id per calendar week (Monday to Sunday) where at least one
resolvable transaction exists for that account and week.

- **Category:** Data Correctness
- **Scope:** TASK-SCOPED — gold_builder.py
- **Why this matters:** Duplicate rows for the same account and week produce
  double-counted weekly aggregations. Analysts querying weekly account
  performance get inflated figures with no visible error.
- **Enforcement points:**
  - gold_builder.py — weekly summary dbt model groups by account_id and
    week_start_date; full recomputation and replace prevents append duplicates

---

### GOLD-W-02
**Condition:** total_purchases must equal the count of PURCHASE type
transactions in Silver for that account_id and week where
_is_resolvable = true.

- **Category:** Data Correctness
- **Scope:** TASK-SCOPED — gold_builder.py
- **Why this matters:** Wrong purchase count produces incorrect weekly
  account performance metrics. Purchase volume is a key risk indicator —
  an analyst acting on a wrong count makes an incorrect risk assessment.
- **Enforcement points:**
  - gold_builder.py — weekly summary dbt model filters to transaction_type
    = PURCHASE and _is_resolvable = true before counting

---

### GOLD-W-03
**Condition:** avg_purchase_amount must equal the average _signed_amount
of PURCHASE type transactions in Silver for that account_id and week
where _is_resolvable = true.

- **Category:** Data Correctness
- **Scope:** TASK-SCOPED — gold_builder.py
- **Why this matters:** Wrong average purchase amount produces incorrect
  spending pattern analysis. avg_purchase_amount and total_purchases have
  independent failure modes — average can be wrong while count is correct.
- **Enforcement points:**
  - gold_builder.py — weekly summary dbt model computes AVG(_signed_amount)
    filtered to PURCHASE type and _is_resolvable = true

---

### GOLD-W-04
**Condition:** total_payments, total_fees, and total_interest must each
equal the sum of _signed_amount for their respective transaction types in
Silver for that account_id and week where _is_resolvable = true.

- **Category:** Data Correctness
- **Scope:** TASK-SCOPED — gold_builder.py
- **Why this matters:** Wrong payment, fee, or interest totals produce
  incorrect account balance reconciliation in weekly summaries. Each
  transaction type has an independent failure mode — one sum can be wrong
  while others are correct.
- **Enforcement points:**
  - gold_builder.py — weekly summary dbt model computes SUM(_signed_amount)
    separately per transaction_type filtered to _is_resolvable = true
- **Verification advisory:** Three verification commands required in Phase 3
  — one per transaction type.

---

### GOLD-W-05
**Condition:** closing_balance in Gold weekly_account_summary must be
non-null and must reflect current_balance from Silver Accounts as of
week_end_date or the most recent available record. A null closing_balance
is a pipeline failure signal, not a valid data state.

- **Category:** Data Correctness
- **Scope:** TASK-SCOPED — gold_builder.py
- **Why this matters:** A null closing_balance means an account appears in
  Gold weekly output with no balance context. Every account_id in Gold weekly
  must have a corresponding Silver Accounts record (GAP-INV-06). A null
  indicates the join failed — a pipeline failure, not missing data.
- **Enforcement points:**
  - gold_builder.py — closing_balance joined from Silver Accounts on
    account_id; null closing_balance after join triggers pipeline FAILED

---

## Group 10 — Gap Invariants — Pipeline Sequencing and Behaviour

---

### GAP-INV-01a
**Condition:** The historical pipeline must process dates in strict ascending
order. A later date must never be processed before an earlier date in the
same historical run.

- **Category:** Operational
- **Scope:** TASK-SCOPED — pipeline.py
- **Why this matters:** Processing transactions before accounts for a given
  date causes Silver promotion to validate account_ids against an incomplete
  Silver Accounts table. Valid transactions for accounts that arrive later
  in the date range are flagged _is_resolvable = false and permanently
  excluded from Gold with no error signal.
- **Enforcement points:**
  - pipeline.py — date-range loop iterates in ascending date order;
    dates are sorted before loop begins

---

### GAP-INV-01b
**Condition:** For each date in the historical pipeline, within-date
processing must follow this sequence: transaction_codes loaded to Silver
first, then accounts promoted to Silver, then transactions promoted to
Silver. Each step must complete successfully before the next begins.

- **Category:** Operational
- **Scope:** TASK-SCOPED — pipeline.py, silver_promoter.py
- **Why this matters:** Processing transactions before accounts for a given
  date means account_id validation runs against an incomplete Silver Accounts
  table. Valid transactions are silently flagged _is_resolvable = false and
  excluded from Gold. This failure is silent — the pipeline reports SUCCESS
  while producing wrong Gold output.
- **Enforcement points:**
  - pipeline.py — within-date sequence is fixed: transaction_codes → accounts
    → transactions; each step evaluates result object before proceeding
  - silver_promoter.py — SIL-REF-01 prerequisite guard ensures
    transaction_codes is loaded before any transaction promotion

---

### GAP-INV-02
**Condition:** When the incremental pipeline finds no source file for
watermark + 1, it must exit without writing to any data layer and without
advancing the watermark. The absence of a source file is not an error
condition.

- **Category:** Operational
- **Scope:** TASK-SCOPED — pipeline.py, bronze_loader.py
- **Why this matters:** Advancing the watermark when no data was processed
  marks a date as complete with no output. Subsequent incremental runs skip
  that date permanently, leaving a gap in Gold output with no indication of
  what was missed.
- **Enforcement points:**
  - bronze_loader.py — file existence check before ingestion; returns
    SKIPPED if no source file found
  - pipeline.py — evaluates SKIPPED result; exits without calling
    silver_promoter.py, gold_builder.py, or control_manager.py watermark
    write

---

### GAP-INV-03
**Condition:** Within a single pipeline run, Bronze must complete
successfully before Silver begins, and Silver must complete successfully
before Gold begins. A stage must not begin if its predecessor returned
a FAILED result.

- **Category:** Operational
- **Scope:** TASK-SCOPED — pipeline.py
- **Why this matters:** Silver running against an incomplete or failed Bronze
  partition promotes wrong data to Silver. Gold running against wrong Silver
  produces wrong aggregations. Neither failure produces an explicit error —
  the downstream stage simply processes incorrect input.
- **Enforcement points:**
  - pipeline.py — evaluates structured result object from each module before
    calling the next; FAILED result stops the pipeline immediately; downstream
    stages are never invoked after a FAILED predecessor

---

### GAP-INV-05
**Condition:** Gold aggregations for a processed date must be fully
recomputed on each pipeline run. Gold must never append to existing rows
for the same date — existing rows must be replaced.

- **Category:** Data Correctness
- **Scope:** TASK-SCOPED — gold_builder.py
- **Why this matters:** Gold append-on-rerun doubles aggregation rows for
  the processed date. GOLD-D-01 (one record per date) and GOLD-W-01 (one
  record per account per week) are both violated. Analysts querying Gold
  totals after a rerun see inflated figures with no error signal.
- **Enforcement points:**
  - gold_builder.py — existing Gold rows for the processed date are deleted
    before dbt Gold models run; dbt writes fresh aggregations to replace them

---

### GAP-INV-06
**Condition:** Every account_id present in Gold weekly_account_summary must
have a corresponding record in Silver Accounts. A Gold weekly summary row
for an account with no Silver Accounts record is a pipeline failure.

- **Category:** Data Correctness
- **Scope:** TASK-SCOPED — gold_builder.py
- **Why this matters:** An account_id in Gold weekly summary with no Silver
  Accounts record produces null closing_balance (violating GOLD-W-05) and
  represents aggregated transactions for an account with no known profile.
  This is not a data gap — it is a pipeline failure that must be surfaced
  explicitly.
- **Enforcement points:**
  - gold_builder.py — closing_balance join is an INNER JOIN on Silver
    Accounts; any account_id with no match causes pipeline to return FAILED

---

## Group 11 — S1B Invariants — Architecture Contracts

---

### S1B-01a
**Condition:** Every module — bronze_loader.py, silver_promoter.py,
gold_builder.py, control_manager.py — must return a structured result
object containing at minimum: status (SUCCESS/FAILED/SKIPPED),
records_processed, records_written, records_rejected (Silver only —
null otherwise), error_message (null on SUCCESS).

- **Category:** Operational
- **Scope:** TASK-SCOPED — all four modules
- **Why this matters:** A missing or malformed result object causes an
  unhandled exception in pipeline.py — not a clean FAILED state. The
  pipeline cannot evaluate whether to proceed, cannot write a correct run
  log entry, and cannot make a correct watermark decision. The entire
  failure handling architecture depends on well-formed result objects.
- **Enforcement points:**
  - bronze_loader.py, silver_promoter.py, gold_builder.py,
    control_manager.py — each returns a result object with all defined
    fields on every code path including error paths
- **Verification advisory:** Five verification cases required in Phase 3 —
  one per result object field.

---

### S1B-01b
**Condition:** pipeline.py must not invoke the next stage if the preceding
module returned no result object or returned status = FAILED.

- **Category:** Operational
- **Scope:** TASK-SCOPED — pipeline.py
- **Why this matters:** A pipeline that proceeds past a FAILED stage runs
  Silver against incomplete Bronze, or Gold against wrong Silver — producing
  incorrect outputs with no error signal. The stage result contract is the
  load-bearing mechanism for all failure handling.
- **Enforcement points:**
  - pipeline.py — evaluates result object after each module call; None
    result or FAILED status triggers immediate pipeline stop; run log
    records FAILED; watermark is not advanced

---

### S1B-02
**Condition:** The historical pipeline and the incremental pipeline must
produce identical Bronze, Silver, Quarantine, and Gold output for the same
input date. The invocation path must not affect the output.

- **Category:** Data Correctness
- **Scope:** TASK-SCOPED — pipeline.py shared core
- **Why this matters:** Logic drift between the historical and incremental
  paths produces different Gold outputs for the same input. An analyst
  reprocessing a date via the historical pipeline gets a different result
  than the original incremental run — with no error signal and no way to
  determine which result is correct.
- **Enforcement points:**
  - pipeline.py — shared core processing function; both pipelines call the
    same core for each date; transformation logic defined once

---

### S1B-05
**Condition:** run_log.parquet must be written exclusively by run_logger.py.
No dbt model may write to, append to, or modify run_log.parquet.

- **Category:** Data Correctness
- **Scope:** TASK-SCOPED — run_logger.py, dbt project
- **Why this matters:** A dbt model writing to the run log creates a circular
  dependency — the model records its own execution. This also risks
  overwriting append-only entries (violating RL-01b) and introducing
  non-deterministic write ordering across dbt and Python writers.
- **Enforcement points:**
  - run_logger.py — sole writer to pipeline/run_log.parquet
  - dbt project configuration — no dbt model declares run_log.parquet as
    an output target

---

### S1B-06
**Condition:** The control table watermark write must be the final operation
in a successful pipeline run — after all run log entries for that run are
recorded with status = SUCCESS. The watermark must never be written before
the run log is complete.

- **Category:** Operational
- **Scope:** TASK-SCOPED — pipeline.py, control_manager.py
- **Why this matters:** A pipeline crash between the watermark write and the
  run log write leaves the watermark advanced with no SUCCESS run log entries
  for that run. INV-05a (run_id in data layers has SUCCESS run log entry) is
  violated. The date is marked as processed but the audit trail is absent.
- **Enforcement points:**
  - pipeline.py — orchestration sequence calls run_logger.py to record
    all SUCCESS entries before calling control_manager.py watermark write
  - control_manager.py — watermark write is the final call in pipeline.py
    orchestration sequence

---

### S1B-dbt-silver-gold
**Condition:** Silver and Gold transformations must be implemented exclusively
as dbt models. No ad-hoc SQL, Python DataFrame operations, or direct DuckDB
queries may be used to produce Silver or Gold layer outputs.

- **Category:** Data Correctness
- **Scope:** TASK-SCOPED — silver_promoter.py, gold_builder.py, dbt project
- **Why this matters:** Ad-hoc SQL outside dbt bypasses quality rule
  enforcement, deduplication logic, and audit column generation. Silver
  records produced outside dbt may be missing _pipeline_run_id (violating
  INV-04), may skip rejection rules (violating SIL-T-07), or may not apply
  the _is_resolvable flag correctly.
- **Enforcement points:**
  - silver_promoter.py — invokes dbt Silver models exclusively; no direct
    DuckDB writes to silver/ paths
  - gold_builder.py — invokes dbt Gold models exclusively; no direct DuckDB
    writes to gold/ paths

---

### S1B-gold-source
**Condition:** Gold models must read exclusively from Silver layer Parquet
files. No Gold model may read directly from Bronze partitions or source
CSV files.

- **Category:** Data Correctness
- **Scope:** TASK-SCOPED — gold_builder.py, dbt project
- **Why this matters:** Gold reading Bronze directly bypasses all Silver
  quality rules. A Gold aggregate computed from Bronze includes malformed
  records, duplicates, and records that Silver would have quarantined.
  The resulting Gold totals are wrong and the wrong input is not detectable
  from Gold output alone.
- **Enforcement points:**
  - dbt Gold model source declarations — all Gold models declare Silver
    Parquet files as sources; no Bronze or source/ paths referenced

---

### S1B-files
**Condition:** The pipeline must not process Silver or Gold for a date unless
the transactions Bronze partition for that date is present. If the
transactions Bronze partition is absent or empty, the pipeline must return
FAILED and must not advance the watermark.

- **Category:** Operational
- **Scope:** TASK-SCOPED — pipeline.py, bronze_loader.py
- **Why this matters:** Silver running with no transactions Bronze partition
  produces an empty Silver transactions layer with no error signal. Gold
  then computes aggregations over zero transactions — appearing as a valid
  zero-transaction day rather than a pipeline failure. The watermark advances
  and the date is permanently marked as processed with wrong Gold output.
- **Enforcement points:**
  - bronze_loader.py — checks for non-empty Bronze transactions partition
    before Silver is invoked; returns FAILED if absent or empty
  - pipeline.py — evaluates bronze_loader.py result; does not call
    silver_promoter.py or gold_builder.py if Bronze transactions FAILED

---

### S1B-parquet
**Condition:** All Bronze, Silver, Quarantine, Gold, and control layer
outputs must be written as Parquet files. No intermediate database, CSV
file, or non-Parquet format may be produced as a layer output.

- **Category:** Data Correctness
- **Scope:** TASK-SCOPED — all modules
- **Why this matters:** Parquet is the integration contract between layers.
  A non-Parquet output in silver/ would not be read by downstream dbt models
  — the downstream layer silently produces empty output without an error.
  The format contract must hold for the pipeline to be correct.
- **Enforcement points:**
  - bronze_loader.py — writes Parquet exclusively to bronze/
  - silver_promoter.py — writes Parquet exclusively to silver/
  - gold_builder.py — writes Parquet exclusively to gold/
  - control_manager.py — writes Parquet exclusively to pipeline/
  - run_logger.py — writes Parquet exclusively to pipeline/

---

## Invariant Count Summary

| Group | Count |
|---|---|
| Group 1 — Pipeline Operational | 5 |
| Group 2 — Audit Trail and Traceability | 7 |
| Group 3 — Bronze Layer | 5 |
| Group 4 — Silver — Transactions | 7 |
| Group 5 — Silver — Accounts | 2 |
| Group 6 — Silver — Quarantine | 2 |
| Group 7 — Silver — Reference Data | 1 |
| Group 8 — Gold — Daily Summary | 4 |
| Group 9 — Gold — Weekly Account Summary | 5 |
| Group 10 — Gap — Pipeline Sequencing | 6 |
| Group 11 — S1B Architecture Contracts | 9 |
| **Total** | **53** |

---

## GLOBAL vs TASK-SCOPED

| Scope | Count | IDs |
|---|---|---|
| GLOBAL | 1 | INV-04 |
| TASK-SCOPED | 52 | All others |

---

## Open Questions Resolved

| OQ | Resolution |
|---|---|
| OQ-1 — Delayed vs missing file | Option A — both treated as no-op for this exercise. Wait/retry and controlled override deferred to ARCHITECTURE.md Section 7 future enhancements. |
| OQ-2 — Run log SKIPPED entry on no-op | SKIPPED entries written for all models on no-op invocation. run_id must not appear in any data layer. Captured in INV-05b and RL-01a. |
| OQ-3 — _pipeline_run_id format | UUIDv4. Collision resistance satisfies RL-02 by design. |
