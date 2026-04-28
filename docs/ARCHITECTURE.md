# ARCHITECTURE.md — Credit Card Transactions Lake

## Changelog
| Version | Date | Author | Change |
|---|---|---|---|
| v1.0 | 2026-04-08 | Krishna | Greenfield — Initial |
| v1.1 | 2026-04-09 | Krishna | Added Component Architecture (Section 2A), expanded Data Model with field-level entity detail and entity relationship map (Section 8), added Constraint Traceability (Section 10) |
| v1.2 | 2026-04-10 | Krishna | Phase 2 complete — OQ-1, OQ-2, OQ-3 resolved and recorded in Section 6; three future enhancement items added to Section 7 from OQ-1 Option A resolution |

---

## 1. Problem Framing

### What the system solves

Data analysts and risk teams currently access raw CSV extract files directly,
bypassing quality control, producing inconsistent results when working from
different file versions, and leaving no audit trail from raw data to reported
numbers. This system implements a Medallion architecture pipeline
(Bronze → Silver → Gold) that ingests daily extract files, enforces defined
quality rules at each layer boundary, and produces Gold-layer aggregations
that analysts can query with confidence via DuckDB. Every result is traceable
to its source file and the pipeline run that produced it.

### What the system explicitly does not solve

- Backfill of specific historical dates to correct errors
- SCD Type 2 history for account attribute changes
- Resolution of _is_resolvable = false records
- Streaming or near-realtime ingestion
- A serving API layer — Gold is queried directly via DuckDB CLI
- Schema evolution
- Production monitoring or alerting infrastructure

### What success looks like

An analyst can run a single DuckDB query against Gold, get a number, and trace
every record that contributed to it back to the source CSV file and the pipeline
run that produced it. The pipeline is re-runnable without manual cleanup. The
same input always produces identical output.

---

## 2. Key Design Decisions

### Decision 1 — Layered Module Architecture (Architecture B)

**What was decided:** `pipeline.py` is a thin orchestrator. Each layer is a
separate Python module with a defined interface: `bronze_loader.py`,
`silver_promoter.py`, `gold_builder.py`, `control_manager.py`,
`run_logger.py`. Each module returns a structured result object
(success/failure, records_processed, records_written, records_rejected).
`pipeline.py` evaluates each result before proceeding to the next stage.

**Rationale:** The system's failure handling, auditability, and sequencing
constraints require explicit stage-level result contracts. A monolithic script
cannot guarantee clean stage boundaries without hidden coupling. Stage result
contracts make partial failure detection explicit — `pipeline.py` knows exactly
which stage failed and stops there.

**Alternatives rejected:**

- Architecture A — Monolithic pipeline script: rejected because failure handling
  and auditability constraints require explicit stage boundaries. A single script
  cannot enforce these without introducing hidden coupling and ambiguity between
  stages.

- Architecture C — dbt-centric architecture: rejected because dbt-managed
  sequencing distributes execution across the DAG and forces the pipeline to
  infer completeness from artifacts, weakening the watermark advancement
  guarantee. Centralised sequencing in Architecture B directly enforces that
  watermark advancement requires full pipeline success.

---

### Decision 2 — Shared Core with Two Invocation Paths

**What was decided:** Both historical and incremental pipelines share the same
core processing flow. The historical pipeline wraps the core in a date-range
loop. The incremental pipeline calls the core for a single date derived from
watermark + 1. Both are entry points into `pipeline.py` selected by
command-line argument.

**Rationale:** Shared core prevents logic drift — transformation logic, quality
rules, and audit column generation are defined once. Two separate implementations
would risk producing different results for the same input, directly violating the
reproducibility constraint.

**Alternatives rejected:** Separate scripts for historical and incremental
pipelines — rejected because duplicated logic creates maintenance risk and
reproducibility cannot be guaranteed across two independent implementations.

---

### Decision 3 — Bronze Idempotency via Row Count Verification

**What was decided:** Before ingesting a source file, `bronze_loader.py` checks
whether the Bronze partition for that date already exists and whether its row
count matches the source CSV row count. If both match, ingestion is skipped. If
the partition is missing or row counts do not match, the partition is deleted and
reprocessed from the source CSV.

