# EXECUTION_PLAN.md — Credit Card Transactions Lake

## Changelog
| Version | Date | Author | Change |
|---|---|---|---|
| v1.0 | 2026-04-15 | Krishna | Greenfield — Phase 3 output. |
| v1.1 | 2026-04-15 | Krishna | Two gaps closed: (1) Task 1.1 expanded — PROJECT_MANIFEST.md now pre-registers all expected project files with PENDING status; Non-Standard Registered Files and Directories sections populated. (2) New Task 1.5 added — tools/ scripts. Session 1 task count updated to 5. |
| v1.2 | 2026-04-15 | Krishna | Phase 4 RESOLVE fixes: R-01 — cold-start guard added to Task 2.4 CC prompt and test cases; TC-cold-start added to Tasks 2.4 and 5.2. R-02 — mount parity probe added to Task 1.2 verification command. R-03 — Transaction Codes Silver idempotency handling added to Task 5.3 CC prompt and new TC-5 rerun test case. R-04 — `not_null: _pipeline_run_id` dbt schema test added to Tasks 3.1, 3.2, 3.3, 3.4, 4.1, 4.2. |

---

## Phase 3 Pre-Flight Checks

### Methodology Version Check

Skill version: PBVI v4.3
Project METHODOLOGY_VERSION: NOT DECLARED (project predates FW-001)
> ⚠ METHODOLOGY VERSION WARNING — project was initialised before the METHODOLOGY_VERSION
> field was introduced (FW-001). Proceeding without stopping. Add
> `METHODOLOGY_VERSION: PBVI v4.3 / BCE v1.7` to PROJECT_MANIFEST.md at Task 1.1.

---

### Requirements Traceability Check

| Requirement / Behaviour | Traced To | Status |
|---|---|---|
| Medallion architecture (Bronze → Silver → Gold) | Decision 1 — Layered Module Architecture | ✅ TRACED |
| Daily CSV ingestion into Bronze | Decision 1 — bronze_loader.py; Data Model Section 8 | ✅ TRACED |
| Bronze immutability / raw preservation | INV-01a, INV-08, INV-09 | ✅ TRACED |
| Bronze idempotency via row count check | Decision 3 | ✅ TRACED |
| Silver transformation via dbt exclusively | S1B-dbt-silver-gold; Decision 1 | ✅ TRACED |
| Silver transaction validation (NULL, amount, code, channel) | SIL-T-07; Data Model Section 8 | ✅ TRACED |
| Silver deduplication on transaction_id | SIL-T-02, GAP-INV-07 | ✅ TRACED |
| Sign assignment via transaction_codes.debit_credit_indicator | SIL-T-05, SIL-T-06 (impl guidance) | ✅ TRACED |
| Silver Accounts upsert (latest state per account_id) | SIL-A-01; Data Model Section 8 | ✅ TRACED |
| Quarantine layer with rejection reasons | SIL-Q-01, SIL-Q-02; Data Model Section 8 | ✅ TRACED |
| Transaction Codes prerequisite guard | Decision 6; SIL-REF-01 | ✅ TRACED |
| Gold Daily Summary aggregation | GOLD-D-01 through GOLD-D-04; Data Model | ✅ TRACED |
| Gold Weekly Account Summary with closing balance | GOLD-W-01 through GOLD-W-05; Data Model | ✅ TRACED |
| Historical pipeline with date-range loop | Decision 2; pipeline_historical.py | ✅ TRACED |
| Incremental pipeline with watermark+1 | Decision 2; pipeline_incremental.py | ✅ TRACED |
| Watermark advances only on full success | INV-02; Decision 7; control_manager.py | ✅ TRACED |
| No-op on missing file — Option A | OQ-1; GAP-INV-02 | ✅ TRACED |
| SKIPPED run log on no-op | OQ-2; INV-05b | ✅ TRACED |
| run_id as UUIDv4 | OQ-3; INV-04 | ✅ TRACED |
| Run log owned by run_logger.py exclusively | Decision 5; RL-01a | ✅ TRACED |
| Audit trail _pipeline_run_id in every layer | INV-04 (GLOBAL) | ✅ TRACED |
| Docker Compose local stack | Fixed Stack | ✅ TRACED |
| DuckDB embedded — no server | Fixed Stack; INV-07 | ✅ TRACED |
| No external service calls | INV-07 impl guidance | ✅ TRACED |
| source/ read-only | INV-06; Task 1.2 read-only mount | ✅ TRACED |
| All outputs Parquet | S1B-parquet | ✅ TRACED |
| Atomic Silver overwrite same mount | Decision 4; Task 1.2 | ✅ TRACED |
| Cross-entry-point equivalence | S1B-02 | ✅ TRACED |
| End-to-end 53-invariant verification | Session 6 | ✅ TRACED |
| No-op date 7 | Task 1.4 (seed), Task 6.2 | ✅ TRACED |
| Idempotency verification | Task 6.3 | ✅ TRACED |
| Backfill — out of scope | ARCHITECTURE.md Section 9 | ✅ TRACED |
| SCD Type 2 — out of scope | ARCHITECTURE.md Section 9 | ✅ TRACED |
| Schema evolution — out of scope | S1B-schema-evolution | ✅ TRACED |
| Encryption / monitoring / serving API — out of scope | ARCHITECTURE.md Section 9 | ✅ TRACED |
| Transaction Codes Silver idempotency on historical rerun | Task 5.3 (v1.2) | ✅ TRACED (R-03) |
| Incremental cold-start guard | Task 2.4 (v1.2) | ✅ TRACED (R-01) |
| Mount parity verification | Task 1.2 (v1.2) | ✅ TRACED (R-02) |
| INV-04 dbt build-time enforcement | Tasks 3.1–3.4, 4.1–4.2 (v1.2) | ✅ TRACED (R-04) |

**Zero gaps.**

---

### Open Questions Status

All three open questions resolved before Phase 2 sign-off on 2026-04-10. No new open
questions surfaced during Phase 3 or Phase 4.

---

## Resolved Decisions Table

| # | Question | Resolution | Resolved |
|---|---|---|---|
| OQ-1 | Delayed vs missing file — operational handling | Option A: both treated as no-op. Pipeline exits without writing to any layer, without advancing watermark. | 2026-04-10 |
| OQ-2 | Run log SKIPPED entry on no-op | SKIPPED entries written for all models on every no-op invocation. run_id for a SKIPPED invocation must not appear in any data layer. | 2026-04-10 |
| OQ-3 | _pipeline_run_id format | UUIDv4 generated by pipeline entry point at invocation start. | 2026-04-10 |

---

## Pipeline Entry Point Design

Two separate Python entry points — both orchestrate through shared module layer:

```
docker compose run pipeline python pipeline/pipeline_historical.py \
    --start-date 2024-01-01 --end-date 2024-01-07

docker compose run pipeline python pipeline/pipeline_incremental.py
```

- `pipeline_historical.py` — iterates a date range in ascending order (GAP-INV-01a),
  processes each date in sequence (GAP-INV-01b), loads Transaction Codes to Silver once
  before the date loop.
- `pipeline_incremental.py` — reads watermark from control table, derives
  watermark + 1, processes that single date. Exits without write if no source file.
  Raises RuntimeError if no watermark exists (R-01 cold-start guard).
- Both entry points import and call the same module layer.
- S1B-02 satisfied: identical inputs produce identical outputs regardless of entry point.

---

## Session Overview Table

| Session | Title | Goal | Tasks | Est. Duration |
|---|---|---|---|---|
| S1 | Project Scaffold and Infrastructure | Runnable Docker environment with directory structure, tools/ scripts, full PROJECT_MANIFEST.md registry, dbt project, source data, and planning artifacts committed | 5 | 120 min |
| S2 | Bronze Ingestion | Historical Bronze ingestion for all source entities with idempotency, row count verification, schema validation, and run log integration | 4 | 90 min |
| S3 | Silver Promotion dbt Models | All Silver dbt models: transaction_codes, accounts, quarantine, transactions | 5 | 120 min |
| S4 | Gold Computation dbt Models | Gold daily_summary and weekly_account_summary dbt models; gold_builder.py invoker | 3 | 75 min |
| S5 | Incremental Pipeline and Control Layer | pipeline_incremental.py; full orchestration Bronze→Silver→Gold→watermark; transaction_codes first-load | 3 | 75 min |
| S6 | End-to-End Verification | Historical full run across all 6 dates; incremental no-op for date 7; mass conservation; invariant audit | 3 | 60 min |

**Total tasks: 23**

---

## Session 1 — Project Scaffold and Infrastructure

**Session goal:** A committed repository with all directories, full PROJECT_MANIFEST.md
registry, five tools/ scripts, Docker Compose stack running, dbt project initialised,
source CSV files seeded, and all planning documents placed in `docs/`. Running
`docker compose build`, `docker compose run pipeline dbt debug`, and
`./tools/challenge.sh --check` all exit 0.

**Branch:** `session/s1_scaffold`

**Integration check:**
```bash
docker compose build \
  && docker compose run --rm pipeline python -c "import duckdb; print('duckdb ok')" \
  && docker compose run --rm pipeline dbt debug --project-dir /app/dbt --profiles-dir /app/dbt \
  && bash tools/challenge.sh --check \
  && echo "S1 INTEGRATION PASS"
```

---

### Task 1.1 — Repository Scaffold, PBVI Directory Structure, and Full PROJECT_MANIFEST.md

**Description:**
Creates the full repository directory tree from scratch. Produces all PBVI directories
with .gitkeep files, all project source directories, README.md, and a fully populated
PROJECT_MANIFEST.md that pre-registers every expected project file with status PENDING.
Places planning documents in `docs/`. No application code created here.

**Input:** None — greenfield.
**Output:** Committed repository with all directories, README.md, and fully populated PROJECT_MANIFEST.md.

**CC Prompt:**
```
You are building the Credit Card Transactions Lake repository from scratch.
No source repository exists — create everything in the current working directory.

STEP 1 — Create PBVI mandatory directories with .gitkeep files:
  brief/.gitkeep, docs/.gitkeep, docs/prompts/.gitkeep, sessions/.gitkeep,
  verification/.gitkeep, discovery/.gitkeep, discovery/components/.gitkeep,
  enhancements/.gitkeep, tools/.gitkeep

STEP 2 — Create project source directories with .gitkeep files:
  source/.gitkeep, pipeline/.gitkeep, bronze/.gitkeep, silver/.gitkeep,
  silver_temp/.gitkeep, gold/.gitkeep, quarantine/.gitkeep, dbt/.gitkeep

STEP 3 — Create README.md at repo root with project description, entry point commands,
  and methodology version: PBVI v4.3 / BCE v1.7.

STEP 4 — Create fully populated PROJECT_MANIFEST.md at repo root.
  METHODOLOGY_VERSION: PBVI v4.3 / BCE v1.7
  Pre-register ALL expected files with status PENDING.
  Include Core Documents, Non-Standard Registered Files, Non-Standard Registered
  Directories, Session Logs, Verification Records, Verification Checklists,
  Discovery Artifacts, Enhancement Registry, Structural Exceptions sections.
  Mark docs/ARCHITECTURE.md, docs/INVARIANTS.md, docs/EXECUTION_PLAN.md as PRESENT.

STEP 5 — Copy planning documents into docs/:
  docs/ARCHITECTURE.md, docs/INVARIANTS.md, docs/EXECUTION_PLAN.md, docs/PHASE4_GATE_RECORD.md

STEP 6 — Initialise git and commit:
  git init
  git add -A
  git commit -m "1.1 — Repo scaffold: PBVI directories, full PROJECT_MANIFEST.md registry, planning artifacts"

CONSTRAINTS:
- Do not create any application code, Docker files, or dbt files in this task.
- Do not create tools/ scripts in this task — that is Task 1.5.
- No external service calls of any kind.
```

**Test Cases:**

| Case | Scenario | Expected |
|---|---|---|
| TC-1 | All PBVI directories present | brief/, docs/, sessions/, verification/, discovery/, enhancements/, tools/ all exist |
| TC-2 | All project source directories present | source/, pipeline/, bronze/, silver/, silver_temp/, gold/, quarantine/, dbt/ all exist |
| TC-3 | README.md at repo root | File present, contains entry point commands |
| TC-4 | PROJECT_MANIFEST.md — METHODOLOGY_VERSION present | `grep "METHODOLOGY_VERSION: PBVI v4.3" PROJECT_MANIFEST.md` matches |
| TC-5 | PROJECT_MANIFEST.md — pipeline modules registered | All 7 pipeline .py files listed with PENDING status |
| TC-6 | PROJECT_MANIFEST.md — tools/ scripts registered | All 5 tools/ scripts listed with PENDING status |
| TC-7 | PROJECT_MANIFEST.md — Non-Standard Directories registered | source/, pipeline/, bronze/, silver/, silver_temp/, gold/, quarantine/, dbt/ all listed |
| TC-8 | docs/ contains planning artifacts | ARCHITECTURE.md, INVARIANTS.md, EXECUTION_PLAN.md, PHASE4_GATE_RECORD.md all present |
| TC-9 | Git repo initialised with initial commit | `git log --oneline` shows exactly one commit |

