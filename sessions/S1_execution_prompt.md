# S1 Execution Prompt — Credit Card Transactions Lake — Project Scaffold and Infrastructure

**Session:** S1
**Project:** credit-card-transactions-lake
**Branch:** `session/s1_scaffold`
**Produced:** Phase 5 — 2026-04-15

---

## EXECUTION MODE

Manual — pause after each task for the engineer's prediction statement, challenge finding dispositions, and commit confirmation before proceeding to the next task.

---

## AGENT IDENTITY

You are the build agent for the Credit Card Transactions Lake, Session S1.
You have no memory of prior sessions. All context you need is in this file and the planning artifacts listed below.
Do not infer context from session logs or other files not listed here.

---

## REPOSITORY CONTEXT

Repo root: determined by current working directory at session launch.
Session branch: `session/s1_scaffold`

Before any task work: confirm this branch exists and you are on it.
If it does not exist: stop immediately. Output:

  LAUNCH ERROR
  ------------
  Branch session/s1_scaffold not found.
  Create branch before launching this session.

Then read `PROJECT_MANIFEST.md` and locate the METHODOLOGY_VERSION field.
Compare it against the loaded PBVI skill's frontmatter version (PBVI v4.3).
If they match: proceed silently.
If they differ or the field is absent: output the following, then continue — do not stop the session.

  METHODOLOGY VERSION WARNING
  ---------------------------
  Skill version:    PBVI v4.3
  Project version:  [value found, or NOT DECLARED]
  Proceeding. Consult BREAKING_CHANGES.md in the DG-Forge repo before continuing.

---

## WHAT HAS ALREADY BEEN BUILT

This is the first session — repository scaffolded, no prior state.

---

## PLANNING ARTIFACTS

Read these files before executing any task. They are the authoritative source of truth.

- `docs/ARCHITECTURE.md` — architecture decisions, data model, out-of-scope boundary
- `docs/INVARIANTS.md` — 53 invariants across 11 groups; GLOBAL invariants are in Claude.md Section 2
- `docs/EXECUTION_PLAN.md` (v1.2) — all task CC prompts, test cases, verification commands
- `docs/Claude.md` — execution contract; Hard Invariants Section 2 applies to every task

---

## SCOPE BOUNDARY

CC may create or modify only the following files in this session:

- All PBVI directories with `.gitkeep`: `brief/`, `docs/`, `docs/prompts/`, `sessions/`, `verification/`, `discovery/`, `discovery/components/`, `enhancements/`, `tools/`
- All project directories with `.gitkeep`: `source/`, `pipeline/`, `bronze/`, `silver/`, `silver_temp/`, `gold/`, `quarantine/`, `dbt/`
- `README.md`, `PROJECT_MANIFEST.md`
- `Dockerfile`, `docker-compose.yml`, `requirements.txt`, `.gitignore`
- `dbt/dbt_project.yml`, `dbt/profiles.yml`, `dbt/models/silver/.gitkeep`, `dbt/models/gold/.gitkeep`
- `source/transaction_codes.csv`, `source/transactions_2024-01-01.csv` through `source/transactions_2024-01-06.csv`, `source/accounts_2024-01-01.csv` through `source/accounts_2024-01-06.csv`
- `tools/launch.sh`, `tools/resume_session.sh`, `tools/resume_challenge.sh`, `tools/challenge.sh`, `tools/monitor.sh`
- `docs/Claude.md` (place only — never modify after placement)
- `sessions/S1_SESSION_LOG.md`, `sessions/S1_VERIFICATION_RECORD.md`

CC must not create application Python modules, Silver/Gold dbt models, or pipeline entry point scripts in this session.

---

## TASK PROMPT IMMUTABILITY

Execute each CC task prompt from `docs/EXECUTION_PLAN.md` exactly as written. If anything in a task prompt appears to conflict with an invariant in `docs/Claude.md`, do not resolve it silently — stop, flag the conflict, and wait for engineer direction. Out-of-scope observations noticed during a task are recorded in the session log under "Out of Scope Observations" — they are not acted on.

---

## SESSION TASKS

| Task | ID | Title |
|---|---|---|
| 1 | 1.1 | Repository Scaffold, PBVI Directory Structure, and Full PROJECT_MANIFEST.md |
| 2 | 1.2 | Docker Compose Stack and Python Environment |
| 3 | 1.3 | dbt Project Initialisation |
| 4 | 1.4 | Source CSV Seed Data |
| 5 | 1.5 | tools/ Scripts |

Execute tasks in order. One task. One commit. No batching.

---

## ARTIFACT PATHS

| Artifact | Path |
|---|---|
| Session log | `sessions/S1_SESSION_LOG.md` |
| Verification record | `sessions/S1_VERIFICATION_RECORD.md` |
| Execution plan (task prompts) | `docs/EXECUTION_PLAN.md` |
| Execution contract | `docs/Claude.md` |

---

## STOP CONDITIONS AND OUTPUT FORMATS

**LAUNCH ERROR** — branch not found: output block above, stop session.

**BLOCKED** — task verification failed, CC cannot resolve without engineer input:
  BLOCKED
  -------
  Task: [ID]
  Reason: [specific failure description]
  Evidence: [verification command output]
  Required: [what the engineer must decide or supply]

**SCOPE VIOLATION** — file outside permitted list modified or created:
  SCOPE VIOLATION
  ---------------
  Task: [ID]
  File: [full path from repo root]
  Action taken: [created | modified | deleted]
  Required: Engineer must review before session proceeds.

**INTEGRATION CHECK** — run at end of session before sign-off:
```bash
docker compose build \
  && docker compose run --rm pipeline python -c "import duckdb; print('duckdb ok')" \
  && docker compose run --rm pipeline dbt debug --project-dir /app/dbt --profiles-dir /app/dbt \
  && bash tools/challenge.sh --check \
  && echo "S1 INTEGRATION PASS"
```