**Rationale:** File-level skip detection alone cannot detect a partial Bronze
write — a partition may exist but be incomplete. Row count verification against
the source CSV is the only mechanism that verifies actual data state rather than
trusting a side-channel registry.

**Alternatives rejected:** Success marker file registry — rejected because it
trusts a side-channel registry rather than verifying actual partition state. A
corrupt or incomplete partition would be skipped silently if the marker file was
written before the write completed.

---

### Decision 4 — Silver Re-promotion Strategy: Atomic Overwrite

**What was decided:** Silver promotion for a given date deletes the existing
partition (if present), recomputes from Bronze, writes to a temporary path, and
atomically replaces the old partition via file rename. This applies to both
historical reprocessing and incremental reruns.

**Rationale:** Overwrite guarantees a clean state regardless of what the
previous partial run left behind. Because Bronze is immutable and promotion
logic is deterministic, the output is always identical for the same input —
idempotency is preserved and clean state is a guaranteed property, not
best-effort.

**Alternatives rejected:** Skip existing Silver partitions — rejected because a
partial write from a failed run would persist without correction, leaving Silver
in an inconsistent state on the next run.

---

### Decision 5 — Run Log Owned Exclusively by run_logger.py

**What was decided:** The run log is written exclusively by `run_logger.py` as
a Python module. dbt models return execution metadata via structured result
objects. `pipeline.py` passes those results to `run_logger.py`, which appends
to the Parquet file directly. dbt never writes to the run log.

**Rationale:** A run log implemented as a dbt model creates a circular
dependency — the model records execution of the models that write to it.
Ownership by `run_logger.py` eliminates this entirely. The run log remains
append-only and is never rolled back — partial failures are preserved
intentionally, providing traceability while the control table guards correctness.

**Alternatives rejected:** Run log as dbt model (Architecture C pattern) —
rejected due to circular dependency risk and loss of explicit control over
append-only write semantics.

---

### Decision 6 — Transaction Codes as Explicit Prerequisite Guard

**What was decided:** `silver_promoter.py` enforces an explicit guard before
any transaction Silver promotion runs: Silver transaction_codes must be
populated. If the reference table is empty, the pipeline stops and records
FAILED in the run log for the Silver transactions model. The historical pipeline
loads Transaction Codes to Silver before processing any daily files.

**Rationale:** Transaction Codes is the authoritative source for sign logic and
transaction code validation. If the reference table is absent, every transaction
will fail INVALID_TRANSACTION_CODE and land in quarantine. This is a silent
correctness failure — the pipeline would appear to run successfully while
producing an empty Silver transactions layer.

**Alternatives rejected:** Implicit enforcement via dbt model dependency —
rejected because an implicit dependency is not visible as a guard condition and
does not produce an explicit failure signal if violated.

---

### Decision 7 — Control Table as Last Write on Full Success

**What was decided:** The control table watermark is advanced by
`control_manager.py` as the final write in a successful pipeline run — after
Gold completes successfully and all run log entries for that run are recorded
with SUCCESS status. If any stage fails, the watermark is not advanced and the
date remains reprocessable.

**Rationale:** The watermark is the correctness guard — it must reflect only
fully completed runs. Advancing it before Gold completes would mark a date as
processed when Gold aggregations may be absent or incomplete.

**Alternatives rejected:** Advancing watermark after Silver completes — rejected
because Gold may still fail, leaving the date marked as processed with no Gold
output.

---

## 3. Challenge My Decisions

### Challenge 1 — Row count verification is insufficient for Bronze idempotency

**Challenge:** A source CSV and its Bronze partition could have identical row
counts but different data — if the CSV was replaced with a corrected version
after initial ingestion, row count verification would skip re-ingestion silently.

**Assessment:** Valid but out of scope. The brief specifies source files in
`source/` are read-only and fixed for this exercise. Source file replacement is
not a defined scenario. For production, a checksum-based verification would be
required. Deferred to future enhancement.

---

