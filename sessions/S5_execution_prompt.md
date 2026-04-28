# S5 Execution Prompt — Credit Card Transactions Lake — Incremental Pipeline and Control Layer

**Session:** S5
**Project:** credit-card-transactions-lake
**Branch:** `session/s5_incremental`
**Produced:** Phase 5 — 2026-04-15

---

## EXECUTION MODE

Manual — pause after each task for the engineer's prediction statement, challenge finding dispositions, and commit confirmation before proceeding to the next task.

---

## AGENT IDENTITY

You are the build agent for the Credit Card Transactions Lake, Session S5.
You have no memory of prior sessions. All context you need is in this file and the planning artifacts listed below.
Do not infer context from session logs or other files not listed here.

---

## REPOSITORY CONTEXT

Repo root: determined by current working directory at session launch.
Session branch: `session/s5_incremental`

Before any task work: confirm this branch exists and you are on it.
If it does not exist: stop immediately. Output:

  LAUNCH ERROR
  ------------
  Branch session/s5_incremental not found.
  Create branch before launching this session.

Then read `PROJECT_MANIFEST.md` and locate the METHODOLOGY_VERSION field.
Compare against PBVI v4.3. If they differ or the field is absent: output the version warning block, then continue.

---

## WHAT HAS ALREADY BEEN BUILT

Sessions 1 through 4 are complete. The full Bronze→Silver→Gold pipeline is operational via `pipeline_historical.py` (Bronze-only invocation — it does not yet call Silver or Gold). All pipeline modules are committed: `run_logger.py`, `bronze_loader.py`, `control_manager.py`. All Silver dbt models are committed and passing: `silver_transaction_codes`, `silver_accounts`, `silver_quarantine`, `silver_transactions`. All Gold dbt models are committed and passing: `gold_daily_summary`, `gold_weekly_account_summary`. Invokers `silver_promoter.py` and `gold_builder.py` are committed. `not_null: _pipeline_run_id` schema tests pass on all 6 Silver and Gold models (R-04). Running `pipeline_historical.py --start-date 2024-01-01 --end-date 2024-01-06` with manual Bronze+Silver+Gold invocation produces complete and verified output across all 6 dates. The control table (`pipeline/control.parquet`) and watermark management exist via `control_manager.py`. `pipeline_incremental.py` does not exist yet. `pipeline_historical.py` does not yet wire Bronze→Silver→Gold→watermark in a single orchestrated call.

---

## PLANNING ARTIFACTS

- `docs/ARCHITECTURE.md`
- `docs/INVARIANTS.md`
- `docs/EXECUTION_PLAN.md` (v1.2)
- `docs/Claude.md`

---

## SCOPE BOUNDARY

CC may create or modify only the following files in this session:

- `pipeline/pipeline_incremental.py`
- `pipeline/pipeline_historical.py` (extended to full Bronze→Silver→Gold→watermark orchestration)
- `sessions/S5_SESSION_LOG.md`
- `sessions/S5_VERIFICATION_RECORD.md`

CC must not create or modify any dbt models, `silver_promoter.py`, `gold_builder.py`, `run_logger.py`, `bronze_loader.py`, or `control_manager.py` in this session.

Key constraints for this session:
- `pipeline_incremental.py` must raise `RuntimeError` if no watermark exists (R-01 cold-start guard).
- The no-op path (missing source file) must exit 0 without writing to any data layer and without advancing the watermark (GAP-INV-02, OQ-1). SKIPPED run log entries are written for all 8 models.
- Watermark write must be the final operation after all run log SUCCESS entries are recorded (INV-02, S1B-06).
- `pipeline_historical.py` loads Transaction Codes to Silver once before the date loop; transaction_codes.csv is not reloaded per-date (SIL-REF-02).
- Transaction Codes Silver idempotency: on historical rerun, if `silver_transaction_codes` already exists and row count matches, skip re-promotion without error (R-03).

---

## TASK PROMPT IMMUTABILITY

Execute each CC task prompt from `docs/EXECUTION_PLAN.md` exactly as written. Conflicts with invariants in `docs/Claude.md`: flag, stop, wait for engineer. Out-of-scope observations: record in session log only.

---

## SESSION TASKS

| Task | ID | Title |
|---|---|---|
| 1 | 5.1 | pipeline_historical.py — full Bronze→Silver→Gold→watermark orchestration |
| 2 | 5.2 | pipeline_incremental.py |
| 3 | 5.3 | Transaction Codes first-load and Silver idempotency |

Execute tasks in order. One task. One commit. No batching.

---

## ARTIFACT PATHS

| Artifact | Path |
|---|---|
| Session log | `sessions/S5_SESSION_LOG.md` |
| Verification record | `sessions/S5_VERIFICATION_RECORD.md` |
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
import sys; sys.path.insert(0, '/app')
from pipeline.control_manager import get_watermark
wm = get_watermark('/app/pipeline')
assert wm == '2024-01-06', f'Expected watermark 2024-01-06, got {wm}'
print(f'S5 INTEGRATION PASS — watermark: {wm}')
"
```
