# S2 Execution Prompt — Credit Card Transactions Lake — Bronze Ingestion

**Session:** S2
**Project:** credit-card-transactions-lake
**Branch:** `session/s2_bronze`
**Produced:** Phase 5 — 2026-04-15

---

## EXECUTION MODE

Manual — pause after each task for the engineer's prediction statement, challenge finding dispositions, and commit confirmation before proceeding to the next task.

---

## AGENT IDENTITY

You are the build agent for the Credit Card Transactions Lake, Session S2.
You have no memory of prior sessions. All context you need is in this file and the planning artifacts listed below.
Do not infer context from session logs or other files not listed here.

---

## REPOSITORY CONTEXT

Repo root: determined by current working directory at session launch.
Session branch: `session/s2_bronze`

Before any task work: confirm this branch exists and you are on it.
If it does not exist: stop immediately. Output:

  LAUNCH ERROR
  ------------
  Branch session/s2_bronze not found.
  Create branch before launching this session.

Then read `PROJECT_MANIFEST.md` and locate the METHODOLOGY_VERSION field.
Compare against PBVI v4.3. If they differ or the field is absent: output the version warning block, then continue.

---

## WHAT HAS ALREADY BEEN BUILT

Session 1 is complete and committed on `session/s1_scaffold`. The repository has all PBVI and project directories, a fully populated PROJECT_MANIFEST.md (METHODOLOGY_VERSION: PBVI v4.3), Docker Compose stack with Python 3.11 / dbt-core 1.7.x / dbt-duckdb 1.7.x / DuckDB embedded, a dbt project initialised with `dbt debug` passing, six days of seed transaction CSVs and six days of accounts CSVs in `source/`, `source/transaction_codes.csv`, and all five `tools/` scripts. `docker compose build` and `./tools/challenge.sh --check` both exit 0. No Python pipeline modules exist yet. No Bronze, Silver, or Gold data has been written.

---

## PLANNING ARTIFACTS

- `docs/ARCHITECTURE.md`
- `docs/INVARIANTS.md`
- `docs/EXECUTION_PLAN.md` (v1.2)
- `docs/Claude.md`

---

## SCOPE BOUNDARY

CC may create or modify only the following files in this session:

- `pipeline/run_logger.py`
- `pipeline/bronze_loader.py`
- `pipeline/control_manager.py`
- `pipeline/pipeline_historical.py` (Bronze-only invocation at this stage — does not call Silver or Gold)
- `sessions/S2_SESSION_LOG.md`
- `sessions/S2_VERIFICATION_RECORD.md`

CC must not create Silver or Gold modules, dbt models, or `pipeline_incremental.py` in this session.
CC must not write transformation logic in Python — Bronze ingestion reads CSV and writes Parquet only.

---

## TASK PROMPT IMMUTABILITY

Execute each CC task prompt from `docs/EXECUTION_PLAN.md` exactly as written. Conflicts with invariants in `docs/Claude.md`: flag, stop, wait for engineer. Out-of-scope observations: record in session log only.

---

## SESSION TASKS

| Task | ID | Title |
|---|---|---|
| 1 | 2.1 | run_logger.py |
| 2 | 2.2 | bronze_loader.py |
| 3 | 2.3 | control_manager.py |
| 4 | 2.4 | pipeline_historical.py (Bronze invocation) |

Execute tasks in order. One task. One commit. No batching.

---

## ARTIFACT PATHS

| Artifact | Path |
|---|---|
| Session log | `sessions/S2_SESSION_LOG.md` |
| Verification record | `sessions/S2_VERIFICATION_RECORD.md` |
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
    rows = conn.execute(f\"SELECT COUNT(*) FROM read_parquet('/app/bronze/transactions/date={date}/data.parquet')\").fetchone()[0]
    nulls = conn.execute(f\"SELECT COUNT(*) FROM read_parquet('/app/bronze/transactions/date={date}/data.parquet') WHERE _pipeline_run_id IS NULL\").fetchone()[0]
    assert rows > 0 and nulls == 0, f'FAIL {date}'
    print(f'S2 {date}: {rows} rows, INV-04 OK')
log = conn.execute(\"SELECT COUNT(*) FROM read_parquet('/app/pipeline/run_log.parquet')\").fetchone()[0]
assert log > 0
print(f'S2 INTEGRATION PASS — run_log: {log} entries')
"
```