### Challenge 2 — Atomic overwrite via file rename is not guaranteed atomic on all filesystems

**Challenge:** File rename atomicity depends on the OS and filesystem. On some
Docker volume configurations, rename across different mount points is not atomic.

**Assessment:** Valid operational risk. Mitigated by ensuring temp path and
target path are on the same filesystem mount. Docker Compose bind mount
configuration must place both on the same volume. Noted as a deployment
constraint.

---

### Challenge 3 — Stage result contracts add overhead for a training system

**Challenge:** The structured result object pattern adds implementation overhead
that may not be justified for a seven-day seed dataset.

**Assessment:** Rejected. The result contracts are load-bearing — they are the
mechanism that enforces watermark advancement correctness and partial failure
detection. Removing them to reduce overhead would compromise the auditability
constraints the system is designed to demonstrate.

---

### Challenge 4 — Explicit Transaction Codes guard duplicates dbt dependency management

**Challenge:** dbt already manages model dependencies. An explicit Python guard
duplicates this concern across two systems.

**Assessment:** Rejected. The dbt dependency ensures correct execution order
within dbt. The Python guard ensures the reference data is actually populated
before promotion runs — these are different enforcement points. The dbt
dependency cannot detect an empty reference table.

---

## 4. Key Risks

| Risk | Mitigation |
|---|---|
| Atomic rename fails across mount points | Ensure temp and target paths share the same Docker volume mount |
| Transaction Codes not loaded before incremental run on fresh environment | Explicit guard in silver_promoter.py stops pipeline with FAILED status |
| Silver partial write persists across runs | Atomic overwrite strategy guarantees clean state on every rerun |
| Gold aggregates silently exclude records due to _is_resolvable flag failure | Silver + quarantine = Bronze row count invariant detects promotion failures |
| Watermark advances on partial success | Control table write is final step — after all stage result contracts return SUCCESS |

---

## 5. Key Assumptions

- Source CSV schema is fixed for this exercise — no schema evolution handling required
- Transaction Codes dimension is static — no updates during pipeline operation
- Docker Compose bind mount places temp and target paths on the same filesystem
- Companion scaffold repository provides correct file naming conventions and pre-seeded data
- Seven daily files are the complete input set — no additional dates beyond the scaffold

---

## 6. Open Questions

All open questions resolved at Phase 2 completion — 2026-04-10.

| # | Question | Resolution | Resolved |
|---|---|---|---|
| OQ-1 | Delayed vs genuinely missing file — should operational handling differ? | **Option A adopted for this exercise.** Both delayed and missing files are treated as no-op — pipeline exits without writing to any data layer and without advancing the watermark. The absence of a source file is not an error condition. Delayed file wait/retry and controlled override mechanisms are production patterns deferred to Section 7. | 2026-04-10 |
| OQ-2 | Run log SKIPPED entry on no-op — write a SKIPPED row or write nothing? | **Write SKIPPED entries.** Every pipeline invocation must produce run log entries for all models. When no source file is available for watermark + 1, all run log entries for that invocation carry status = SKIPPED. The run_id for a SKIPPED invocation must not appear in any data layer. | 2026-04-10 |
| OQ-3 | _pipeline_run_id format — UUID, timestamp-based string, or other? | **UUIDv4.** Generated by pipeline.py at invocation start. UUID collision resistance satisfies the uniqueness invariant (RL-02) by design. No additional coordination required across concurrent runs. | 2026-04-10 |

---

## 7. Future Enhancements (Parking Lot)

