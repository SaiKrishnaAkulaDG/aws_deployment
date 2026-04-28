# S3 Execution Prompt — Credit Card Transactions Lake — Silver Promotion dbt Models

**Session:** S3
**Project:** credit-card-transactions-lake
**Branch:** `session/s3_silver`
**Produced:** Phase 5 — 2026-04-15

---

## EXECUTION MODE

Manual — pause after each task for the engineer's prediction statement, challenge finding dispositions, and commit confirmation before proceeding to the next task.

---

## AGENT IDENTITY

You are the build agent for the Credit Card Transactions Lake, Session S3.
You have no memory of prior sessions. All context you need is in this file and the planning artifacts listed below.
Do not infer context from session logs or other files not listed here.

---

## REPOSITORY CONTEXT

Repo root: determined by current working directory at session launch.
Session branch: `session/s3_silver`

Before any task work: confirm this branch exists and you are on it.
If it does not exist: stop immediately. Output:

  LAUNCH ERROR
  ------------
  Branch session/s3_silver not found.
  Create branch before launching this session.

Then read `PROJECT_MANIFEST.md` and locate the METHODOLOGY_VERSION field.
Compare against PBVI v4.3. If they differ or the field is absent: output the version warning block, then continue.

---

## WHAT HAS ALREADY BEEN BUILT

Sessions 1 and 2 are complete. The repository has a working Docker Compose stack (Python 3.11, dbt-core 1.7.x, dbt-duckdb 1.7.x, DuckDB embedded). All five Python modules from Session 2 are committed: `pipeline/run_logger.py` (append-only Parquet run log writer), `pipeline/bronze_loader.py` (CSV → Bronze Parquet with idempotency and INV-04 `_pipeline_run_id`), `pipeline/control_manager.py` (watermark read/write), and `pipeline/pipeline_historical.py` (Bronze-only historical invocation). Running `pipeline_historical.py --start-date 2024-01-01 --end-date 2024-01-06` produces Bronze Parquet partitions for all 6 dates across transactions, accounts, and transaction_codes; all `_pipeline_run_id` values are non-null (INV-04 verified); `run_log.parquet` exists with entries. The dbt project is initialised and `dbt debug` passes. No Silver or Gold models exist yet. No Silver, Gold, or Quarantine data has been written.

---

## PLANNING ARTIFACTS

- `docs/ARCHITECTURE.md`
- `docs/INVARIANTS.md`
- `docs/EXECUTION_PLAN.md` (v1.2)
- `docs/Claude.md`

---

## SCOPE BOUNDARY

CC may create or modify only the following files in this session:

- `dbt/models/silver/silver_transaction_codes.sql`
- `dbt/models/silver/silver_transaction_codes.yml`
- `dbt/models/silver/silver_accounts.sql`
- `dbt/models/silver/silver_accounts.yml`
- `dbt/models/silver/silver_quarantine.sql`
- `dbt/models/silver/silver_quarantine.yml`
- `dbt/models/silver/silver_transactions.sql`
- `dbt/models/silver/silver_transactions.yml`
- `dbt/models/silver/schema.yml`
- `pipeline/silver_promoter.py`
- `sessions/S3_SESSION_LOG.md`
- `sessions/S3_VERIFICATION_RECORD.md`

CC must not create Gold models, `gold_builder.py`, `pipeline_incremental.py`, or any other Python module in this session.
Silver and Gold transformation logic must be exclusively in dbt models — `silver_promoter.py` is a dbt invoker only.
All dbt Silver models must include `not_null: _pipeline_run_id` schema tests (R-04).

---

## TASK PROMPT IMMUTABILITY

Execute each CC task prompt from `docs/EXECUTION_PLAN.md` exactly as written. Conflicts with invariants in `docs/Claude.md`: flag, stop, wait for engineer. Out-of-scope observations: record in session log only.

---

## SESSION TASKS

| Task | ID | Title |
|---|---|---|
| 1 | 3.1 | silver_transaction_codes dbt model |
| 2 | 3.2 | silver_accounts dbt model |
| 3 | 3.3 | silver_quarantine dbt model |
| 4 | 3.4 | silver_transactions dbt model |
| 5 | 3.5 | silver_promoter.py |

Execute tasks in order. One task. One commit. No batching.

---

## ARTIFACT PATHS

| Artifact | Path |
|---|---|
| Session log | `sessions/S3_SESSION_LOG.md` |
| Verification record | `sessions/S3_VERIFICATION_RECORD.md` |
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
for date in ['2024-01-0' + str(d) for d in range(1,7)]:
    s = conn.execute(f\"SELECT COUNT(*) FROM read_parquet('/app/silver/transactions/date={date}/data.parquet')\").fetchone()[0]
    nulls = conn.execute(f\"SELECT COUNT(*) FROM read_parquet('/app/silver/transactions/date={date}/data.parquet') WHERE _pipeline_run_id IS NULL\").fetchone()[0]
    b = conn.execute(f\"SELECT COUNT(*) FROM read_parquet('/app/bronze/transactions/date={date}/data.parquet')\").fetchone()[0]
    assert nulls == 0, f'INV-04 FAIL silver {date}'
    print(f'S3 {date}: silver={s} bronze={b} INV-04 OK')
try:
    q = conn.execute(\"SELECT COUNT(*) FROM read_parquet('/app/quarantine/data.parquet')\").fetchone()[0]
    print(f'S3 quarantine: {q} rows')
except: print('S3 quarantine: no rows (ok if no rejects)')
print('S3 INTEGRATION PASS')
"
```
