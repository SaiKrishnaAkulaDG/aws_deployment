# Claude.md — v1.0 · FROZEN · 2026-04-15

## Changelog
| Version | Date | Author | Change |
|---|---|---|---|
| v1.0 | 2026-04-15 | Krishna | Greenfield — Initial. Phase 5 output. |

---

## 1. System Intent

This system ingests daily credit card transaction CSV files through a three-layer medallion pipeline (Bronze → Silver → Gold), producing auditable Parquet datasets and a fully traceable run log, using Python modules for Bronze ingestion and dbt exclusively for Silver and Gold transformation.
It does not expose a serving API, perform schema evolution, execute backfills, or use any external service calls — all computation is local, embedded, and deterministic.
Success is: every record in every layer carries a non-null `_pipeline_run_id`; every successful invocation is recorded in the run log; idempotent re-runs produce identical outputs; and the watermark advances only after full pipeline success.

---

## 2. Hard Invariants

**[Methodology-mandated — cannot be removed, does not consume an engineer slot]**
INVARIANT: Each function, method, or handler must have a single stateable purpose. Conditional nesting exceeding two levels is a structural violation — refactor before proceeding. This is never negotiable.

**[Engineer — INV-04 · GLOBAL]**
INVARIANT: Every record written to Bronze, Silver, Quarantine, or Gold must carry a non-null `_pipeline_run_id`. A null `_pipeline_run_id` in any data layer is an immediate build stop — the audit chain is broken and no downstream task may proceed. This is never negotiable.

**[Engineer — INV-02 · GLOBAL]**
INVARIANT: The watermark in the control table must advance only after all Bronze, Silver, and Gold writes for that invocation have completed successfully and all run log entries for that run_id carry status = SUCCESS. A watermark write before run log completion leaves the system in an unauditable state. This is never negotiable.

**[Engineer — S1B-05 / Decision 5 · GLOBAL]**
INVARIANT: `pipeline/run_log.parquet` must be written exclusively by `pipeline/run_logger.py`. No dbt model may write to, append to, or modify `run_log.parquet` under any circumstance. This is never negotiable.

**[Engineer — GAP-INV-02 / OQ-1 · GLOBAL]**
INVARIANT: When the source file for the target date is absent, the pipeline must exit without writing to any data layer and without advancing the watermark. SKIPPED run log entries are written for all models; the SKIPPED run_id must not appear in any data layer partition. This is never negotiable.

**[Engineer — S1B-dbt-silver-gold · GLOBAL]**
INVARIANT: Silver and Gold transformation logic must be implemented exclusively as dbt models. Python modules (`silver_promoter.py`, `gold_builder.py`) are invokers only — they call `dbt run`; they must not contain transformation SQL or data-shaping logic. This is never negotiable.

> Note: Five engineer invariants are declared above. The methodology-mandated invariant (complexity) is pre-declared and does not count against the engineer slot limit.

---

## 3. Scope Boundary

CC is permitted to create or modify only the following files:

**Session 1 — Scaffold:**
- `brief/.gitkeep`, `docs/.gitkeep`, `docs/prompts/.gitkeep`, `sessions/.gitkeep`, `verification/.gitkeep`, `discovery/.gitkeep`, `discovery/components/.gitkeep`, `enhancements/.gitkeep`, `tools/.gitkeep`
- `source/.gitkeep`, `pipeline/.gitkeep`, `bronze/.gitkeep`, `silver/.gitkeep`, `silver_temp/.gitkeep`, `gold/.gitkeep`, `quarantine/.gitkeep`, `dbt/.gitkeep`
- `README.md`, `PROJECT_MANIFEST.md`
- `Dockerfile`, `docker-compose.yml`, `requirements.txt`, `.gitignore`
- `dbt/dbt_project.yml`, `dbt/profiles.yml`, `dbt/models/silver/.gitkeep`, `dbt/models/gold/.gitkeep`
- `source/transaction_codes.csv`, `source/transactions_2024-01-01.csv` through `source/transactions_2024-01-06.csv`, `source/accounts_2024-01-01.csv` through `source/accounts_2024-01-06.csv`
- `tools/launch.sh`, `tools/resume_session.sh`, `tools/resume_challenge.sh`, `tools/challenge.sh`, `tools/monitor.sh`
- `docs/Claude.md` (this file — placed in Session 1, never modified)
- `sessions/S1_SESSION_LOG.md`, `sessions/S1_VERIFICATION_RECORD.md`