| Item | Rationale for deferral |
|---|---|
| Backfill pipeline for specific historical dates | Requires dedicated watermark guard logic — out of scope per brief |
| SCD Type 2 for Accounts | Full history preservation — out of scope per brief |
| Checksum-based Bronze verification | Source files are fixed for this exercise — row count sufficient |
| Serving API layer | Gold queried directly via DuckDB CLI — out of scope per brief |
| Resolution of _is_resolvable = false records | Depends on backfill pipeline — out of scope |
| Production monitoring and alerting | Out of scope per brief |
| Delayed file wait/retry mechanism | OQ-1 Option A deferral. Production pattern requiring retry interval, timeout definition, and escalation behaviour when file has not arrived within the window. Requires a new pipeline control mechanism distinct from the current no-op exit. |
| Controlled override for permanently missing dates | OQ-1 Option A deferral. Production pattern requiring a marking mechanism (who can mark a date as permanently missing), an observable state change in the control table, and a watermark guard that permits the pipeline to advance past the marked date. |
| Per-date skip acknowledgment log | OQ-1 Option A deferral. When a date is skipped via controlled override, an explicit acknowledgment record should be written to an audit log — distinct from the run log — recording the date, the actor, the reason, and the timestamp. Provides an audit trail for skipped dates separate from normal pipeline execution records. |

---

## 8. Data Model

### First-class entities

**Transactions (fact):** Append-only daily fact records. One CSV per calendar
day. transaction_id is globally unique. amount is always positive in source —
sign assigned in Silver via Transaction Codes debit_credit_indicator. account_id
and transaction_code are foreign keys validated at Silver promotion.

**Transaction Codes (reference):** Static dimension. Loaded once during
historical pipeline initialisation. Authoritative source for sign logic
(DR = positive, CR = negative) and transaction type classification. Never
updated during pipeline operation.

**Accounts (slowly changing, simplified):** Daily delta files containing only
new or changed records. Silver maintains latest state per account_id via upsert.
No history retained — SCD Type 2 deferred to future enhancement.

### Layer outputs

**Bronze:** Immutable raw partitions. One Parquet file per source entity per
date. Audit columns added by pipeline. Never modified after initial write.

**Silver Transactions:** Clean, validated, deduplicated records. Globally
deduplicated on transaction_id. Sign applied from Transaction Codes.
_is_resolvable flag set at promotion time. Records with unknown account_id
enter Silver with _is_resolvable = false and are excluded from Gold.

**Silver Accounts:** Latest state per account_id. Upsert on each delta file.
No partition — single Parquet file.

**Silver Transaction Codes:** Single reference Parquet file. Loaded once.
Never updated incrementally.

**Silver Quarantine:** Rejected records with _rejection_reason codes.
Partitioned by Bronze source date. Records failing hard rejection rules
(NULL_REQUIRED_FIELD, INVALID_AMOUNT, DUPLICATE_TRANSACTION_ID,
INVALID_TRANSACTION_CODE, INVALID_CHANNEL, INVALID_ACCOUNT_STATUS) never
enter Silver — written to quarantine with reason code only.

**Gold Daily Summary:** One record per calendar day. Resolvable transactions
only (_is_resolvable = true). Recomputed on each pipeline run for the
processed date.

**Gold Weekly Account Summary:** One record per account per calendar week
(Monday to Sunday). Resolvable transactions only. Closing balance from latest
Silver Accounts state. A null closing_balance is not a valid data state — it
indicates a pipeline failure, as every account_id in Gold must have a
corresponding Silver Accounts record.

### Control and audit

**Pipeline Control Table:** Single Parquet file at pipeline/control.parquet.
Tracks watermark — last successfully processed date. Written last on full
pipeline success by control_manager.py. Never advanced on partial success.

**Pipeline Run Log:** Append-only Parquet file at pipeline/run_log.parquet.
One row per model per pipeline invocation. Written exclusively by
run_logger.py. Never rolled back — partial failures preserved intentionally.
Connective tissue between Gold aggregates and source Bronze records via
_pipeline_run_id.

---

## 9. Out of Scope Decisions

| Decision | Rationale |
|---|---|
| No backfill pipeline | Requires dedicated watermark guard logic with different invocation semantics — documented as known production pattern |
| No SCD Type 2 for Accounts | Simplification conscious — cost is inability to reconstruct historical account state |
| No transaction code changes during operation | Production pattern requiring cross-team coordination — static for this exercise |
| No streaming ingestion | Batch pipeline only |
| No serving API | DuckDB CLI is sufficient for this exercise |
| No schema evolution | Fixed schema for this exercise |
| No _is_resolvable resolution | Depends on backfill pipeline — out of scope above |
