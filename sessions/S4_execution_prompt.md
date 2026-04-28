# S4 Execution Prompt — Credit Card Transactions Lake — Gold Computation dbt Models

**Session:** S4
**Project:** credit-card-transactions-lake
**Branch:** `session/s4_gold`
**Produced:** Phase 5 — 2026-04-15

---

## EXECUTION MODE

Manual — pause after each task for the engineer's prediction statement, challenge finding dispositions, and commit confirmation before proceeding to the next task.

---

## AGENT IDENTITY

You are the build agent for the Credit Card Transactions Lake, Session S4.
You have no memory of prior sessions. All context you need is in this file and the planning artifacts listed below.
Do not infer context from session logs or other files not listed here.

---

## REPOSITORY CONTEXT

Repo root: determined by current working directory at session launch.
Session branch: `session/s4_gold`

Before any task work: confirm this branch exists and you are on it.
If it does not exist: stop immediately. Output:

  LAUNCH ERROR
  ------------
  Branch session/s4_gold not found.
  Create branch before launching this session.

Then read `PROJECT_MANIFEST.md` and locate the METHODOLOGY_VERSION field.
Compare against PBVI v4.3. If they differ or the field is absent: output the version warning block, then continue.

---

## WHAT HAS ALREADY BEEN BUILT

Sessions 1, 2, and 3 are complete. The Docker Compose stack is operational. All Bronze Python modules are committed and verified: `run_logger.py`, `bronze_loader.py`, `control_manager.py`, `pipeline_historical.py` (Bronze-only). All four Silver dbt models are committed and tested: `silver_transaction_codes`, `silver_accounts`, `silver_quarantine`, `silver_transactions` — all with `not_null: _pipeline_run_id` schema tests passing (R-04). `pipeline/silver_promoter.py` is committed and invokes `dbt run --select models/silver/` successfully. Running `pipeline_historical.py --start-date 2024-01-01 --end-date 2024-01-06` produces Bronze and Silver partitions for all 6 dates with zero null `_pipeline_run_id` values; quarantine receives rejected records. Mass conservation (SIL-T-01) is verified for all 6 dates. No Gold models or `gold_builder.py` exist yet.

---

## PLANNING ARTIFACTS

- `docs/ARCHITECTURE.md`
- `docs/INVARIANTS.md`
- `docs/EXECUTION_PLAN.md` (v1.2)
- `docs/Claude.md`

---

## SCOPE BOUNDARY

CC may create or modify only the following files in this session:

- `dbt/models/gold/gold_daily_summary.sql`
- `dbt/models/gold/gold_daily_summary.yml`
- `dbt/models/gold/gold_weekly_account_summary.sql`
- `dbt/models/gold/gold_weekly_account_summary.yml`
- `dbt/models/gold/schema.yml`
- `pipeline/gold_builder.py`
- `sessions/S4_SESSION_LOG.md`
- `sessions/S4_VERIFICATION_RECORD.md`

CC must not create `pipeline_incremental.py` or modify any Silver models in this session.
Gold transformation logic must be exclusively in dbt models — `gold_builder.py` is a dbt invoker only.
All dbt Gold models must include `not_null: _pipeline_run_id` schema tests (R-04).
Gold reads from Silver only — not from Bronze directly (S1B-gold-source).
Gold is fully recomputed on every run — no append (GAP-INV-05).

---

## TASK PROMPT IMMUTABILITY

Execute each CC task prompt from `docs/EXECUTION_PLAN.md` exactly as written. Conflicts with invariants in `docs/Claude.md`: flag, stop, wait for engineer. Out-of-scope observations: record in session log only.

---

## SESSION TASKS

| Task | ID | Title |
|---|---|---|
| 1 | 4.1 | gold_daily_summary dbt model |
| 2 | 4.2 | gold_weekly_account_summary dbt model |
| 3 | 4.3 | gold_builder.py |

Execute tasks in order. One task. One commit. No batching.

---

## ARTIFACT PATHS

| Artifact | Path |
|---|---|
| Session log | `sessions/S4_SESSION_LOG.md` |
| Verification record | `sessions/S4_VERIFICATION_RECORD.md` |
| Execution plan | `docs/EXECUTION_PLAN.md` |
| Execution contract | `docs/Claude.md` |

---

## STOP CONDITIONS AND OUTPUT FORMATS

**LAUNCH ERROR** — branch not found: output block above, stop session.

**BLOCKED:**
  BLOCKED
  -------
  Task: [ID]
  Reason: [specific failure description]
  Evidence: [verification command output]
  Required: [what the engineer must decide or supply]

**SCOPE VIOLATION:**
  SCOPE VIOLATION
  ---------------
  Task: [ID]
  File: [full path from repo root]
  Action taken: [created | modified | deleted]
  Required: Engineer must review before session proceeds.

**INTEGRATION CHECK** — run at end of session before sign-off:
```bash
docker compose run --rm pipeline python pipeline/pipeline_historical.py \
    --start-date 2024-01-01 --end-date 2024-01-06 \
  && docker compose run --rm pipeline python -c "
import duckdb; conn = duckdb.connect()
daily = conn.execute(\"SELECT COUNT(*) FROM read_parquet('/app/gold/daily_summary/data.parquet')\").fetchone()[0]
weekly = conn.execute(\"SELECT COUNT(*) FROM read_parquet('/app/gold/weekly_account_summary/data.parquet')\").fetchone()[0]
nulls_d = conn.execute(\"SELECT COUNT(*) FROM read_parquet('/app/gold/daily_summary/data.parquet') WHERE _pipeline_run_id IS NULL\").fetchone()[0]
nulls_w = conn.execute(\"SELECT COUNT(*) FROM read_parquet('/app/gold/weekly_account_summary/data.parquet') WHERE _pipeline_run_id IS NULL\").fetchone()[0]
assert nulls_d == 0 and nulls_w == 0, 'INV-04 FAIL in Gold'
print(f'S4 INTEGRATION PASS — daily_summary: {daily} rows, weekly_account_summary: {weekly} rows, INV-04 OK')
"
```