**Verification command:**
```bash
for d in brief docs docs/prompts sessions verification discovery discovery/components enhancements tools source pipeline bronze silver silver_temp gold quarantine dbt; do
  [ -d "$d" ] && echo "OK: $d" || echo "MISSING: $d"
done \
  && [ -f README.md ] && echo "OK: README.md" \
  && [ -f PROJECT_MANIFEST.md ] && echo "OK: PROJECT_MANIFEST.md" \
  && grep "METHODOLOGY_VERSION: PBVI v4.3" PROJECT_MANIFEST.md && echo "OK: METHODOLOGY_VERSION" \
  && grep "pipeline/run_logger.py" PROJECT_MANIFEST.md && echo "OK: run_logger registered" \
  && grep "tools/challenge.sh" PROJECT_MANIFEST.md && echo "OK: challenge.sh registered" \
  && [ -f docs/PHASE4_GATE_RECORD.md ] && echo "OK: PHASE4_GATE_RECORD.md" \
  && git log --oneline | head -3
```

**Invariant enforcement:** None — structure only, no data layer writes.

**Regression classification:** NOT-REGRESSION-RELEVANT — directory structure and registry; no runtime behaviour.

---

### Task 1.2 — Docker Compose Stack and Python Environment

**Description:**
Creates `docker-compose.yml`, `Dockerfile`, and `requirements.txt`. Python 3.11,
dbt-core 1.7.x, dbt-duckdb 1.7.x, duckdb Python binding, and pyarrow installed.
`source/` mounted read-only. `silver/` and `silver_temp/` on same bind mount parent
to satisfy Decision 4 atomic rename constraint.

**R-02 fix (v1.2):** Verification command extended with mount parity probe to confirm
`silver/` and `silver_temp/` are on the same filesystem before Session 3 begins.

**Input:** Directory structure from Task 1.1.
**Output:** `docker-compose.yml`, `Dockerfile`, `requirements.txt`, `.gitignore` committed. `docker compose build` exits 0. Mount parity probe passes.

**CC Prompt:**
```
Create the Docker Compose stack for the Credit Card Transactions Lake pipeline.

REQUIREMENTS:
- Python 3.11 base image
- Install: dbt-core==1.7.*, dbt-duckdb==1.7.*, duckdb (matching dbt-duckdb pin),
  pyarrow, pandas
- Single service named "pipeline"
- Working directory in container: /app

BIND MOUNTS — all host paths relative to repo root, all container paths under /app:
  source/      → /app/source      (READ-ONLY — INV-06: source files never modified)
  pipeline/    → /app/pipeline
  bronze/      → /app/bronze
  silver/      → /app/silver
  silver_temp/ → /app/silver_temp
  gold/        → /app/gold
  quarantine/  → /app/quarantine
  dbt/         → /app/dbt

CRITICAL — Decision 4 atomic rename constraint (Implementation Guidance):
silver/ and silver_temp/ MUST be on the same Docker volume / filesystem mount.
Silver re-promotion uses os.rename() which requires source and destination to be
on the same mount point. Use bind mounts to the same host directory parent.
Incorrect volume configuration will cause OSError at runtime.

CREATE FILES:
1. Dockerfile
2. docker-compose.yml
3. requirements.txt
4. .gitignore:
   - Exclude runtime Parquet files: pipeline/*.parquet, bronze/**/*.parquet,
     silver/**/*.parquet, silver_temp/**/*.parquet, gold/**/*.parquet,
     quarantine/**/*.parquet, pipeline/dbt_catalog.duckdb
   - Keep .gitkeep files tracked: !**/.gitkeep

Do NOT create any Python application files in this task.

CONSTRAINTS:
- DuckDB is embedded — no separate DuckDB server process (Fixed Stack).
- No external service calls (INV-07).
- Each function must have a single stateable purpose.
  Conditional nesting exceeding two levels is a structural violation.

After creating files:
  git add -A
  git commit -m "1.2 — Docker Compose stack: Python 3.11, dbt-core 1.7.x, dbt-duckdb 1.7.x"
```

**Test Cases:**

| Case | Scenario | Expected |
|---|---|---|
| TC-1 | `docker compose build` | Exit 0, no errors |
| TC-2 | Python deps importable | `import duckdb; import pyarrow; import pandas` exits 0 |
| TC-3 | dbt version correct | `dbt --version` reports 1.7.x |
| TC-4 | source/ mounted read-only | Write attempt to /app/source raises PermissionError |
| TC-5 | silver/ and silver_temp/ rename works | `os.rename('/app/silver_temp/probe', '/app/silver/probe')` exits 0 |
| TC-6 | .gitignore excludes runtime Parquet | `git status` shows no untracked .parquet files after build |

**Verification command (R-02 — mount parity probe added):**
```bash
docker compose build \
  && docker compose run --rm pipeline python -c "import duckdb; import pyarrow; import pandas; print('deps ok')" \
  && docker compose run --rm pipeline dbt --version \
  && docker compose run --rm pipeline python -c "
import os, pathlib
pathlib.Path('/app/silver_temp/mount_probe').touch()
os.rename('/app/silver_temp/mount_probe', '/app/silver/mount_probe')
os.remove('/app/silver/mount_probe')
print('R-02 PASS: silver/ and silver_temp/ on same filesystem — atomic rename confirmed')
" \
  && echo "Task 1.2 PASS"
```

**Invariant enforcement:**
- **INV-06** (Source files never modified): `source/` read-only bind mount. Verified TC-4.
- **Decision 4 atomic rename** (Implementation Guidance): `silver/` and `silver_temp/` same mount. Verified TC-5 and mount parity probe.

**Regression classification:** REGRESSION-RELEVANT — Docker build is prerequisite for every downstream task. Portable.

---

### Task 1.3 — dbt Project Initialisation

**Description:**
Creates the dbt project inside `dbt/` with `dbt_project.yml` and `profiles.yml` pointing
to an embedded DuckDB file. Creates `models/silver/` and `models/gold/` subdirectories.
No model SQL files yet. `dbt debug` exits 0.

**Input:** Docker environment from Task 1.2.
**Output:** `dbt/dbt_project.yml`, `dbt/profiles.yml`, model directory structure committed. `dbt debug` exits 0.

**CC Prompt:**
```
Initialise the dbt project for the Credit Card Transactions Lake inside dbt/.

CREATE the following files:

1. dbt/dbt_project.yml:
   - name: credit_card_transactions_lake
   - version: "1.0.0"
   - profile: credit_card_transactions_lake
   - model-paths: ["models"]
   - models:
       credit_card_transactions_lake:
         silver:
           +materialized: table
         gold:
           +materialized: table

2. dbt/profiles.yml:
   - profile: credit_card_transactions_lake
   - target: dev
   - type: duckdb
   - path: /app/pipeline/dbt_catalog.duckdb
   - threads: 1

3. dbt/models/silver/.gitkeep
4. dbt/models/gold/.gitkeep
5. dbt/models/sources.yml — placeholder, empty sources block

CONSTRAINTS:
- DuckDB embedded — no server, no network (INV-07).
- Do not create any model SQL files in this task.

Run before committing:
  docker compose run --rm pipeline dbt debug --project-dir /app/dbt --profiles-dir /app/dbt

  git add dbt/
  git commit -m "1.3 — dbt project init: credit_card_transactions_lake, DuckDB profile"
```

**Test Cases:**

| Case | Scenario | Expected |
|---|---|---|
| TC-1 | `dbt debug` inside container | Exit 0, "All checks passed" |
| TC-2 | Profile name correct | `grep "credit_card_transactions_lake" dbt/profiles.yml` matches |
| TC-3 | DuckDB path correct | `grep "/app/pipeline/dbt_catalog.duckdb" dbt/profiles.yml` matches |
| TC-4 | Model directories exist | `ls dbt/models/silver dbt/models/gold` exits 0 |

**Verification command:**
```bash
docker compose run --rm pipeline dbt debug --project-dir /app/dbt --profiles-dir /app/dbt \
  && echo "Task 1.3 PASS"
```

**Invariant enforcement:** INV-07 (No external service calls).

**Regression classification:** REGRESSION-RELEVANT — dbt configuration is prerequisite for all Sessions 3 and 4. Portable.

---

### Task 1.4 — Source CSV Seed Data

**Description:**
Creates six daily transaction CSV files, six accounts delta CSV files, and one static
transaction_codes CSV in `source/`. Covers all Silver validation rules and Gold exclusion
logic. Date 7 (2024-01-07) intentionally has no transaction file — tests the no-op path.

**Input:** `source/` directory.
**Output:** 6 transaction CSVs, 6 accounts CSVs, 1 transaction_codes CSV committed. No file for 2024-01-07.

**CC Prompt:**
```
Create seed source CSV files for the Credit Card Transactions Lake in source/.
These files are read-only test fixtures — never modified by the pipeline (INV-06).

SCHEMA — transactions_{YYYY-MM-DD}.csv:
  transaction_id, transaction_date, account_id, transaction_code,
  amount, channel, description

SCHEMA — accounts_{YYYY-MM-DD}.csv:
  account_id, account_name, account_status, credit_limit,
  current_balance, last_updated

SCHEMA — transaction_codes.csv:
  transaction_code, description, debit_credit_indicator, transaction_type

CREATE FILES for dates 2024-01-01 through 2024-01-06 (6 dates).
DO NOT create any file for 2024-01-07 — tests the no-op path (GAP-INV-02, OQ-1).

CONTENT REQUIREMENTS — seed data must collectively cover:
1. At least 5 clean transactions per date (happy path)
2. 1 transaction with NULL transaction_id → NULL_REQUIRED_FIELD quarantine
3. 1 transaction with amount = -50 (negative) → INVALID_AMOUNT quarantine
4. 1 duplicate transaction_id across two different dates → DUPLICATE_TRANSACTION_ID quarantine
5. 1 transaction with transaction_code not in transaction_codes.csv → INVALID_TRANSACTION_CODE quarantine
6. 1 transaction with channel = "UNKNOWN_CHANNEL" → INVALID_CHANNEL quarantine
7. 1 transaction referencing account_id not in any accounts file → _is_resolvable = false in Silver
8. At least PURCHASE and PAYMENT transaction_types — required for Gold weekly summary
9. debit_credit_indicator values: DR and CR only

  git add source/
  git commit -m "1.4 — Source CSV seed data: 6 dates, all validation scenarios, no file for 2024-01-07"
```

**Test Cases:**

| Case | Scenario | Expected |
|---|---|---|
| TC-1 | 6 transaction files present | transactions_2024-01-01.csv through transactions_2024-01-06.csv |
| TC-2 | No file for 2024-01-07 | `ls source/transactions_2024-01-07.csv` → not found |
| TC-3 | transaction_codes.csv present | File exists with DR and CR indicators |
| TC-4 | All quarantine scenarios represented | NULL, negative amount, duplicate, invalid code, invalid channel all in seed data |

**Verification command:**
```bash
for d in 01 02 03 04 05 06; do
  [ -f "source/transactions_2024-01-${d}.csv" ] && echo "OK: transactions_2024-01-${d}.csv" || echo "MISSING"
done \
  && [ ! -f "source/transactions_2024-01-07.csv" ] && echo "OK: no file for date 7" \
  && [ -f "source/transaction_codes.csv" ] && echo "OK: transaction_codes.csv" \
  && echo "Task 1.4 PASS"
```

**Invariant enforcement:** INV-06, GAP-INV-02.

**Regression classification:** NOT-REGRESSION-RELEVANT — static seed data; no runtime behaviour change.

---

### Task 1.5 — tools/ Agentic Build Scripts

**Description:**
Creates the five PBVI tools/ scripts: `challenge.sh`, `launch.sh`, `resume_session.sh`,
`resume_challenge.sh`, `monitor.sh`. These scripts are authored from the PBVI spec since
no DG-Forge repo exists to clone from.

**Input:** PBVI methodology spec (pbvi_core.md, pbvi_templates.md).
**Output:** All 5 scripts committed under `tools/`. `./tools/challenge.sh --check` exits 0.

**CC Prompt:**
```
Create the five PBVI tools/ scripts for the Credit Card Transactions Lake.
No DG-Forge repo exists to clone — author from the PBVI methodology spec.

CREATE tools/challenge.sh — the challenge agent runner.
  Accepts: S[N] TASK_ID as arguments, or --check for self-test.
  Provides: Claude.md + task section from EXECUTION_PLAN.md + git diff + Verification Record.
  Returns: CLEAN or FINDINGS verdict.

CREATE tools/launch.sh — autonomous session launcher.
  Accepts: session number.
  Invokes Claude Code with the session execution prompt file.

CREATE tools/resume_session.sh — blocked session resume.
  Accepts: session number, task ID.
  Resumes from a BLOCKED stop point.

CREATE tools/resume_challenge.sh — challenge findings resume.
  Accepts: session number, task ID.
  Resumes after CHALLENGE FINDINGS handling.

CREATE tools/monitor.sh — session progress monitor.
  Shows current session log status and task completion count.

CONSTRAINTS:
- No external service calls (INV-07).
- chmod +x all scripts.

  git add tools/
  git commit -m "1.5 — tools/ PBVI scripts: challenge.sh, launch.sh, resume scripts, monitor.sh"
```

**Test Cases:**

| Case | Scenario | Expected |
|---|---|---|
| TC-1 | `./tools/challenge.sh --check` | Exit 0 |
| TC-2 | All 5 scripts executable | `ls -la tools/*.sh` shows x permission for all |

