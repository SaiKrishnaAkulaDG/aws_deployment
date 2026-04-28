# S6 Execution Prompt — Credit Card Transactions Lake — End-to-End Verification

**Session:** S6
**Project:** credit-card-transactions-lake
**Branch:** `session/s6_verification`
**Produced:** Phase 5 — 2026-04-15

---

## EXECUTION MODE

Manual — pause after each task for the engineer's prediction statement, challenge finding dispositions, and commit confirmation before proceeding to the next task.

---

## AGENT IDENTITY

You are the build agent for the Credit Card Transactions Lake, Session S6.
You have no memory of prior sessions. All context you need is in this file and the planning artifacts listed below.
Do not infer context from session logs or other files not listed here.

---

## REPOSITORY CONTEXT

Repo root: determined by current working directory at session launch.
Session branch: `session/s6_verification`

Before any task work: confirm this branch exists and you are on it.
If it does not exist: stop immediately. Output:

  LAUNCH ERROR
  ------------
  Branch session/s6_verification not found.
  Create branch before launching this session.

Then read `PROJECT_MANIFEST.md` and locate the METHODOLOGY_VERSION field.
Compare against PBVI v4.3. If they differ or the field is absent: output the version warning block, then continue.

---

## WHAT HAS ALREADY BEEN BUILT

Sessions 1 through 5 are complete. The full pipeline is operational end-to-end. `pipeline_historical.py` orchestrates Bronze→Silver→Gold→watermark for a date range and advances the watermark only after all layers and run log SUCCESS entries are complete (INV-02). `pipeline_incremental.py` reads watermark+1, processes a single date through the same module layer, raises RuntimeError on cold-start (R-01), and performs a clean no-op exit if the source file is absent (GAP-INV-02). All Silver and Gold dbt models pass `not_null: _pipeline_run_id` schema tests (R-04). Transaction Codes are loaded to Silver once before the historical date loop and are idempotency-safe on rerun (R-03). Running `pipeline_historical.py --start-date 2024-01-01 --end-date 2024-01-06` produces complete Bronze, Silver, Gold, and Quarantine output for all 6 dates with watermark at `2024-01-06`. `source/transactions_2024-01-07.csv` is intentionally absent for the no-op test.

---

## PLANNING ARTIFACTS

- `docs/ARCHITECTURE.md`
- `docs/INVARIANTS.md`
- `docs/EXECUTION_PLAN.md` (v1.2)
- `docs/Claude.md`

---

## SCOPE BOUNDARY

CC may create or modify only the following files in this session:

- `sessions/S6_SESSION_LOG.md`
- `sessions/S6_VERIFICATION_RECORD.md`
- `verification/VERIFICATION_CHECKLIST.md`
- `verification/REGRESSION_SUITE.sh`

CC must not create or modify any Python modules, dbt models, or planning artifacts in this session.
This session is verification-only. No new code is written. All writes are to verification artifacts.

---

## TASK PROMPT IMMUTABILITY

Execute each CC task prompt from `docs/EXECUTION_PLAN.md` exactly as written. Conflicts with invariants in `docs/Claude.md`: flag, stop, wait for engineer. Out-of-scope observations: record in session log only.

---

## SESSION TASKS

| Task | ID | Title |
|---|---|---|
| 1 | 6.1 | Full Historical Run and 53-Invariant Audit |
| 2 | 6.2 | No-Op Path Verification (Date 7) |
| 3 | 6.3 | Idempotency and S1B-02 Cross-Entry-Point Verification |

Execute tasks in order. One task. One commit. No batching.

---

## ARTIFACT PATHS

| Artifact | Path |
|---|---|
| Session log | `sessions/S6_SESSION_LOG.md` |
| Verification record | `sessions/S6_VERIFICATION_RECORD.md` |
| Verification checklist | `verification/VERIFICATION_CHECKLIST.md` |
| Regression suite | `verification/REGRESSION_SUITE.sh` |
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
docker compose run --rm pipeline python -c "
import duckdb; conn = duckdb.connect()
for path, name in [
  ('/app/bronze/transactions/date=2024-01-01/data.parquet', 'bronze'),
  ('/app/silver/transactions/date=2024-01-01/data.parquet', 'silver'),
  ('/app/gold/daily_summary/data.parquet', 'gold'),
]:
    nulls = conn.execute(f\"SELECT COUNT(*) FROM read_parquet('{path}') WHERE _pipeline_run_id IS NULL\").fetchone()[0]
    assert nulls == 0, f'INV-04 FAIL in {name}'
    print(f'INV-04 PASS: {name}')
for date in ['2024-01-0' + str(d) for d in range(1,7)]:
    s = conn.execute(f\"SELECT COUNT(*) FROM read_parquet('/app/silver/transactions/date={date}/data.parquet')\").fetchone()[0]
    b = conn.execute(f\"SELECT COUNT(*) FROM read_parquet('/app/bronze/transactions/date={date}/data.parquet')\").fetchone()[0]
    try: q = conn.execute(f\"SELECT COUNT(*) FROM read_parquet('/app/quarantine/data.parquet') WHERE transaction_date='{date}'\").fetchone()[0]
    except: q = 0
    assert s + q == b, f'SIL-T-01 FAIL {date}'
    print(f'SIL-T-01 PASS {date}')
print('S6 INTEGRATION PASS')
" \
  && bash verification/REGRESSION_SUITE.sh \
  && echo "REGRESSION SUITE PASS"
```

**Phase 8 gate:** Session S6 is the final build session. After engineer sign-off, raise a PR from `session/s6_verification` to `main`. Phase 7 (Session Integration Check) and Phase 8 (System Sign-Off) follow.