**Session 2 — Bronze:**
- `pipeline/run_logger.py`
- `pipeline/bronze_loader.py`
- `pipeline/control_manager.py`
- `pipeline/pipeline_historical.py` (Bronze invocation only at this stage)
- `sessions/S2_SESSION_LOG.md`, `sessions/S2_VERIFICATION_RECORD.md`

**Session 3 — Silver:**
- `dbt/models/silver/silver_transaction_codes.sql`, `dbt/models/silver/silver_transaction_codes.yml`
- `dbt/models/silver/silver_accounts.sql`, `dbt/models/silver/silver_accounts.yml`
- `dbt/models/silver/silver_quarantine.sql`, `dbt/models/silver/silver_quarantine.yml`
- `dbt/models/silver/silver_transactions.sql`, `dbt/models/silver/silver_transactions.yml`
- `dbt/models/silver/schema.yml`
- `pipeline/silver_promoter.py`
- `sessions/S3_SESSION_LOG.md`, `sessions/S3_VERIFICATION_RECORD.md`

**Session 4 — Gold:**
- `dbt/models/gold/gold_daily_summary.sql`, `dbt/models/gold/gold_daily_summary.yml`
- `dbt/models/gold/gold_weekly_account_summary.sql`, `dbt/models/gold/gold_weekly_account_summary.yml`
- `dbt/models/gold/schema.yml`
- `pipeline/gold_builder.py`
- `sessions/S4_SESSION_LOG.md`, `sessions/S4_VERIFICATION_RECORD.md`

**Session 5 — Incremental:**
- `pipeline/pipeline_incremental.py`
- `pipeline/pipeline_historical.py` (extended to full Bronze→Silver→Gold→watermark)
- `sessions/S5_SESSION_LOG.md`, `sessions/S5_VERIFICATION_RECORD.md`

**Session 6 — Verification:**
- `sessions/S6_SESSION_LOG.md`, `sessions/S6_VERIFICATION_RECORD.md`
- `verification/VERIFICATION_CHECKLIST.md`
- `verification/REGRESSION_SUITE.sh`

**CC must not:**
- Modify any file under `docs/` except placing `docs/Claude.md` in Task 1.1
- Modify `docs/ARCHITECTURE.md`, `docs/INVARIANTS.md`, `docs/EXECUTION_PLAN.md`, `docs/PHASE4_GATE_RECORD.md`
- Modify any file under `brief/`
- Create files outside the per-session permitted list above
- Write transformation logic in Python modules — dbt models only for Silver and Gold
- Write to or modify `pipeline/run_log.parquet` from any module other than `pipeline/run_logger.py`

**Conflict rule:** If a task prompt conflicts with an invariant, the invariant wins. Flag the conflict immediately — never resolve silently.

---

## 4. Fixed Stack

| Component | Version / Detail |
|---|---|
| Python | 3.11 |
| dbt-core | 1.7.x |
| dbt-duckdb adapter | 1.7.x |
| DuckDB (Python binding) | Pin to match dbt-duckdb 1.7.x |
| pyarrow | Latest compatible with Python 3.11 |
| pandas | Latest compatible with Python 3.11 |
| DuckDB deployment | Embedded — no separate server process |
| Storage | Parquet files on local filesystem |
| Orchestration | Docker Compose — all services run locally |
| Source data | Static CSV files in `source/` — read-only at runtime |
| Bronze ingestion | Python + DuckDB directly — dbt not used |
| Silver and Gold | dbt models exclusively |
| Run log and control table | Parquet files at `pipeline/run_log.parquet` and `pipeline/control.parquet` |
| DuckDB catalog file | `pipeline/dbt_catalog.duckdb` |
| Pipeline entry points | `pipeline/pipeline_historical.py` and `pipeline/pipeline_incremental.py` |
| `_pipeline_run_id` format | UUIDv4 string generated at invocation start (OQ-3) |
| Container working directory | `/app` |
| Source mount | `source/` → `/app/source` READ-ONLY |
| Atomic rename constraint | `silver/` and `silver_temp/` must share the same filesystem/mount parent (Decision 4) |

No environment variables are required for the fixed stack configuration. All paths are derived from bind mounts at container startup.

---

## 5. Rules

**Rule 1:** All file references use full paths from repo root — never bare filenames.

**Rule 2:** All files inside any enhancement package carry their ENH-NNN prefix — no exceptions.

**Rule 3:** Any file not in the mandatory set for its directory and not registered in PROJECT_MANIFEST.md must not be read by CC as authoritative input. CC flags unregistered files and reports them to the engineer before proceeding.