**Verification command:**
```bash
bash tools/challenge.sh --check \
  && ls -la tools/*.sh \
  && echo "Task 1.5 PASS"
```

**Invariant enforcement:** None — tooling only.

**Regression classification:** NOT-REGRESSION-RELEVANT — build tooling; no runtime data behaviour.

---

## Session 2 — Bronze Ingestion

**Session goal:** `bronze_loader.load_bronze('transactions', '2024-01-01', run_id, '/app/source', '/app/bronze')`
returns SUCCESS. Bronze partition at correct path. `_pipeline_run_id` non-null. Idempotency
confirmed. run_log.parquet written. `pipeline_historical.py` (Bronze only) processes all 6 dates.

**Branch:** `session/s2_bronze`

**Integration check:**
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

---

### Task 2.1 — run_logger.py

**Description:**
Implements `pipeline/run_logger.py`. Append-only writer to `pipeline/run_log.parquet`.
One row per model per invocation. Creates the file on first write. Never overwrites
existing rows — always appends. Enforces field-level constraints: records_rejected null
for Bronze and Gold; error_message null on SUCCESS; no paths in error_message.

**Input:** None — standalone module.
**Output:** `pipeline/run_logger.py` committed.

**CC Prompt:**
```
Implement pipeline/run_logger.py for the Credit Card Transactions Lake.

PURPOSE: append-only run log writer. Writes to pipeline/run_log.parquet.
One row per model per pipeline invocation.

FUNCTION SIGNATURES:

def append_run_log(records: list[dict]) -> None
  Each record dict:
    run_id: str                — UUIDv4 string (RL-02)
    model_name: str            — one of: bronze_transactions, bronze_accounts,
                                 bronze_transaction_codes, silver_transactions,
                                 silver_accounts, silver_transaction_codes,
                                 silver_quarantine, gold_daily_summary, gold_weekly_summary
    status: str                — SUCCESS | FAILED | SKIPPED
    started_at: str            — ISO 8601 datetime
    completed_at: str          — ISO 8601 datetime
    records_processed: int | None
    records_written: int | None
    records_rejected: int | None  — NULL for Bronze and Gold models (RL-04)
    error_message: str | None     — NULL on SUCCESS (RL-05a);
                                    never contains paths or credentials (RL-05b)
    processed_date: str | None    — YYYY-MM-DD, NULL for SKIPPED

def get_run_log() -> pandas.DataFrame
  Read pipeline/run_log.parquet. Return empty DataFrame if file absent.

IMPLEMENTATION RULES:
- If run_log.parquet absent: create with correct schema then write (RL-01b).
- If present: read existing rows, append new rows, overwrite file.
  Logically append-only — never modify existing rows (RL-01b).
- Use pyarrow or pandas for Parquet I/O — not DuckDB write (Decision 5).
- records_rejected must be None for Bronze and Gold model rows (RL-04).
- error_message must be None on SUCCESS rows (RL-05a).
- Strip any path separators (/ and \) from error_message before writing (RL-05b).
- No external service calls (INV-07).
- Each function must have a single stateable purpose.
  Conditional nesting exceeding two levels is a structural violation.

NOTE — expected SKIPPED model count per no-op incremental invocation is 8:
  bronze_transactions, bronze_accounts, silver_transaction_codes, silver_accounts,
  silver_transactions, silver_quarantine, gold_daily_summary, gold_weekly_summary.
  (R-07: self-documenting constant for Task 6.2 verification)

After implementation:
  git add pipeline/run_logger.py
  git commit -m "2.1 — run_logger.py: append-only run log writer, Parquet I/O"
```

**Test Cases:**

| Case | Scenario | Expected |
|---|---|---|
| TC-1 | First write — file absent | run_log.parquet created with 1 row |
| TC-2 | Second write — file present | run_log.parquet has 2 rows; first row unchanged (RL-01b) |
| TC-3 | SUCCESS record | error_message is null |
| TC-4 | Bronze record | records_rejected is null (RL-04) |
| TC-5 | Gold record | records_rejected is null (RL-04) |
| TC-6 | FAILED record with path in message | Path separators stripped from error_message (RL-05b) |
| TC-7 | get_run_log() — file absent | Returns empty DataFrame |

**Verification command:**
```bash
docker compose run --rm pipeline python -c "
import sys; sys.path.insert(0, '/app')
from pipeline.run_logger import append_run_log, get_run_log
import uuid, datetime
run_id = str(uuid.uuid4())
append_run_log([{'run_id': run_id, 'model_name': 'bronze_transactions',
  'status': 'SUCCESS', 'started_at': datetime.datetime.utcnow().isoformat(),
  'completed_at': datetime.datetime.utcnow().isoformat(),
  'records_processed': 100, 'records_written': 100,
  'records_rejected': None, 'error_message': None, 'processed_date': '2024-01-01'}])
df = get_run_log()
assert len(df) >= 1
row = df[df.run_id == run_id].iloc[0]
assert str(row['error_message']) in ('None', 'nan', '')
assert str(row['records_rejected']) in ('None', 'nan', '')
print('Task 2.1 PASS')
"
```

**Invariant enforcement:** RL-01b, RL-02, RL-04 (impl guidance), RL-05a (impl guidance), RL-05b (impl guidance), S1B-05.

**Regression classification:** REGRESSION-RELEVANT — run log correctness verified end-to-end. Portable.

---

### Task 2.2 — bronze_loader.py

**Description:**
Implements `pipeline/bronze_loader.py`. Reads a source CSV, validates schema, checks
existing Bronze partition (row count idempotency), writes to
`bronze/{entity}/date=YYYY-MM-DD/data.parquet`. Adds `_pipeline_run_id`,
`_ingested_at`, `_source_file` audit columns. Returns structured result.

**Input:** Source CSV path, entity name, date string, run_id.
**Output:** `pipeline/bronze_loader.py` committed.

**CC Prompt:**
```
Implement pipeline/bronze_loader.py for the Credit Card Transactions Lake.

PURPOSE: ingest one source CSV file into a Bronze Parquet partition.

FUNCTION SIGNATURE:
  def load_bronze(entity: str, date_str: str, run_id: str,
                  source_dir: str, bronze_dir: str) -> dict

Returns: {status, records_processed, records_written, error_message, entity, date_str}

EXPECTED SCHEMAS (S1B-schema-evolution: fixed, no dynamic inference):
  transactions:       transaction_id, transaction_date, account_id,
                      transaction_code, amount, channel, description
  accounts:           account_id, account_name, account_status, credit_limit,
                      current_balance, last_updated
  transaction_codes:  transaction_code, description, debit_credit_indicator,
                      transaction_type

IMPLEMENTATION RULES:
1. Source file path: {source_dir}/{entity}_{date_str}.csv
   Exception — transaction_codes: {source_dir}/transaction_codes.csv (no date suffix).
2. Absent source file → return status=SKIPPED, records_processed=None (GAP-INV-02, OQ-1).
3. Schema validation (S1B-schema): compare CSV headers. Mismatch → FAILED.
4. Idempotency check — Decision 3 (INV-01a):
   Target: {bronze_dir}/{entity}/date={date_str}/data.parquet (INV-10)
   - Partition exists + row count matches source: return SUCCESS immediately.
   - Partition exists + row count mismatches: delete partition, re-ingest (S1B-03).
   - Partition absent: proceed to ingest.
5. Add audit columns to every row (INV-04 GLOBAL, INV-08):
   _pipeline_run_id: run_id string — MUST be non-null
   _ingested_at: current UTC datetime ISO string
   _source_file: basename only — no directory path (RL-05b analog)
6. Write Parquet to target path. Create parent directories as needed (S1B-parquet).
7. Source file must not be modified or deleted (INV-06).
8. Bronze preserves source data exactly — no transforms, no type coercions (INV-08).
9. No external service calls (INV-07).
10. Each function must have a single stateable purpose.
    Conditional nesting exceeding two levels is a structural violation.

Use Python + DuckDB for Parquet I/O (S1B-bronze-python).

After implementation:
  git add pipeline/bronze_loader.py
  git commit -m "2.2 — bronze_loader.py: CSV ingestion, schema validation, row-count idempotency"
```

**Test Cases:**

| Case | Scenario | Expected |
|---|---|---|
| TC-1 | Clean CSV — first ingestion | status=SUCCESS; Parquet at correct path; row count matches source |
| TC-2 | Rerun same CSV (idempotent) | status=SUCCESS; no rewrite; row count unchanged (INV-01a) |
| TC-3 | Partition exists, row count matches | SUCCESS returned immediately |
| TC-4 | Partition exists, row count mismatches | Partition deleted, re-ingested (S1B-03) |
| TC-5 | Source file absent | status=SKIPPED; no Parquet written (GAP-INV-02) |
| TC-6 | Schema mismatch | status=FAILED; no Parquet written (S1B-schema) |
| TC-7 | Audit columns present and non-null | _pipeline_run_id, _ingested_at, _source_file all non-null (INV-04) |
| TC-8 | Source columns preserved exactly | All source values unchanged in Bronze (INV-08) |
| TC-9 | Source file unchanged after ingestion | MD5 hash identical before and after call (INV-06) |
| TC-10 | Bronze path convention correct | Path is `bronze/{entity}/date={date_str}/data.parquet` (INV-10) |

**Verification command:**
```bash
docker compose run --rm pipeline python -c "
import sys, hashlib; sys.path.insert(0, '/app')
from pipeline.bronze_loader import load_bronze
import uuid, duckdb
run_id = str(uuid.uuid4())
with open('/app/source/transactions_2024-01-01.csv','rb') as f: before = hashlib.md5(f.read()).hexdigest()
result = load_bronze('transactions', '2024-01-01', run_id, '/app/source', '/app/bronze')
assert result['status'] == 'SUCCESS', f'Expected SUCCESS got {result}'
with open('/app/source/transactions_2024-01-01.csv','rb') as f: after = hashlib.md5(f.read()).hexdigest()
assert before == after, 'INV-06 FAIL: source file modified'
conn = duckdb.connect()
rows = conn.execute(\"SELECT COUNT(*) FROM read_parquet('/app/bronze/transactions/date=2024-01-01/data.parquet')\").fetchone()[0]
nulls = conn.execute(\"SELECT COUNT(*) FROM read_parquet('/app/bronze/transactions/date=2024-01-01/data.parquet') WHERE _pipeline_run_id IS NULL\").fetchone()[0]
assert rows > 0 and nulls == 0
result2 = load_bronze('transactions', '2024-01-01', run_id, '/app/source', '/app/bronze')
rows2 = conn.execute(\"SELECT COUNT(*) FROM read_parquet('/app/bronze/transactions/date=2024-01-01/data.parquet')\").fetchone()[0]
assert rows == rows2, f'INV-01a FAIL: row count changed on rerun'
print(f'Task 2.2 PASS — {rows} rows, idempotency confirmed')
"
```

**Invariant enforcement:** INV-01a, INV-04 (GLOBAL), INV-06, INV-08, INV-09, GAP-INV-02, S1B-03, S1B-schema, S1B-bronze-python, S1B-parquet, INV-07 (impl guidance), INV-10 (impl guidance), S1B-schema-evolution (impl guidance).

**Regression classification:** REGRESSION-RELEVANT — Bronze ingestion is foundation of all downstream layers. Portable.

---

### Task 2.3 — pipeline_historical.py (Bronze only)

**Description:**
Implements `pipeline_historical.py` — historical entry point. Bronze ingestion and run
log writing only. Silver, Gold, and watermark added in Session 5.

**Input:** `bronze_loader.py`, `run_logger.py`.
**Output:** `pipeline/pipeline_historical.py` committed. Bronze run produces all six partitions.

**CC Prompt:**
```
Implement pipeline/pipeline_historical.py — historical pipeline entry point.
SESSION 2 SCOPE: Bronze ingestion and run log writing only.
Silver, Gold, and watermark are NOT implemented in this task.

INVOCATION:
  python pipeline/pipeline_historical.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD

IMPLEMENTATION RULES:
1. Generate run_id = str(uuid.uuid4()) at invocation start (OQ-3, RL-02).
2. Parse --start-date and --end-date. Validate both present and start <= end.
3. Iterate dates from start_date to end_date INCLUSIVE in ascending order (GAP-INV-01a).
4. For EACH date, call bronze_loader.load_bronze in sequence (GAP-INV-01b):
   a. transaction_codes — first date only
   b. accounts — every date
   c. transactions — every date
5. After each load_bronze() call, immediately call run_logger.append_run_log().
6. If bronze_transactions FAILED: write FAILED log entry. Continue to next date.
7. If no source file (SKIPPED): write SKIPPED entries for all models for that date.
8. WATERMARK: do NOT advance watermark — Session 5 scope.
9. No external service calls (INV-07).
10. Each function must have a single stateable purpose.
    Conditional nesting exceeding two levels is a structural violation.

CONSTANTS at module top: SOURCE_DIR, BRONZE_DIR, PIPELINE_DIR

  git add pipeline/pipeline_historical.py
  git commit -m "2.3 — pipeline_historical.py: date-range Bronze ingestion, run log integration"
```

**Test Cases:**

