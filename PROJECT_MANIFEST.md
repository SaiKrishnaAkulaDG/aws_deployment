# PROJECT_MANIFEST.md — Credit Card Transactions Lake

## Methodology Version

METHODOLOGY_VERSION: PBVI v4.3 / BCE v1.7

---

## Core Documents

| File | Status | Session | Purpose |
|---|---|---|---|
| `docs/ARCHITECTURE.md` | PRESENT | S1 | System design decisions and component architecture |
| `docs/INVARIANTS.md` | PRESENT | S1 | 53 invariants across 11 groups; audit and constraints |
| `docs/EXECUTION_PLAN.md` | PRESENT | S1 | Task prompts, test cases, verification commands |
| `docs/PHASE4_GATE_RECORD.md` | PRESENT | S1 | Phase 4 resolution record and open question closures |
| `docs/Claude.md` | PENDING | S1 | Execution contract and hard invariants |

---

## Infrastructure Files

| File | Status | Session | Purpose |
|---|---|---|---|
| `README.md` | PRESENT | S1 | Project description and entry point commands |
| `PROJECT_MANIFEST.md` | PRESENT | S1 | This file — full project registry |
| `Dockerfile` | PENDING | S1 | Python 3.11, dbt-core 1.7.x, dbt-duckdb 1.7.x |
| `docker-compose.yml` | PENDING | S1 | Service definition, bind mounts, environment |
| `requirements.txt` | PENDING | S1 | Python package dependencies |
| `.gitignore` | PENDING | S1 | Runtime Parquet files, DuckDB catalog |

---

## Session Logs and Verification

| File | Status | Session |
|---|---|---|
| `sessions/S1_SESSION_LOG.md` | PENDING | S1 |
| `sessions/S1_VERIFICATION_RECORD.md` | PENDING | S1 |
| `sessions/S2_SESSION_LOG.md` | PENDING | S2 |
| `sessions/S2_VERIFICATION_RECORD.md` | PENDING | S2 |
| `sessions/S3_SESSION_LOG.md` | PENDING | S3 |
| `sessions/S3_VERIFICATION_RECORD.md` | PENDING | S3 |
| `sessions/S4_SESSION_LOG.md` | PENDING | S4 |
| `sessions/S4_VERIFICATION_RECORD.md` | PENDING | S4 |
| `sessions/S5_SESSION_LOG.md` | PENDING | S5 |
| `sessions/S5_VERIFICATION_RECORD.md` | PENDING | S5 |
| `sessions/S6_SESSION_LOG.md` | PENDING | S6 |
| `sessions/S6_VERIFICATION_RECORD.md` | PENDING | S6 |

---

## Pipeline Python Modules

| File | Status | Session | Purpose |
|---|---|---|---|
| `pipeline/run_logger.py` | PENDING | S2 | Run log management and UUIDv4 generation |
| `pipeline/bronze_loader.py` | PENDING | S2 | Bronze CSV ingestion with row count verification |
| `pipeline/control_manager.py` | PENDING | S2 | Watermark and control table management |
| `pipeline/pipeline_historical.py` | PENDING | S5 | Historical pipeline entry point (date-range loop) |
| `pipeline/pipeline_incremental.py` | PENDING | S5 | Incremental pipeline entry point (watermark + 1) |
| `pipeline/silver_promoter.py` | PENDING | S3 | Silver dbt invocation and atomic rename |
| `pipeline/gold_builder.py` | PENDING | S4 | Gold dbt invocation |

---

## dbt Project Files

| File | Status | Session | Purpose |
|---|---|---|---|
| `dbt/dbt_project.yml` | PENDING | S1 | dbt project configuration |
| `dbt/profiles.yml` | PENDING | S1 | dbt profile for DuckDB adapter |
| `dbt/models/silver/silver_transaction_codes.sql` | PENDING | S3 | Silver Transaction Codes model |
| `dbt/models/silver/silver_transaction_codes.yml` | PENDING | S3 | Transaction Codes schema and tests |
| `dbt/models/silver/silver_accounts.sql` | PENDING | S3 | Silver Accounts model (latest state per account_id) |
| `dbt/models/silver/silver_accounts.yml` | PENDING | S3 | Accounts schema and tests |
| `dbt/models/silver/silver_quarantine.sql` | PENDING | S3 | Silver Quarantine model |
| `dbt/models/silver/silver_quarantine.yml` | PENDING | S3 | Quarantine schema and tests |
| `dbt/models/silver/silver_transactions.sql` | PENDING | S3 | Silver Transactions model (deduplicated, validated) |
| `dbt/models/silver/silver_transactions.yml` | PENDING | S3 | Transactions schema and tests |
| `dbt/models/silver/schema.yml` | PENDING | S3 | Silver layer schema definitions |
| `dbt/models/gold/gold_daily_summary.sql` | PENDING | S4 | Gold daily transaction summary |
| `dbt/models/gold/gold_daily_summary.yml` | PENDING | S4 | Daily summary schema and tests |
| `dbt/models/gold/gold_weekly_account_summary.sql` | PENDING | S4 | Gold weekly account summary with closing balance |
| `dbt/models/gold/gold_weekly_account_summary.yml` | PENDING | S4 | Weekly summary schema and tests |
| `dbt/models/gold/schema.yml` | PENDING | S4 | Gold layer schema definitions |