| Case | Scenario | Expected |
|---|---|---|
| TC-1 | Full run 2024-01-01 to 2024-01-06 | 6 transaction + 6 accounts + 1 transaction_codes Bronze partitions |
| TC-2 | Run log entries written | run_log.parquet has rows for all models all 6 dates |
| TC-3 | Ascending date order | Run log entries per date in ascending order (GAP-INV-01a) |
| TC-4 | Within-date sequence | bronze_transaction_codes, bronze_accounts, bronze_transactions (GAP-INV-01b) |
| TC-5 | Idempotent rerun | Bronze row counts unchanged on second run; new run_id in run_log |
| TC-6 | S1B-02 | Row counts identical between first and second run for same date |

**Verification command:**
```bash
docker compose run --rm pipeline python pipeline/pipeline_historical.py \
    --start-date 2024-01-01 --end-date 2024-01-06 \
  && docker compose run --rm pipeline python -c "
import duckdb; conn = duckdb.connect()
for date in ['2024-01-0' + str(d) for d in range(1,7)]:
    rows = conn.execute(f\"SELECT COUNT(*) FROM read_parquet('/app/bronze/transactions/date={date}/data.parquet')\").fetchone()[0]
    assert rows > 0, f'No rows for {date}'
    print(f'bronze/transactions/{date}: {rows} rows')
log = conn.execute(\"SELECT COUNT(*) FROM read_parquet('/app/pipeline/run_log.parquet')\").fetchone()[0]
assert log > 0
print('Task 2.3 PASS')
"
```

**Invariant enforcement:** GAP-INV-01a, GAP-INV-01b, GAP-INV-02, INV-05a, RL-01a, S1B-02.

**Regression classification:** REGRESSION-RELEVANT — historical pipeline is primary Bronze test path. Portable.

---

### Task 2.4 — control_manager.py

**Description:**
Implements `pipeline/control_manager.py` with `get_watermark()`, `set_watermark()`,
and `get_next_date()` backed by `pipeline/control.parquet`.

**R-01 fix (v1.2):** Cold-start guard added. If `control.parquet` is absent when
`get_watermark()` is called from `pipeline_incremental.py` context, the caller must
handle `None` return by raising `RuntimeError`. The guard is implemented in
`pipeline_incremental.py` (Task 5.2). Test case TC-cold-start added here to verify
the `None` return and the guard behaviour.

**Input:** None — standalone module.
**Output:** `pipeline/control_manager.py` committed.

**CC Prompt:**
```
Implement pipeline/control_manager.py for the Credit Card Transactions Lake.

FUNCTIONS:

1. get_watermark(pipeline_dir: str) -> str | None
   Read pipeline_dir/control.parquet if exists. Return watermark_date or None.
   Returns None on cold start (no control.parquet) — callers must handle None explicitly.

2. set_watermark(date_str: str, pipeline_dir: str) -> None
   Write/overwrite pipeline_dir/control.parquet:
     watermark_date: date_str
     updated_at: current UTC datetime ISO string
   CALLED ONLY as the final operation in a fully successful pipeline run (INV-02).

3. get_next_date(pipeline_dir: str) -> str | None
   Call get_watermark(). If None: return None.
   If watermark present: return watermark_date + 1 calendar day as YYYY-MM-DD.

IMPLEMENTATION RULES:
- Use pyarrow or pandas for Parquet I/O (S1B-parquet).
- No external service calls (INV-07).
- Each function must have a single stateable purpose.
  Conditional nesting exceeding two levels is a structural violation.
- get_watermark() returns None on cold start — this is not an error at the module level.
  pipeline_incremental.py is responsible for raising RuntimeError on None (R-01).

After implementation:
  git add pipeline/control_manager.py
  git commit -m "2.4 — control_manager.py: watermark read/write, get_next_date, cold-start None"
```

**Test Cases:**

| Case | Scenario | Expected |
|---|---|---|
| TC-1 | get_watermark — file absent | Returns None |
| TC-2 | set_watermark then get_watermark | Returns set date |
| TC-3 | get_next_date — no watermark | Returns None |
| TC-4 | get_next_date — watermark 2024-01-05 | Returns "2024-01-06" |
| TC-cold-start | get_watermark on fresh env → None returned | None returned cleanly; no exception raised by control_manager itself |

**Verification command:**
```bash
docker compose run --rm pipeline python -c "
import sys, tempfile; sys.path.insert(0, '/app')
from pipeline.control_manager import get_watermark, set_watermark, get_next_date
td = tempfile.mkdtemp()
result = get_watermark(td)
assert result is None, f'Expected None on cold start, got {result}'
print('TC-cold-start PASS: get_watermark returns None on cold start')
set_watermark('2024-01-05', td)
assert get_watermark(td) == '2024-01-05'
assert get_next_date(td) == '2024-01-06'
print('Task 2.4 PASS')
"
```

**Invariant enforcement:** INV-02 (Watermark advances only after full success — set_watermark() not yet wired to entry points — Session 5. Documented.), S1B-parquet.

**Regression classification:** REGRESSION-RELEVANT — watermark drives incremental pipeline. Portable.

---

## Session 3 — Silver Promotion: dbt Models

**Session goal:** `silver_promoter.promote_silver('2024-01-01', run_id, '/app')` returns
SUCCESS. Silver Transactions, Silver Accounts, Silver Quarantine, and Silver Transaction
Codes Parquet files all present. Mass conservation holds for all 6 dates. All dbt tests pass.

**Branch:** `session/s3_silver_dbt`

**Integration check:**
```bash
docker compose run --rm pipeline python -c "
import sys; sys.path.insert(0, '/app')
from pipeline.silver_promoter import promote_silver
import uuid
result = promote_silver('2024-01-01', str(uuid.uuid4()), '/app')
assert result['status'] == 'SUCCESS', f'FAILED: {result}'
import duckdb; conn = duckdb.connect()
silver = conn.execute(\"SELECT COUNT(*) FROM read_parquet('/app/silver/transactions/date=2024-01-01/data.parquet')\").fetchone()[0]
quar = conn.execute(\"SELECT COUNT(*) FROM read_parquet('/app/quarantine/data.parquet') WHERE transaction_date = '2024-01-01'\").fetchone()[0]
bronze = conn.execute(\"SELECT COUNT(*) FROM read_parquet('/app/bronze/transactions/date=2024-01-01/data.parquet')\").fetchone()[0]
assert silver + quar == bronze, f'SIL-T-01 FAIL: {silver}+{quar}!={bronze}'
print(f'S3 INTEGRATION PASS — silver={silver}, quar={quar}, bronze={bronze}')
"
```

---

### Task 3.1 — dbt Sources and Silver Transaction Codes Model

**Description:**
Defines `dbt/models/sources.yml` and implements `silver_transaction_codes` dbt model.

**R-04 fix (v1.2):** `not_null: _pipeline_run_id` dbt schema test added to
`silver_transaction_codes.yml` to enforce INV-04 at dbt build time.

**CC Prompt:**
```
Implement the dbt Silver Transaction Codes model for the Credit Card Transactions Lake.

STEP 1 — Update dbt/models/sources.yml:
  Declare Bronze Parquet paths as dbt sources using dbt-duckdb external source syntax.
  Tables: bronze_transactions, bronze_accounts, bronze_transaction_codes.

STEP 2 — Create dbt/models/silver/silver_transaction_codes.sql:
  SELECT all columns from bronze_transaction_codes source.
  _pipeline_run_id: from source _pipeline_run_id column (INV-04).
  config: materialized='external', location='/app/silver/transaction_codes/data.parquet'

STEP 3 — Create dbt/models/silver/silver_transaction_codes.yml:
  Tests: not_null(transaction_code), not_null(debit_credit_indicator),
  not_null(transaction_type), not_null(_pipeline_run_id),
  accepted_values(debit_credit_indicator, ['DR','CR']),
  accepted_values(transaction_type, ['PURCHASE','PAYMENT','FEE','INTEREST'])

  CRITICAL (R-04): not_null(_pipeline_run_id) dbt test is REQUIRED.
  This enforces INV-04 (GLOBAL) at dbt build time — not just at Session 6 audit.

RULES:
- INV-04 (GLOBAL): _pipeline_run_id non-null on every Silver row — enforced by dbt test.
- SIL-REF-02 (impl guidance): this model only run via promote_silver_transaction_codes().
- No external service calls (INV-07).

  git add dbt/models/
  git commit -m "3.1 — dbt Silver Transaction Codes: reference load, sources.yml"
```

**Test Cases:**

| Case | Scenario | Expected |
|---|---|---|
| TC-1 | `dbt run` | Exit 0; silver/transaction_codes/data.parquet created |
| TC-2 | Row count = Bronze row count | silver_transaction_codes count = bronze_transaction_codes count |
| TC-3 | `dbt test` passes | All not_null and accepted_values tests pass |
| TC-4 | _pipeline_run_id non-null | not_null(_pipeline_run_id) dbt test passes (INV-04, R-04) |
| TC-5 | SIL-REF-01 prerequisite met | `SELECT COUNT(*) > 0` from silver/transaction_codes |

**Verification command:**
```bash
docker compose run --rm pipeline dbt run --select silver_transaction_codes \
    --project-dir /app/dbt --profiles-dir /app/dbt \
  && docker compose run --rm pipeline dbt test --select silver_transaction_codes \
    --project-dir /app/dbt --profiles-dir /app/dbt \
  && echo "Task 3.1 PASS — including not_null(_pipeline_run_id) INV-04 dbt test"
```

**Invariant enforcement:** SIL-REF-01, INV-04 (GLOBAL — dbt test, R-04), S1B-dbt-silver-gold, SIL-REF-02 (impl guidance).

**Regression classification:** REGRESSION-RELEVANT — reference data prerequisite for all transaction promotion. Portable.

---

### Task 3.2 — dbt Silver Accounts Model

**Description:**
Implements `silver_accounts` dbt model. One current record per account_id (SIL-A-01).
Latest record wins per account_id via ROW_NUMBER().

**R-04 fix (v1.2):** `not_null: _pipeline_run_id` dbt schema test added.

**CC Prompt:**
```
Implement the dbt Silver Accounts model for the Credit Card Transactions Lake.

REQUIREMENT: One current record per account_id (SIL-A-01). Latest last_updated wins.
ROW_NUMBER() OVER (PARTITION BY account_id ORDER BY last_updated DESC) — keep rank=1.

CREATE dbt/models/silver/silver_accounts.sql:
  Source: bronze_accounts (glob across all date partitions).
  Apply ROW_NUMBER() deduplication.
  _pipeline_run_id: from source _pipeline_run_id (INV-04).
  config: materialized='external', location='/app/silver/accounts/data.parquet'

CREATE dbt/models/silver/silver_accounts.yml:
  Tests: not_null(account_id), unique(account_id) (SIL-A-01), not_null(_pipeline_run_id)

  CRITICAL (R-04): not_null(_pipeline_run_id) dbt test is REQUIRED — enforces INV-04 at build time.

RULES:
- GAP-INV-04: absent accounts file — glob handles gracefully.
- INV-01b: idempotent.
- INV-04 (GLOBAL): _pipeline_run_id non-null — enforced by dbt test.
- S1B-dbt-silver-gold: dbt model exclusively.
- No external service calls (INV-07).

  git add dbt/models/silver/silver_accounts.sql dbt/models/silver/silver_accounts.yml
  git commit -m "3.2 — dbt Silver Accounts: latest per account_id upsert"
```

**Test Cases:**

| Case | Scenario | Expected |
|---|---|---|
| TC-1 | `dbt run` | Exit 0; silver/accounts/data.parquet created |
| TC-2 | One record per account_id | unique(account_id) test passes (SIL-A-01) |
| TC-3 | account_id on multiple dates | Latest last_updated retained |
| TC-4 | _pipeline_run_id non-null | not_null(_pipeline_run_id) dbt test passes (INV-04, R-04) |
| TC-5 | Idempotent rerun | Row count unchanged on second run (INV-01b) |

**Verification command:**
```bash
docker compose run --rm pipeline dbt run --select silver_accounts \
    --project-dir /app/dbt --profiles-dir /app/dbt \
  && docker compose run --rm pipeline dbt test --select silver_accounts \
    --project-dir /app/dbt --profiles-dir /app/dbt \
  && echo "Task 3.2 PASS"
```

**Invariant enforcement:** SIL-A-01, GAP-INV-04, INV-04 (GLOBAL — dbt test, R-04), INV-01b.

**Regression classification:** REGRESSION-RELEVANT — Silver Accounts drives _is_resolvable and closing_balance. Portable.

---

### Task 3.3 — dbt Silver Quarantine Model

**Description:**
Implements `silver_quarantine` dbt model. Five rejection rules applied in order.
Original Bronze columns preserved unchanged (SIL-Q-03).

**R-04 fix (v1.2):** `not_null: _pipeline_run_id` dbt schema test added.

**CC Prompt:**
```
Implement the dbt Silver Quarantine model for the Credit Card Transactions Lake.

REJECTION RULES — evaluate in order, assign FIRST matching reason:
1. NULL_REQUIRED_FIELD: any required field is NULL
2. INVALID_AMOUNT: amount <= 0
3. DUPLICATE_TRANSACTION_ID: transaction_id appears more than once across all Bronze partitions
4. INVALID_TRANSACTION_CODE: transaction_code not in silver_transaction_codes
5. INVALID_CHANNEL: channel not in ('POS','ONLINE','ATM','MOBILE','BRANCH')

CREATE dbt/models/silver/silver_quarantine.sql:
  Source: bronze_transactions (all partitions). Ref: silver_transaction_codes.
  Apply rules in order. Include ONLY rows matching at least one rule.
  _rejection_reason: first matching rule code.
  _pipeline_run_id: from source _pipeline_run_id (INV-04).
  Retain ALL original Bronze source columns unchanged (SIL-Q-03 impl guidance).
  config: materialized='external', location='/app/quarantine/data.parquet'

CREATE dbt/models/silver/silver_quarantine.yml:
  Tests: not_null(_rejection_reason) (SIL-Q-01),
  accepted_values(_rejection_reason, ['NULL_REQUIRED_FIELD','INVALID_AMOUNT',
  'DUPLICATE_TRANSACTION_ID','INVALID_TRANSACTION_CODE','INVALID_CHANNEL']) (SIL-Q-02),
  not_null(_pipeline_run_id)

  CRITICAL (R-04): not_null(_pipeline_run_id) dbt test is REQUIRED — enforces INV-04 at build time.

RULES:
- SIL-Q-03 (impl guidance): ALL original Bronze columns preserved unchanged.
- GAP-INV-07: DUPLICATE_TRANSACTION_ID → quarantine.
- INV-04 (GLOBAL): _pipeline_run_id non-null — enforced by dbt test.
- No external service calls (INV-07). Each CTE single purpose. Nesting > 2 levels → refactor.

  git add dbt/models/silver/silver_quarantine.sql dbt/models/silver/silver_quarantine.yml
  git commit -m "3.3 — dbt Silver Quarantine: 5 rejection rules, all reason codes"
```

**Test Cases:**

| Case | Scenario | Expected |
|---|---|---|
| TC-1 | NULL transaction_id | Quarantine with NULL_REQUIRED_FIELD |
| TC-2 | Negative amount | Quarantine with INVALID_AMOUNT |
| TC-3 | Duplicate transaction_id | Quarantine with DUPLICATE_TRANSACTION_ID (GAP-INV-07) |
| TC-4 | Unknown transaction_code | Quarantine with INVALID_TRANSACTION_CODE |
| TC-5 | Invalid channel | Quarantine with INVALID_CHANNEL |
| TC-6 | `dbt test` passes | not_null and accepted_values pass (SIL-Q-01, SIL-Q-02) |
| TC-7 | _pipeline_run_id non-null | not_null(_pipeline_run_id) dbt test passes (INV-04, R-04) |
| TC-8 | Original columns preserved | Source Bronze columns intact (SIL-Q-03) |

**Verification command:**
```bash
docker compose run --rm pipeline dbt run --select silver_quarantine \
    --project-dir /app/dbt --profiles-dir /app/dbt \
  && docker compose run --rm pipeline dbt test --select silver_quarantine \
    --project-dir /app/dbt --profiles-dir /app/dbt \
  && docker compose run --rm pipeline python -c "
import duckdb; conn = duckdb.connect()
reasons = conn.execute(\"SELECT _rejection_reason, COUNT(*) FROM read_parquet('/app/quarantine/data.parquet') GROUP BY 1\").fetchall()
print('Quarantine by reason:', reasons)
assert any(r[0] == 'NULL_REQUIRED_FIELD' for r in reasons)
assert any(r[0] == 'INVALID_AMOUNT' for r in reasons)
print('Task 3.3 PASS')
"
```

**Invariant enforcement:** SIL-Q-01, SIL-Q-02, SIL-T-07, GAP-INV-07, SIL-T-02, SIL-Q-03 (impl guidance), INV-04 (GLOBAL — dbt test, R-04).

**Regression classification:** REGRESSION-RELEVANT — quarantine is one half of mass conservation check. Portable.

---

### Task 3.4 — dbt Silver Transactions Model

**Description:**
Implements `silver_transactions` dbt model. Validation, deduplication, sign assignment
via `debit_credit_indicator`, `_is_resolvable` flag for unknown accounts.

**R-04 fix (v1.2):** `not_null: _pipeline_run_id` dbt schema test added.

**CC Prompt:**
```
Implement the dbt Silver Transactions model for the Credit Card Transactions Lake.

CREATE dbt/models/silver/silver_transactions.sql:
  Source: bronze_transactions (partitioned by date={date_var}).
  Exclude quarantine-bound records (those matching rejection rules).
  JOIN to silver_transaction_codes for _signed_amount derivation.
  _signed_amount: CASE WHEN debit_credit_indicator = 'DR' THEN amount ELSE -amount END
  _is_resolvable: true if account_id in silver_accounts, false otherwise (SIL-T-08).
  _pipeline_run_id: propagated from Bronze source (INV-04).
  config: materialized='external', location='/app/silver/transactions/date={date_var}/data.parquet'

CREATE dbt/models/silver/silver_transactions.yml:
  Tests: unique(transaction_id) (SIL-T-02), not_null(_signed_amount) (SIL-T-05),
  not_null(_pipeline_run_id)

  CRITICAL (R-04): not_null(_pipeline_run_id) dbt test is REQUIRED — enforces INV-04 at build time.

RULES:
- SIL-T-06 (impl guidance): sign from debit_credit_indicator ONLY.
- SIL-T-08: unknown account_id → Silver with _is_resolvable=false, not quarantine.
- INV-04 (GLOBAL): _pipeline_run_id non-null — enforced by dbt test.
- INV-01b: idempotent.
- S1B-dbt-silver-gold: dbt model exclusively.
- No external service calls (INV-07). Each CTE single purpose. Nesting > 2 levels → refactor.

  git add dbt/models/silver/silver_transactions.sql dbt/models/silver/silver_transactions.yml
  git commit -m "3.4 — dbt Silver Transactions: validation, sign assignment, _is_resolvable"
```

**Test Cases:**

| Case | Scenario | Expected |
|---|---|---|
| TC-1 | Clean records | Present in Silver with correct _signed_amount |
| TC-2 | DR record | _signed_amount positive |
| TC-3 | CR record | _signed_amount negative |
| TC-4 | Quarantine-bound records | NOT in Silver |
| TC-5 | Unknown account_id | In Silver with _is_resolvable=false (SIL-T-08) |
| TC-6 | Known account_id | In Silver with _is_resolvable=true |
| TC-7 | `dbt test` passes | unique(transaction_id), not_null(_signed_amount), not_null(_pipeline_run_id) pass |
| TC-8 | Mass conservation | silver + quarantine = bronze (SIL-T-01) |
| TC-9 | _pipeline_run_id non-null | not_null(_pipeline_run_id) dbt test passes (INV-04, R-04) |

**Verification command:**
```bash
docker compose run --rm pipeline dbt run --select silver_transactions \
    --project-dir /app/dbt --profiles-dir /app/dbt \
  && docker compose run --rm pipeline dbt test --select silver_transactions \
    --project-dir /app/dbt --profiles-dir /app/dbt \
  && docker compose run --rm pipeline python -c "
import duckdb; conn = duckdb.connect()
silver = conn.execute(\"SELECT COUNT(*) FROM read_parquet('/app/silver/transactions/date=2024-01-01/data.parquet')\").fetchone()[0]
quar = conn.execute(\"SELECT COUNT(*) FROM read_parquet('/app/quarantine/data.parquet') WHERE transaction_date='2024-01-01'\").fetchone()[0]
bronze = conn.execute(\"SELECT COUNT(*) FROM read_parquet('/app/bronze/transactions/date=2024-01-01/data.parquet')\").fetchone()[0]
assert silver + quar == bronze, f'SIL-T-01 FAIL: {silver}+{quar}!={bronze}'
print('Task 3.4 PASS — mass conservation verified')
"
```

**Invariant enforcement:** SIL-T-01, SIL-T-02, SIL-T-04, SIL-T-05, SIL-T-07, SIL-T-08, INV-01b, INV-04 (GLOBAL — dbt test, R-04), SIL-T-06 (impl guidance).

**Regression classification:** REGRESSION-RELEVANT — Silver Transactions is source for all Gold aggregations. Portable.

---

### Task 3.5 — silver_promoter.py

**Description:**
Implements `pipeline/silver_promoter.py`. Enforces Transaction Codes prerequisite guard
(SIL-REF-01). Invokes dbt Silver models via subprocess. Handles atomic overwrite via
`silver_temp/` (Decision 4). Returns structured result.

**CC Prompt:**
```
Implement pipeline/silver_promoter.py for the Credit Card Transactions Lake.

FUNCTION SIGNATURES:

1. promote_silver_transaction_codes(run_id: str, app_dir: str) -> dict
   Run dbt model: silver_transaction_codes.
   Return: {status, records_written, error_message}

2. promote_silver(date_str: str, run_id: str, app_dir: str) -> dict
   PREREQUISITE GUARD (SIL-REF-01, Decision 6):
     Check /app/silver/transaction_codes/data.parquet exists and has > 0 rows.
     If absent or empty: return status=FAILED,
     error_message="Silver transaction_codes not populated". Do NOT run any dbt models.

   Run dbt models in order: silver_accounts, silver_transactions, silver_quarantine.
   Pass date_str as dbt variable.

   Idempotency — Decision 4 (INV-01b):
     dbt writes to silver_temp/{model}/date={date_str}/data.parquet
     os.rename() to silver/{model}/date={date_str}/data.parquet

3. invoke_dbt_model(model_name: str, app_dir: str, variables: dict | None) -> dict
   Helper: subprocess dbt run --select {model_name}.
   Return: {status, records_written, error_message (no file paths — RL-05b)}.

RULES:
- SIL-REF-01: prerequisite check is FIRST operation in promote_silver().
- Decision 4 atomic rename: silver_temp/ staging + os.rename().
- INV-01b: atomic overwrite guarantees clean state on rerun.
- SIL-REF-02 (impl guidance): promote_silver() does NOT re-run silver_transaction_codes.
- S1B-dbt-silver-gold: dbt invoked via subprocess.
- No external service calls (INV-07).
- Each function must have a single stateable purpose.
  Conditional nesting exceeding two levels is a structural violation.

  git add pipeline/silver_promoter.py
  git commit -m "3.5 — silver_promoter.py: dbt invoker, SIL-REF-01 guard, atomic overwrite"
```

**Test Cases:**

| Case | Scenario | Expected |
|---|---|---|
| TC-1 | promote_silver — transaction_codes populated | status=SUCCESS; Silver partitions written |
| TC-2 | promote_silver — transaction_codes absent | status=FAILED; no dbt models run (SIL-REF-01) |
| TC-3 | promote_silver_transaction_codes | status=SUCCESS; silver/transaction_codes/data.parquet written |
| TC-4 | Atomic overwrite on rerun | Silver partition cleanly replaced (Decision 4) |
| TC-5 | Idempotent rerun | Row counts identical after second call (INV-01b) |
| TC-6 | SIL-REF-02: transaction_codes not re-run | promote_silver() does not invoke silver_transaction_codes dbt model |

**Verification command:**
```bash
docker compose run --rm pipeline python -c "
import sys; sys.path.insert(0, '/app')
from pipeline.silver_promoter import promote_silver
import uuid, duckdb
result = promote_silver('2024-01-01', str(uuid.uuid4()), '/app')
assert result['status'] == 'SUCCESS', f'FAILED: {result}'
conn = duckdb.connect()
silver = conn.execute(\"SELECT COUNT(*) FROM read_parquet('/app/silver/transactions/date=2024-01-01/data.parquet')\").fetchone()[0]
assert silver > 0
print(f'Task 3.5 PASS — {silver} silver transactions')
"
```

**Invariant enforcement:** SIL-REF-01, INV-01b, Decision 4 (impl guidance), SIL-REF-02 (impl guidance), S1B-dbt-silver-gold, GAP-INV-03.

**Regression classification:** REGRESSION-RELEVANT — Silver promoter is integration point for all Silver invariants. Portable.

---

## Session 4 — Gold Computation: dbt Models

**Session goal:** `gold_builder.promote_gold('2024-01-01', run_id, '/app')` returns SUCCESS.
Both Gold Parquet files present. GOLD-D-01 through GOLD-D-04 and GOLD-W-01 through GOLD-W-05
all verified. _is_resolvable=false records excluded from both Gold outputs.

**Branch:** `session/s4_gold_dbt`

**Integration check:**
```bash
docker compose run --rm pipeline python -c "
import sys; sys.path.insert(0, '/app')
from pipeline.gold_builder import promote_gold
import uuid
result = promote_gold('2024-01-01', str(uuid.uuid4()), '/app')
assert result['status'] == 'SUCCESS', f'FAILED: {result}'
import duckdb; conn = duckdb.connect()
daily = conn.execute(\"SELECT COUNT(*) FROM read_parquet('/app/gold/daily_summary/data.parquet')\").fetchone()[0]
weekly = conn.execute(\"SELECT COUNT(*) FROM read_parquet('/app/gold/weekly_summary/data.parquet')\").fetchone()[0]
assert daily > 0 and weekly > 0
print(f'S4 INTEGRATION PASS — daily={daily}, weekly={weekly}')
"
```

---

### Task 4.1 — dbt Gold Daily Summary Model

**Description:**
Implements `gold_daily_summary` dbt model. One record per transaction_date (GOLD-D-01).
Resolvable transactions only. Reads Silver exclusively.