---

## Source Data Files

| File | Status | Session | Purpose |
|---|---|---|---|
| `source/transaction_codes.csv` | PENDING | S1 | Reference table: code → debit_credit_indicator |
| `source/transactions_2024-01-01.csv` | PENDING | S1 | Daily transactions for 2024-01-01 |
| `source/transactions_2024-01-02.csv` | PENDING | S1 | Daily transactions for 2024-01-02 |
| `source/transactions_2024-01-03.csv` | PENDING | S1 | Daily transactions for 2024-01-03 |
| `source/transactions_2024-01-04.csv` | PENDING | S1 | Daily transactions for 2024-01-04 |
| `source/transactions_2024-01-05.csv` | PENDING | S1 | Daily transactions for 2024-01-05 |
| `source/transactions_2024-01-06.csv` | PENDING | S1 | Daily transactions for 2024-01-06 |
| `source/accounts_2024-01-01.csv` | PENDING | S1 | Daily accounts for 2024-01-01 |
| `source/accounts_2024-01-02.csv` | PENDING | S1 | Daily accounts for 2024-01-02 |
| `source/accounts_2024-01-03.csv` | PENDING | S1 | Daily accounts for 2024-01-03 |
| `source/accounts_2024-01-04.csv` | PENDING | S1 | Daily accounts for 2024-01-04 |
| `source/accounts_2024-01-05.csv` | PENDING | S1 | Daily accounts for 2024-01-05 |
| `source/accounts_2024-01-06.csv` | PENDING | S1 | Daily accounts for 2024-01-06 |

---

## Tools and Scripts

| File | Status | Session | Purpose |
|---|---|---|---|
| `tools/launch.sh` | PENDING | S1 | Session launch script |
| `tools/resume_session.sh` | PENDING | S1 | Resume interrupted session |
| `tools/resume_challenge.sh` | PENDING | S1 | Resume challenge mode |
| `tools/challenge.sh` | PENDING | S1 | Challenge mode verification |
| `tools/monitor.sh` | PENDING | S1 | Pipeline monitoring script |

---

## Non-Standard Registered Files

| File | Status | Purpose |
|---|---|---|
| `sessions/S1_execution_prompt.md` | PRESENT | S1 manual execution instructions |
| `sessions/S2_execution_prompt.md` | PRESENT | S2 manual execution instructions |
| `sessions/S3_execution_prompt.md` | PRESENT | S3 manual execution instructions |
| `sessions/S4_execution_prompt.md` | PRESENT | S4 manual execution instructions |
| `sessions/S5_execution_prompt.md` | PRESENT | S5 manual execution instructions |
| `sessions/S6_execution_prompt.md` | PRESENT | S6 manual execution instructions |

---

## Non-Standard Registered Directories

| Directory | Status | Purpose |
|---|---|---|
| `brief/` | PENDING | PBVI brief documentation |
| `docs/prompts/` | PENDING | Session prompt storage |
| `discovery/` | PENDING | Discovery and analysis artifacts |
| `discovery/components/` | PENDING | Component-level discovery |
| `verification/` | PENDING | Verification checklists and test suites |
| `enhancements/` | PENDING | Enhancement packages (ENH-NNN) |
| `source/` | PENDING | Read-only source CSV files |
| `pipeline/` | PENDING | Run log, control table, entry point scripts |
| `bronze/` | PENDING | Raw ingested data by date partition |
| `silver/` | PENDING | Transformed, validated data |
| `silver_temp/` | PENDING | Temporary Silver layer (atomic rename staging) |
| `gold/` | PENDING | Aggregated summary tables |
| `quarantine/` | PENDING | Rejected records with reasons |
| `dbt/` | PENDING | dbt project |

---

## Structural Exceptions

None declared.

---

## Notes

- All PENDING files will be created across Sessions S1–S6.
- PRESENT files are foundational planning artifacts placed in S1.
- All paths are relative to repo root.
- Source files in `source/` are read-only at runtime (INV-06).
- All Parquet files (.parquet) in pipeline/, bronze/, silver/, gold/, quarantine/ are runtime outputs — not committed.
- DuckDB catalog file `pipeline/dbt_catalog.duckdb` is a runtime artifact — not committed.