**R-04 fix (v1.2):** `not_null: _pipeline_run_id` dbt schema test added.

**CC Prompt:**
```
Implement the dbt Gold Daily Summary model for the Credit Card Transactions Lake.

CREATE dbt/models/gold/gold_daily_summary.sql:
  Source: {{ ref('silver_transactions') }} — Silver ONLY, never Bronze (S1B-gold-source).
  Filter: WHERE _is_resolvable = true (GOLD-D-02).
  GROUP BY transaction_date.
  Columns: transaction_date, total_signed_amount (SUM), total_transactions (COUNT),
           _pipeline_run_id (MAX)
  config: materialized='external', location='/app/gold/daily_summary/data.parquet'

CREATE dbt/models/gold/gold_daily_summary.yml:
  Tests: not_null(transaction_date), unique(transaction_date) (GOLD-D-01),
  not_null(total_signed_amount), not_null(total_transactions), not_null(_pipeline_run_id)

  CRITICAL (R-04): not_null(_pipeline_run_id) dbt test is REQUIRED — enforces INV-04 at build time.

RULES:
- GOLD-D-02: _is_resolvable=true filter mandatory.
- GOLD-D-03: SUM(_signed_amount) — not SUM(amount).
- GAP-INV-05: external materialization overwrites — never append.
- S1B-gold-source: ref('silver_transactions') only.
- INV-01d: idempotent.
- INV-04 (GLOBAL): _pipeline_run_id non-null — enforced by dbt test.

  git add dbt/models/gold/
  git commit -m "4.1 — dbt Gold Daily Summary: one record per date, resolvable only"
```

**Test Cases:**

| Case | Scenario | Expected |
|---|---|---|
| TC-1 | `dbt run` | Exit 0; gold/daily_summary/data.parquet created |
| TC-2 | One record per date | unique(transaction_date) passes (GOLD-D-01) |
| TC-3 | _is_resolvable=false excluded | total_transactions < bronze row count |
| TC-4 | total_signed_amount = SUM(_signed_amount) | Manual spot-check vs Silver (GOLD-D-03) |
| TC-5 | _pipeline_run_id non-null | not_null(_pipeline_run_id) dbt test passes (INV-04, R-04) |
| TC-6 | Idempotent rerun | Values identical after second run (INV-01d) |

**Verification command:**
```bash
docker compose run --rm pipeline dbt run --select gold_daily_summary \
    --project-dir /app/dbt --profiles-dir /app/dbt \
  && docker compose run --rm pipeline dbt test --select gold_daily_summary \
    --project-dir /app/dbt --profiles-dir /app/dbt \
  && echo "Task 4.1 PASS"
```

**Invariant enforcement:** GOLD-D-01, GOLD-D-02, GOLD-D-03, GOLD-D-04, GAP-INV-05, INV-01d, INV-04 (GLOBAL — dbt test, R-04), S1B-gold-source.

**Regression classification:** REGRESSION-RELEVANT — daily summary is primary Gold output. Portable.

---

### Task 4.2 — dbt Gold Weekly Account Summary Model

**Description:**
Implements `gold_weekly_account_summary` dbt model. One record per account per ISO
week. Closing balance from Silver Accounts via INNER JOIN.

**R-04 fix (v1.2):** `not_null: _pipeline_run_id` dbt schema test added.

**CC Prompt:**
```
Implement the dbt Gold Weekly Account Summary model for the Credit Card Transactions Lake.

CREATE dbt/models/gold/gold_weekly_account_summary.sql:
  Sources: {{ ref('silver_transactions') }}, {{ ref('silver_accounts') }}
  Filter: silver_transactions WHERE _is_resolvable = true
  GROUP BY account_id, DATE_TRUNC('week', transaction_date)
  Columns: account_id, week_start_date, total_purchases (COUNT PURCHASE),
           avg_purchase_amount, total_payments, total_fees, total_interest,
           closing_balance (INNER JOIN silver_accounts), _pipeline_run_id (MAX)
  config: materialized='external', location='/app/gold/weekly_summary/data.parquet'

CRITICAL — closing_balance:
  Use INNER JOIN (not LEFT JOIN) to silver_accounts.
  closing_balance null = pipeline failure (GOLD-W-05, GAP-INV-06).

CREATE dbt/models/gold/gold_weekly_account_summary.yml:
  Tests: not_null(account_id), not_null(week_start_date),
  unique combination of (account_id, week_start_date) (GOLD-W-01),
  not_null(closing_balance) (GOLD-W-05), not_null(_pipeline_run_id)

  CRITICAL (R-04): not_null(_pipeline_run_id) dbt test is REQUIRED — enforces INV-04 at build time.

RULES:
- GOLD-W-05: closing_balance non-null — INNER JOIN + not_null test.
- GAP-INV-06: INNER JOIN enforces every Gold account has Silver Accounts record.
- GAP-INV-05: external materialization overwrites.
- S1B-gold-source: Silver refs only.
- INV-04 (GLOBAL): _pipeline_run_id non-null — enforced by dbt test.

  git add dbt/models/gold/gold_weekly_account_summary.sql \
          dbt/models/gold/gold_weekly_account_summary.yml
  git commit -m "4.2 — dbt Gold Weekly Account Summary: per-account-week, closing balance"
```

**Test Cases:**

| Case | Scenario | Expected |
|---|---|---|
| TC-1 | `dbt run` | Exit 0; gold/weekly_summary/data.parquet created |
| TC-2 | One record per account per week | unique(account_id, week_start_date) passes (GOLD-W-01) |
| TC-3 | closing_balance non-null | not_null(closing_balance) passes (GOLD-W-05) |
| TC-4 | total_purchases correct | COUNT(PURCHASE) matches Silver spot-check |
| TC-5 | avg_purchase_amount correct | AVG of PURCHASE _signed_amount matches Silver |
| TC-6 | _is_resolvable=false excluded | Accounts with _is_resolvable=false absent from weekly |
| TC-7 | _pipeline_run_id non-null | not_null(_pipeline_run_id) dbt test passes (INV-04, R-04) |
| TC-8 | Idempotent rerun | Values identical after second run (INV-01d) |

**Verification command:**
```bash
docker compose run --rm pipeline dbt run --select gold_weekly_account_summary \
    --project-dir /app/dbt --profiles-dir /app/dbt \
  && docker compose run --rm pipeline dbt test --select gold_weekly_account_summary \
    --project-dir /app/dbt --profiles-dir /app/dbt \
  && echo "Task 4.2 PASS"
```

**Invariant enforcement:** GOLD-W-01 through GOLD-W-05, GAP-INV-05, GAP-INV-06, GOLD-D-02, INV-01d, INV-04 (GLOBAL — dbt test, R-04), S1B-gold-source.

**Regression classification:** REGRESSION-RELEVANT — weekly summary is second primary Gold output. Portable.

---

### Task 4.3 — gold_builder.py

**Description:**
Implements `pipeline/gold_builder.py`. Invokes both dbt Gold models via subprocess.
Returns structured result to pipeline entry points.

**CC Prompt:**
```
Implement pipeline/gold_builder.py for the Credit Card Transactions Lake.

FUNCTION SIGNATURE:
  def promote_gold(date_str: str, run_id: str, app_dir: str) -> dict

Returns: {status: "SUCCESS"|"FAILED", records_written: int|None, error_message: str|None}

IMPLEMENTATION:
1. Run dbt models in order: gold_daily_summary, gold_weekly_account_summary.
   Pass date_str as dbt variable.
2. Source is Silver only (S1B-gold-source).
3. If either model fails: return status=FAILED. error_message must not contain paths (RL-05b).
4. Gold fully recomputed — external materialization handles overwrite (GAP-INV-05).
5. No external service calls (INV-07).
6. Each function must have a single stateable purpose.
   Conditional nesting exceeding two levels is a structural violation.

  git add pipeline/gold_builder.py
  git commit -m "4.3 — gold_builder.py: dbt Gold invoker, daily and weekly summary"
```

**Test Cases:**

| Case | Scenario | Expected |
|---|---|---|
| TC-1 | promote_gold — Silver populated | status=SUCCESS; both Gold files present |
| TC-2 | promote_gold — Silver empty | status=FAILED |
| TC-3 | Idempotent rerun | status=SUCCESS; Gold unchanged (INV-01d) |

**Verification command:**
```bash
docker compose run --rm pipeline python -c "
import sys, os; sys.path.insert(0, '/app')
from pipeline.gold_builder import promote_gold
import uuid
result = promote_gold('2024-01-01', str(uuid.uuid4()), '/app')
assert result['status'] == 'SUCCESS', f'FAILED: {result}'
assert os.path.exists('/app/gold/daily_summary/data.parquet')
assert os.path.exists('/app/gold/weekly_summary/data.parquet')
print('Task 4.3 PASS')
"
```

**Invariant enforcement:** GAP-INV-05, INV-01d, S1B-gold-source, S1B-dbt-silver-gold.

**Regression classification:** REGRESSION-RELEVANT — gold_builder is integration point for all Gold invariants. Portable.

---

## Session 5 — Incremental Pipeline and Control Layer

**Session goal:** Full pipeline orchestration complete for both entry points. Historical
run processes all 6 dates end-to-end and advances watermark to 2024-01-06. Incremental
run processes watermark+1. Both entry points verified independently.

**Branch:** `session/s5_incremental`

**Integration check:**
```bash
docker compose run --rm pipeline python pipeline/pipeline_historical.py \
    --start-date 2024-01-01 --end-date 2024-01-06 \
  && docker compose run --rm pipeline python -c "
import sys; sys.path.insert(0, '/app')
from pipeline.control_manager import get_watermark
wm = get_watermark('/app/pipeline')
assert wm == '2024-01-06', f'Watermark wrong: {wm}'
print(f'S5 INTEGRATION PASS — watermark={wm}')
"
```

---

### Task 5.1 — pipeline_historical.py — Full Orchestration (Silver + Gold + Watermark)

**Description:**
Extends `pipeline_historical.py` to call `silver_promoter.promote_silver()` and
`gold_builder.promote_gold()` after Bronze succeeds. Advances watermark only after
all stages return SUCCESS and all run log entries are written.

**CC Prompt:**
```
Extend pipeline/pipeline_historical.py to complete full pipeline orchestration:
Bronze → Silver → Gold → Run Log → Watermark.

CURRENT STATE: Bronze ingestion + run log only.
ADD for each date in the loop:

STEP 1 — Silver:
  Call silver_promoter.promote_silver(date_str, run_id, APP_DIR).
  Write run log entries for silver_accounts, silver_transactions, silver_quarantine.
  If FAILED: write FAILED entries for silver_*. Write SKIPPED for gold_*.
  Do NOT call gold_builder. Do NOT advance watermark. Continue to next date.

STEP 2 — Gold:
  Call gold_builder.promote_gold(date_str, run_id, APP_DIR).
  Write run log entries for gold_daily_summary, gold_weekly_summary.
  If FAILED: write FAILED entries for gold_*. Do NOT advance watermark. Continue.

STEP 3 — Watermark (INV-02, Decision 7):
  ONLY when Bronze + Silver + Gold all SUCCESS:
    a. Confirm all run log entries for this date written with SUCCESS.
    b. THEN call control_manager.set_watermark(date_str, PIPELINE_DIR).
    Watermark write is the FINAL operation.

STEP 4 — Guards (S1B-01b, GAP-INV-03):
  Bronze FAILED → no Silver, no Gold.
  Silver FAILED → no Gold.

No external service calls (INV-07).
Each function must have a single stateable purpose.
Conditional nesting exceeding two levels is a structural violation.

  git add pipeline/pipeline_historical.py
  git commit -m "5.1 — pipeline_historical.py: full Bronze→Silver→Gold→watermark orchestration"
```

**Test Cases:**

| Case | Scenario | Expected |
|---|---|---|
| TC-1 | Full run 2024-01-01 to 2024-01-06 | All 6 dates processed; watermark = 2024-01-06 |
| TC-2 | Run log — all models all dates | run_log has bronze_*, silver_*, gold_* entries for each date |
| TC-3 | Watermark only after all SUCCESS | Simulated failure: watermark not advanced for that date |
| TC-4 | Silver FAILED → gold SKIPPED | SKIPPED entries for gold_* when silver FAILED |
| TC-5 | S1B-06: watermark is final write | run_log complete before control.parquet updated |
| TC-6 | GAP-INV-03: layer ordering enforced | Bronze complete before Silver; Silver before Gold |

**Verification command:**
```bash
docker compose run --rm pipeline python pipeline/pipeline_historical.py \
    --start-date 2024-01-01 --end-date 2024-01-06 \
  && docker compose run --rm pipeline python -c "
import sys; sys.path.insert(0, '/app')
from pipeline.control_manager import get_watermark
from pipeline.run_logger import get_run_log
wm = get_watermark('/app/pipeline')
assert wm == '2024-01-06', f'Watermark wrong: {wm}'
log = get_run_log()
assert 'gold_daily_summary' in log.model_name.values
assert 'silver_transactions' in log.model_name.values
print(f'Task 5.1 PASS — watermark={wm}, log rows={len(log)}')
"
```

**Invariant enforcement:** INV-02, S1B-06, GAP-INV-03, S1B-01b, INV-05a, RL-01a.

**Regression classification:** REGRESSION-RELEVANT — complete historical orchestration is the primary end-to-end path. Portable.

---

### Task 5.2 — pipeline_incremental.py

**Description:**
Implements `pipeline_incremental.py`. Reads watermark, derives watermark+1, runs full
pipeline for that date. Handles no-op with SKIPPED run log entries. Does not re-ingest
transaction_codes.

**R-01 fix (v1.2):** Explicit cold-start guard added. If `get_watermark()` returns
None, pipeline raises `RuntimeError` and exits non-zero with a clear message directing
the operator to run `pipeline_historical.py` first.

**CC Prompt:**
```
Implement pipeline/pipeline_incremental.py — the incremental pipeline entry point.

INVOCATION (no CLI arguments):
  python pipeline/pipeline_incremental.py

IMPLEMENTATION RULES:

1. Generate run_id = str(uuid.uuid4()) at invocation start (OQ-3, RL-02).

2. Call control_manager.get_watermark(PIPELINE_DIR).
   COLD-START GUARD (R-01): If None returned:
     print("ERROR: No watermark found. Run pipeline_historical.py first.")
     sys.exit(1)
   This is not a silent soft-exit — it is a hard failure with non-zero exit code.
   If watermark present: target_date = watermark + 1 calendar day.

3. If source/transactions_{target_date}.csv absent:
   Write SKIPPED run log entries for ALL 8 models (OQ-2).
   Do NOT write to any data layer (GAP-INV-02).
   Do NOT advance watermark (INV-02).
   Print "No source file for {target_date} — SKIPPED" and exit 0.

4. Full pipeline for target_date:
   a. bronze_loader('transactions', target_date, ...)
   b. bronze_loader('accounts', target_date, ...)
   c. silver_promoter.promote_silver(target_date, run_id, APP_DIR)
   d. gold_builder.promote_gold(target_date, run_id, APP_DIR)
   Write run log entries after each step.

5. Same failure guards as pipeline_historical.py (S1B-01b, GAP-INV-03).

6. Advance watermark ONLY after full SUCCESS (INV-02):
   Write all run log SUCCESS entries FIRST, then set_watermark().

7. Do NOT run bronze_loader for transaction_codes (SIL-REF-02 impl guidance).

8. S1B-02: same module layer as historical — identical output for same input.

9. No external service calls (INV-07).
10. Each function must have a single stateable purpose.
    Conditional nesting exceeding two levels is a structural violation.

CONSTANTS: APP_DIR, SOURCE_DIR, BRONZE_DIR, PIPELINE_DIR

  git add pipeline/pipeline_incremental.py
  git commit -m "5.2 — pipeline_incremental.py: watermark+1, cold-start guard, incremental processing"
```

**Test Cases:**

| Case | Scenario | Expected |
|---|---|---|
| TC-1 | Incremental after historical | Processes watermark+1; watermark advances |
| TC-2 | No source file for watermark+1 | SKIPPED run log written; no data written; watermark unchanged (GAP-INV-02, OQ-2) |
| TC-cold-start | No watermark set (cold start) | Prints error message; exits with code 1 (R-01) |
| TC-4 | Transaction codes NOT re-ingested | No bronze_transaction_codes in run log for incremental run (SIL-REF-02) |
| TC-5 | S1B-02: identical output to historical | Bronze/Silver/Gold row counts identical for same date |
| TC-6 | INV-02: watermark only on full success | Simulated Silver failure: watermark unchanged |

**Verification command:**
```bash
docker compose run --rm pipeline python pipeline/pipeline_incremental.py \
  && docker compose run --rm pipeline python -c "
import sys; sys.path.insert(0, '/app')
from pipeline.control_manager import get_watermark
wm = get_watermark('/app/pipeline')
print(f'Watermark after incremental: {wm}')
assert wm is not None
print('Task 5.2 PASS')
" \
  && docker compose run --rm pipeline python -c "
import subprocess, sys
result = subprocess.run(['python', 'pipeline/pipeline_incremental.py'],
  capture_output=True, text=True,
  env={**__import__('os').environ, 'PIPELINE_DIR': '/tmp/empty_pipeline_dir'})
assert result.returncode == 1, f'Expected exit 1 on cold start, got {result.returncode}'
assert 'pipeline_historical' in result.stdout or 'pipeline_historical' in result.stderr
print('TC-cold-start PASS: cold-start guard exits 1 with informative message (R-01)')
"
```

**Invariant enforcement:** INV-02, GAP-INV-02, INV-05b, RL-01a, S1B-02, SIL-REF-02 (impl guidance), S1B-01b, GAP-INV-03.

**Regression classification:** REGRESSION-RELEVANT — incremental is the operational runtime path. Portable.

---

### Task 5.3 — pipeline_historical.py — Transaction Codes First-Load

**Description:**
Restructures `pipeline_historical.py` so Transaction Codes Bronze ingestion and Silver
promotion runs ONCE before the date loop. Removes transaction_codes handling from inside
the loop.

**R-03 fix (v1.2):** Idempotency handling added for Silver transaction_codes on
historical rerun. If `silver/transaction_codes/data.parquet` already exists and row
count matches Bronze, skip reload. If row count differs, overwrite atomically. New
TC-5 (rerun) test case added.

**CC Prompt:**
```
Update pipeline/pipeline_historical.py to move Transaction Codes load to a
pre-loop STEP 0.

PROBLEM: Transaction Codes currently loaded inside the date loop on the first date.
silver_promoter.promote_silver() SIL-REF-01 guard checks Silver transaction_codes
is populated before it runs — but inside the loop it hasn't been promoted yet
when the first date's promote_silver() is called.

FIX — Add before the date loop begins:

STEP 0 — Transaction Codes (runs ONCE per historical invocation):
  a. Check Silver transaction_codes idempotency (R-03):
     If /app/silver/transaction_codes/data.parquet exists:
       Get Silver row count.
       Get Bronze transaction_codes row count.
       If counts match: log "silver_transaction_codes already populated, skipping reload"
         and skip to date loop. SIL-REF-01 guard will pass.
       If counts differ: proceed with reload (overwrite atomically).
     If /app/silver/transaction_codes/data.parquet absent: proceed with fresh load.
  b. bronze_loader.load_bronze('transaction_codes', start_date, run_id, ...)
  c. Write run log entry for bronze_transaction_codes.
  d. If FAILED: write FAILED entry, abort entire historical run.
  e. silver_promoter.promote_silver_transaction_codes(run_id, APP_DIR)
  f. Write run log entry for silver_transaction_codes.
  g. If FAILED: write FAILED entry, abort entire historical run.

THEN the date loop runs — promote_silver() per date finds Silver transaction_codes
populated and SIL-REF-01 guard passes.

ALSO: remove any transaction_codes Bronze loading from inside the date loop.
Transaction Codes loaded exactly once per historical invocation — not per date.

No external service calls (INV-07).
Each function must have a single stateable purpose.
Conditional nesting exceeding two levels is a structural violation.

  git add pipeline/pipeline_historical.py
  git commit -m "5.3 — pipeline_historical.py: transaction_codes first-load, rerun idempotency"
```

**Test Cases:**

| Case | Scenario | Expected |
|---|---|---|
| TC-1 | Fresh historical run | silver/transaction_codes/data.parquet exists before first date Silver promotion |
| TC-2 | Transaction codes Bronze fails | Historical run aborts; no date processing |
| TC-3 | Transaction codes loaded exactly once per run | run_log has exactly 1 bronze_transaction_codes entry per run_id |
| TC-4 | SIL-REF-01 satisfied for all 6 dates | promote_silver() SUCCESS for all 6 dates |
| TC-5 | Second historical run (rerun) — Silver TC row count matches Bronze | Reload skipped; existing Silver transaction_codes preserved; SIL-REF-01 passes (R-03) |

**Verification command:**
```bash
docker compose run --rm pipeline python pipeline/pipeline_historical.py \
    --start-date 2024-01-01 --end-date 2024-01-06 \
  && docker compose run --rm pipeline python -c "
import sys; sys.path.insert(0, '/app')
from pipeline.run_logger import get_run_log
import duckdb; conn = duckdb.connect()
log = get_run_log()
for rid in log.run_id.unique():
    subset = log[(log.run_id == rid) & (log.model_name == 'bronze_transaction_codes')]
    assert len(subset) <= 1, f'Expected at most 1 transaction_codes entry per run_id, got {len(subset)}'
silver_tc = conn.execute(\"SELECT COUNT(*) FROM read_parquet('/app/silver/transaction_codes/data.parquet')\").fetchone()[0]
assert silver_tc > 0, 'Silver transaction_codes empty'
print(f'Task 5.3 PASS — transaction_codes loaded once per invocation, silver_tc rows={silver_tc}')
" \
  && docker compose run --rm pipeline python pipeline/pipeline_historical.py \
    --start-date 2024-01-01 --end-date 2024-01-06 \
  && echo "TC-5 rerun: PASS — second historical run completed without error (R-03)"
```

**Invariant enforcement:** SIL-REF-01, GAP-INV-01b, Decision 6, INV-01b (analogous for transaction_codes Silver, R-03).

**Regression classification:** REGRESSION-RELEVANT — transaction_codes first-load is prerequisite for entire historical run. Portable.

---

## Session 6 — End-to-End Verification

**Session goal:** Clean-state historical run across all 6 seed dates succeeds end-to-end.
Incremental no-op for date 7 writes SKIPPED entries and does not advance watermark.
All 53 invariants verified. Idempotency and S1B-02 cross-entry-point equivalence confirmed.

**Branch:** `session/s6_e2e_verification`

**Integration check:**
```bash
rm -rf bronze/ silver/ gold/ quarantine/ pipeline/control.parquet pipeline/run_log.parquet \
  && mkdir -p bronze silver silver_temp gold quarantine \
  && docker compose run --rm pipeline python pipeline/pipeline_historical.py \
    --start-date 2024-01-01 --end-date 2024-01-06 \
  && docker compose run --rm pipeline python -c "
import sys, duckdb; sys.path.insert(0, '/app')
from pipeline.control_manager import get_watermark
wm = get_watermark('/app/pipeline')
assert wm == '2024-01-06', f'Watermark wrong: {wm}'
conn = duckdb.connect()
for date in ['2024-01-0' + str(d) for d in range(1,7)]:
    s = conn.execute(f\"SELECT COUNT(*) FROM read_parquet('/app/silver/transactions/date={date}/data.parquet')\").fetchone()[0]
    b = conn.execute(f\"SELECT COUNT(*) FROM read_parquet('/app/bronze/transactions/date={date}/data.parquet')\").fetchone()[0]
    try: q = conn.execute(f\"SELECT COUNT(*) FROM read_parquet('/app/quarantine/data.parquet') WHERE transaction_date='{date}'\").fetchone()[0]
    except: q = 0
    assert s + q == b, f'SIL-T-01 FAIL {date}: {s}+{q}!={b}'
print('S6 INTEGRATION PASS — watermark correct, mass conservation verified all 6 dates')
"
```

---

### Task 6.1 — Invariant Audit: All 53 Invariants Verified

**Description:**
Systematic verification that every invariant in INVARIANTS.md has at least one passing
test. Verifies all 10 implementation guidance items are correctly embedded in code.
Verifies `not_null(_pipeline_run_id)` dbt tests pass for all Silver and Gold models (R-04).

**CC Prompt:**
```
Produce a full invariant coverage verification for the Credit Card Transactions Lake.

Load docs/INVARIANTS.md. For each of the 53 invariants, verify and record:
| Invariant ID | Condition summary | Verified by | Result |

IMPLEMENTATION GUIDANCE — verify embedding in code:
- INV-07: no requests/urllib/socket imports in any pipeline module
- INV-10: bronze_loader uses bronze/{entity}/date={date_str}/data.parquet
- SIL-T-06: silver_transactions.sql uses ONLY debit_credit_indicator for sign
- SIL-Q-03: silver_quarantine.sql selects all Bronze source columns unchanged
- SIL-REF-02: pipeline_incremental.py has no bronze_loader call for transaction_codes
- RL-03: run_log.parquet field values correct — query and verify
- RL-04: records_rejected null for Bronze and Gold — query run_log
- RL-05a: error_message null on SUCCESS — query run_log
- Decision 4 atomic rename: silver_temp on same volume as silver (Task 1.2 mount probe)
- S1B-schema-evolution: expected schemas hardcoded in bronze_loader.py

R-04 VERIFICATION: confirm not_null(_pipeline_run_id) dbt test exists and passes for
  silver_transaction_codes, silver_accounts, silver_quarantine, silver_transactions,
  gold_daily_summary, gold_weekly_account_summary.

Record all results in sessions/S6_VERIFICATION_RECORD.md.

  git add sessions/S6_VERIFICATION_RECORD.md
  git commit -m "6.1 — Invariant audit: all 53 invariants verified"
```

**Test Cases:**

| Case | Scenario | Expected |
|---|---|---|
| TC-1 | Coverage table complete | 53 rows, zero gaps |
| TC-2 | INV-04 (GLOBAL) | Zero null _pipeline_run_id in Bronze, Silver, Quarantine, Gold |
| TC-3 | SIL-T-01 mass conservation | silver + quarantine = bronze for all 6 dates |
| TC-4 | SIL-T-02 no duplicates | unique(transaction_id) dbt test passes |
| TC-5 | INV-05a | All run_ids in data layers have SUCCESS run log entries |
| TC-6 | INV-05b | No SKIPPED run_id appears in any data layer Parquet |
| TC-7 | R-04 dbt tests | not_null(_pipeline_run_id) passes for all 6 Silver and Gold models |

**Verification command:**
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
print('Task 6.1 PASS')
"
```

**Invariant enforcement:** This task IS the invariant audit — all 53 verified here.

**Regression classification:** REGRESSION-RELEVANT — verification queries are regression suite source. Portable.

---

### Task 6.2 — No-Op Path Verification (Date 7)

**Description:**
Verifies the complete no-op path: `pipeline_incremental.py` with watermark at
2024-01-06 and no source file for 2024-01-07. SKIPPED run log for all 8 models.
Watermark unchanged. No data written.

**CC Prompt:**
```
Verify the no-op path for the Credit Card Transactions Lake.

Precondition: watermark = 2024-01-06. source/transactions_2024-01-07.csv absent.

RUN: python pipeline/pipeline_incremental.py

VERIFY:
1. Exit code 0 (GAP-INV-02).
2. Watermark still 2024-01-06 (INV-02).
3. run_log has SKIPPED entries for ALL 8 models for the incremental run_id (OQ-2, RL-01a).
   Expected 8 models: bronze_transactions, bronze_accounts, silver_transaction_codes,
   silver_accounts, silver_transactions, silver_quarantine, gold_daily_summary,
   gold_weekly_summary.
4. SKIPPED run_id NOT in bronze/transactions/date=2024-01-07/ (must not exist).
5. SKIPPED run_id NOT in silver/transactions/date=2024-01-07/ (must not exist).
6. No Parquet written anywhere for 2024-01-07 (INV-05b).

Record all results in sessions/S6_VERIFICATION_RECORD.md.

  git add sessions/S6_VERIFICATION_RECORD.md
  git commit -m "6.2 — No-op path verified: SKIPPED entries, watermark unchanged, no data written"
```

**Test Cases:**

| Case | Scenario | Expected |
|---|---|---|
| TC-1 | Exit code 0 | No crash (GAP-INV-02) |
| TC-2 | Watermark unchanged | get_watermark() = "2024-01-06" (INV-02) |
| TC-3 | 8 SKIPPED entries | run_log has 8 SKIPPED rows for incremental run_id (OQ-2) |
| TC-4 | No Bronze for date 7 | bronze/transactions/date=2024-01-07/ does not exist |
| TC-5 | SKIPPED run_id absent from data layers | INV-05b satisfied |

**Verification command:**
```bash
docker compose run --rm pipeline python pipeline/pipeline_incremental.py \
  && docker compose run --rm pipeline python -c "
import sys, os; sys.path.insert(0, '/app')
from pipeline.control_manager import get_watermark
from pipeline.run_logger import get_run_log
wm = get_watermark('/app/pipeline')
assert wm == '2024-01-06', f'Watermark advanced: {wm}'
log = get_run_log()
latest_run_id = log.sort_values('started_at').iloc[-1]['run_id']
skipped = log[(log.run_id == latest_run_id) & (log.status == 'SKIPPED')]
assert len(skipped) >= 8, f'Expected 8 SKIPPED, got {len(skipped)}'
assert not os.path.exists('/app/bronze/transactions/date=2024-01-07')
print('Task 6.2 PASS — no-op path fully verified')
"
```

**Invariant enforcement:** GAP-INV-02, INV-02, INV-05b, OQ-2, RL-01a.

**Regression classification:** REGRESSION-RELEVANT — no-op path is a correctness invariant for watermark and data layer integrity. Portable.

---

### Task 6.3 — Idempotency and S1B-02 Cross-Entry-Point Verification

**Description:**
Verifies historical rerun produces identical output. Verifies incremental produces
identical output to historical for same date. Confirms INV-01a, INV-01b, INV-01d, S1B-02.

**CC Prompt:**
```
Verify idempotency and cross-entry-point equivalence (S1B-02).

PART 1 — Historical rerun idempotency:
  1. Record Bronze, Silver, Gold row counts for all 6 dates.
  2. Run pipeline_historical.py --start-date 2024-01-01 --end-date 2024-01-06 again.
  3. Assert all counts identical (INV-01a, INV-01b, INV-01d).

PART 2 — S1B-02 cross-entry-point:
  1. Record Bronze, Silver, Gold row counts for 2024-01-01 from historical run.
  2. Delete 2024-01-01 partitions from Bronze, Silver, Gold.
  3. Reset watermark to "2023-12-31".
  4. Run pipeline_incremental.py.
  5. Assert counts match historical output.

Record all results in sessions/S6_VERIFICATION_RECORD.md.

  git add sessions/S6_VERIFICATION_RECORD.md
  git commit -m "6.3 — Idempotency and S1B-02 cross-entry-point equivalence verified"
```

**Test Cases:**

| Case | Scenario | Expected |
|---|---|---|
| TC-1 | Historical rerun — Bronze | Row counts identical (INV-01a) |
| TC-2 | Historical rerun — Silver | Row counts identical (INV-01b) |
| TC-3 | Historical rerun — Gold | Values identical (INV-01d) |
| TC-4 | Incremental vs historical Bronze 2024-01-01 | Row count identical (S1B-02) |
| TC-5 | Incremental vs historical Silver 2024-01-01 | Row count identical (S1B-02) |
| TC-6 | Incremental vs historical Gold 2024-01-01 | total_signed_amount and total_transactions identical (S1B-02) |

**Verification command:**
```bash
docker compose run --rm pipeline python pipeline/pipeline_historical.py \
    --start-date 2024-01-01 --end-date 2024-01-06 \
  && docker compose run --rm pipeline python -c "
import duckdb; conn = duckdb.connect()
for date in ['2024-01-0' + str(d) for d in range(1,7)]:
    silver = conn.execute(f\"SELECT COUNT(*) FROM read_parquet('/app/silver/transactions/date={date}/data.parquet')\").fetchone()[0]
    print(f'{date}: {silver} silver rows')
print('Task 6.3 idempotency rerun complete — verify counts match pre-rerun values')
"
```

**Invariant enforcement:** INV-01a, INV-01b, INV-01d, S1B-02.

**Regression classification:** REGRESSION-RELEVANT — idempotency is a foundational correctness property. Portable.

---

## Invariant Traceability Matrix

Every invariant in INVARIANTS.md traceable to at least one task. Zero gaps.

| Invariant ID | Primary Task | Verification Task |
|---|---|---|
| INV-01a | 2.2 | 6.3 |
| INV-01b | 3.5 | 6.3 |
| INV-01d | 4.3 | 6.3 |
| INV-02 | 5.1, 5.2 | 6.2 |
| INV-04 (GLOBAL) | All Bronze/Silver/Gold tasks | 6.1 |
| INV-05a | 2.1, 5.1 | 6.1 |
| INV-05b | 5.2 | 6.2 |
| INV-06 | 2.2 | 2.2 |
| INV-08 | 2.2 | 2.2 |
| INV-09 | 2.2 | 2.2 |
| GAP-INV-01a | 2.3 | 2.3 |
| GAP-INV-01b | 5.3 | 5.3 |
| GAP-INV-02 | 5.2 | 6.2 |
| GAP-INV-03 | 5.1, 5.2 | 5.1 |
| GAP-INV-04 | 3.2 | 3.2 |
| GAP-INV-05 | 4.1, 4.2 | 4.1, 4.2 |
| GAP-INV-06 | 4.2 | 4.2 |
| GAP-INV-07 | 3.3 | 3.3 |
| SIL-T-01 | 3.3, 3.4 | 6.1 |
| SIL-T-02 | 3.3, 3.4 | 3.4 |
| SIL-T-04 | 3.4 | 3.4 |
| SIL-T-05 | 3.4 | 3.4 |
| SIL-T-07 | 3.3 | 3.3 |
| SIL-T-08 | 3.4 | 3.4 |
| SIL-A-01 | 3.2 | 3.2 |
| SIL-Q-01 | 3.3 | 3.3 |
| SIL-Q-02 | 3.3 | 3.3 |
| SIL-REF-01 | 3.5 | 3.5 |
| GOLD-D-01 | 4.1 | 4.1 |
| GOLD-D-02 | 4.1, 4.2 | 4.1, 4.2 |
| GOLD-D-03 | 4.1 | 4.1 |
| GOLD-D-04 | 4.1 | 4.1 |
| GOLD-W-01 | 4.2 | 4.2 |
| GOLD-W-02 | 4.2 | 4.2 |
| GOLD-W-03 | 4.2 | 4.2 |
| GOLD-W-04 | 4.2 | 4.2 |
| GOLD-W-05 | 4.2 | 4.2 |
| RL-01a | 2.1, 2.3, 5.2 | 6.2 |
| RL-01b | 2.1 | 2.1 |
| RL-02 | 2.1, 2.3, 5.2 | 2.1 |
| RL-05b | 2.1 | 2.1 |
| S1B-01b | 5.1, 5.2 | 5.1 |
| S1B-02 | 5.1, 5.2 | 6.3 |
| S1B-03 | 2.2 | 2.2 |
| S1B-05 | 2.1 | 2.1 |
| S1B-bronze-python | 2.2 | 2.2 |
| S1B-dbt-silver-gold | 3.1–3.5, 4.1–4.3 | 6.1 |
| S1B-files | 5.1, 5.2 | 5.1 |
| S1B-gold-source | 4.1, 4.2, 4.3 | 4.1 |
| S1B-parquet | All output tasks | 6.1 |
| S1B-schema | 2.2 | 2.2 |
| INV-07 (impl guidance) | All module tasks | 6.1 |
| INV-10 (impl guidance) | 2.2 | 2.2 |
| SIL-T-06 (impl guidance) | 3.4 | 6.1 |
| SIL-Q-03 (impl guidance) | 3.3 | 6.1 |
| SIL-REF-02 (impl guidance) | 3.5, 5.2 | 6.1 |
| RL-03 (impl guidance) | 2.1 | 6.1 |
| RL-04 (impl guidance) | 2.1 | 2.1 |
| RL-05a (impl guidance) | 2.1 | 2.1 |
| Decision 4 atomic rename (impl guidance) | 1.2, 3.5 | 1.2 |
| S1B-schema-evolution (impl guidance) | 2.2 | 6.1 |

**Coverage result: All 53 invariants + 10 implementation guidance items traced. Zero gaps.**

---

## Implementation Guidance Embedding Checklist

| Guidance Item | Embedded In Task | Status |
|---|---|---|
| INV-07 — No external service calls | 1.3, 2.1, 2.2, 2.3, 2.4, 3.1–3.5, 4.1–4.3, 5.1–5.3 | ✅ EMBEDDED |
| INV-10 — Bronze path convention | 2.2 | ✅ EMBEDDED |
| SIL-T-06 — Sign from debit_credit_indicator exclusively | 3.4 | ✅ EMBEDDED |
| SIL-Q-03 — Quarantine retains original Bronze fields | 3.3 | ✅ EMBEDDED |
| SIL-REF-02 — Transaction Codes not reloaded in incremental | 3.5, 5.2 | ✅ EMBEDDED |
| RL-03 — Run log records correctly | 2.1 | ✅ EMBEDDED |
| RL-04 — records_rejected null for Bronze and Gold | 2.1 | ✅ EMBEDDED |
| RL-05a — error_message null on SUCCESS | 2.1 | ✅ EMBEDDED |
| Decision 4 atomic rename — same Docker volume | 1.2 | ✅ EMBEDDED |
| S1B-schema-evolution — Fixed schema hardcoded | 2.2 | ✅ EMBEDDED |

---

## Phase 4 Gate — RESOLVE Fixes Applied (v1.2)

| Finding | Fix Applied In | Status |
|---|---|---|
| R-01 — Incremental cold-start guard | Task 2.4 CC prompt (cold-start note), Task 5.2 CC prompt (hard exit) + TC-cold-start | ✅ CLOSED |
| R-02 — Mount parity verification | Task 1.2 verification command (mount parity probe) | ✅ CLOSED |
| R-03 — Silver Transaction Codes rerun idempotency | Task 5.3 CC prompt (idempotency check) + TC-5 (rerun) | ✅ CLOSED |
| R-04 — dbt not_null(_pipeline_run_id) build-time tests | Tasks 3.1, 3.2, 3.3, 3.4, 4.1, 4.2 CC prompts and schema.yml | ✅ CLOSED |

---

## Phase 4 Sign-Off Gate

| Check | Status |
|---|---|
| All RESOLVE findings applied — R-01, R-02, R-03, R-04 | ✅ PASS |
| Requirements traceability — 38 + 4 Phase 4 additions | ✅ PASS |
| Session overview table | ✅ PRESENT — 6 sessions, 23 tasks |
| Per-task: description, CC prompt, test cases, verification command | ✅ PRESENT all 23 tasks |
| Per-task invariant enforcement | ✅ PRESENT all 23 tasks |
| Per-task regression classification | ✅ PRESENT all 23 tasks |
| All 53 invariants traceable | ✅ PASS — traceability matrix unchanged |
| All 10 implementation guidance items embedded | ✅ PASS |
| EXECUTION_PLAN.md v1.2 — All Phase 4 RESOLVE fixes closed. Ready for Phase 5. |

**Engineer sign-off required before Phase 5 begins.**
