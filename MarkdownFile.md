**Requirements Brief**

**Credit Card Financial Transactions Lake**

Version 1.0 · Classification: Training Demo System · PBVI Data Engineering Training Vehicle

# 1\. The Problem

A financial services client processes credit card transactions across multiple channels daily. Data analysts and risk teams need reliable, queryable aggregations of transaction activity per account — but currently access raw extract files directly. This bypasses quality control, produces inconsistent results when analysts work from different file versions, and provides no audit trail of how raw data became the numbers being acted on.

The client wants a structured data lake implementing the Medallion architecture (Bronze → Silver → Gold) that ingests daily extract files, enforces defined quality rules at each layer boundary, and produces Gold-layer aggregations that analysts can query with confidence via DuckDB. The pipeline must be re-runnable without producing duplicates or incorrect aggregations.

This system ingests and surfaces pre-existing data. It does not compute risk, make credit decisions, or modify source system records.

# 2\. Source Data Model

The source system produces extract files in CSV format. There are three source entities. File naming conventions and directory placement are fixed — see the companion scaffold repository.

## 2.1 Transactions

One CSV file per calendar day containing all transactions processed on that date. Filename: transactions\_YYYY-MM-DD.csv. This is an append-only fact entity — transactions are never updated or deleted in the source system.

| Field | Type | Nullable | Description |
| --- | --- | --- | --- |
| transaction_id | STRING | No | Unique identifier for the transaction |
| account_id | STRING | No | Foreign key to Accounts |
| transaction_date | DATE | No | Date the transaction was processed (YYYY-MM-DD) |
| amount | DECIMAL | No | Transaction value — always positive in source. Sign is assigned in Silver using transaction_codes.debit_credit_indicator |
| transaction_code | STRING | No | Foreign key to Transaction Codes dimension |
| merchant_name | STRING | Yes | Merchant name for PURCHASE transactions. Null for non-purchase types |
| channel | STRING | No | ONLINE or IN_STORE |

**_Note:_** _Amount sign convention: source amounts are always positive. The pipeline assigns the correct sign in Silver by joining to Transaction Codes and applying debit\_credit\_indicator. The pipeline never applies sign logic based on its own rules — the Transaction Codes dimension is the authoritative source for sign assignment._

## 2.2 Transaction Codes

A single reference file containing all valid transaction codes. Filename: transaction\_codes.csv. This file is loaded once as part of the historical pipeline initialisation. It does not change during the exercise.

| Field | Type | Nullable | Description |
| --- | --- | --- | --- |
| transaction_code | STRING | No | Primary key — unique code identifying the transaction type |
| transaction_type | STRING | No | Category: PURCHASE, PAYMENT, FEE, INTEREST, REFUND |
| description | STRING | No | Human-readable label for this code |
| debit_credit_indicator | STRING | No | DR increases balance (charges, fees, interest). CR decreases balance (payments, refunds) |
| affects_balance | BOOLEAN | No | Whether this transaction type changes the outstanding account balance |

**_Note:_** _In production, transaction code changes are a governed process with significant business process implications — new codes require coordination across risk, finance, and operations teams and do not arrive silently in a pipeline. This exercise treats the dimension as static to keep scope manageable._

## 2.3 Accounts

A daily delta file containing new accounts and accounts whose attributes changed since the previous extract. Filename: accounts\_YYYY-MM-DD.csv. The file contains only new or changed records — unchanged accounts are not included.

| Field | Type | Nullable | Description |
| --- | --- | --- | --- |
| account_id | STRING | No | Primary key — unique account identifier |
| open_date | DATE | No | Date the account was opened |
| credit_limit | DECIMAL | No | Approved credit limit in GBP |
| current_balance | DECIMAL | No | Outstanding balance as of extract date |
| billing_cycle_start | INTEGER | No | Day of month the billing cycle starts (1–28) |
| billing_cycle_end | INTEGER | No | Day of month the billing cycle ends (1–28) |
| account_status | STRING | No | ACTIVE, SUSPENDED, or CLOSED |

**_Note:_** _Silver maintains the latest record per account\_id — this is a deliberate simplification. A production implementation would use SCD Type 2 to preserve the full history of credit limit changes, status transitions, and balance snapshots. Teams should be aware of what this simplification costs: there is no way to reconstruct what an account's credit limit was on a historical date._

# 3\. Pipeline Architecture

The system implements two distinct pipelines. They share the same layer structure and transformation logic but have different invocation interfaces and state management behaviour.

## 3.1 Historical Load Pipeline

Runs once to initialise the data lake from historical extract files. Accepts start\_date and end\_date as parameters and processes all files in that date range in date order: transaction\_codes.csv first, then daily accounts and transactions files for each date in the range.

*   Processes Bronze → Silver → Gold in sequence for the full date range
*   Transaction codes are loaded to Silver reference layer before any transaction processing begins
*   Initialises the pipeline control table with the watermark set to end\_date on successful completion
*   Re-running the historical pipeline against a date range already present in Bronze must not produce duplicate records — idempotency is required

**_Note:_** _Backfill capability — the ability to reprocess specific historical dates to correct errors — is explicitly out of scope for this exercise. It is documented here as a known production pattern that would require a dedicated backfill pipeline with watermark guard logic to prevent future-date processing._

## 3.2 Incremental Load Pipeline

Runs on a scheduled basis (daily in production) to process the next day's extract files. Uses a control table to track the watermark — the last successfully processed date.

*   Reads the current watermark from the pipeline control table
*   Determines the next date to process as watermark + 1 day
*   Processes Bronze → Silver → Gold for that date only
*   Advances the watermark only after all three layers complete successfully for that date
*   Is idempotent — running it twice when no new file is available must not corrupt existing data

# 4\. Layer Specifications

## 4.1 Bronze Layer

Bronze is the immutable raw landing zone. It stores exactly what arrived in the source file — no transformations, no filtering, no enrichment beyond the pipeline audit columns listed below.

*   Each source file lands as a Parquet partition: bronze/{entity}/date=YYYY-MM-DD/data.parquet
*   Transaction codes land at: bronze/transaction\_codes/data.parquet (not date-partitioned — single reference file)
*   Source records are written exactly as received — malformed records, nulls, and duplicates are preserved
*   Bronze partitions are never overwritten or deleted after initial write
*   Loading the same source file twice must not create duplicate records in Bronze

**Bronze audit columns** (added by the pipeline — not present in source files):

| Column | Type | Description |
| --- | --- | --- |
| _source_file | STRING | Originating CSV filename |
| _ingested_at | TIMESTAMP | When the pipeline wrote this record to Bronze |
| _pipeline_run_id | STRING | Unique identifier of the pipeline run that loaded this record |

## 4.2 Silver Layer

Silver contains clean, validated, and conformed records promoted from Bronze. It is the authoritative data layer — Gold is computed exclusively from Silver.

### 4.2.1 Silver — Transactions

Records promoted from Bronze transactions after passing all quality checks. Sign is applied using Transaction Codes debit\_credit\_indicator. account\_id is validated against Silver Accounts — records referencing unknown accounts are flagged but not quarantined.

*   Partitioned by Bronze source date: silver/transactions/date=YYYY-MM-DD/data.parquet
*   Deduplication is enforced across all partitions — a transaction\_id that already exists in any Silver partition is rejected to quarantine
*   Re-running Silver promotion for a date already promoted must not duplicate records

**Silver Transactions audit columns:**

| Column | Type | Description |
| --- | --- | --- |
| _source_file | STRING | Carried forward from Bronze |
| _bronze_ingested_at | TIMESTAMP | Carried forward from Bronze |
| _pipeline_run_id | STRING | Pipeline run that promoted this record |
| _promoted_at | TIMESTAMP | When this record was promoted to Silver |
| _is_resolvable | BOOLEAN | False if account_id not found in Silver Accounts at promotion time. Excluded from Gold aggregations until resolved via backfill (out of scope) |
| _signed_amount | DECIMAL | Amount with sign applied from transaction_codes.debit_credit_indicator. DR = positive, CR = negative |

### 4.2.2 Silver — Accounts

Latest record per account\_id. Delta records from Bronze are upserted — existing records are replaced if a newer version arrives. No history is retained.

*   Stored as a single non-partitioned file: silver/accounts/data.parquet
*   Upsert key: account\_id
*   Re-running accounts promotion for a date already processed must produce identical output

**Silver Accounts audit columns:**

| Column | Type | Description |
| --- | --- | --- |
| _source_file | STRING | Carried forward from Bronze |
| _bronze_ingested_at | TIMESTAMP | Carried forward from Bronze |
| _pipeline_run_id | STRING | Pipeline run that last upserted this record |
| _record_valid_from | TIMESTAMP | When this version of the account record became current in Silver |

### 4.2.3 Silver — Transaction Codes

Loaded once from Bronze during historical pipeline initialisation. Stored as a single reference file: silver/transaction\_codes/data.parquet. Not updated during incremental runs.

| Column | Type | Description |
| --- | --- | --- |
| _source_file | STRING | Carried forward from Bronze |
| _bronze_ingested_at | TIMESTAMP | Carried forward from Bronze |
| _pipeline_run_id | STRING | Pipeline run that loaded this reference data |

### 4.2.4 Silver — Quarantine

Records rejected during Silver promotion are written to quarantine rather than silently dropped. Quarantine is the audit trail for data quality failures.

*   Partitioned by Bronze source date: silver/quarantine/date=YYYY-MM-DD/rejected.parquet
*   Contains the original source record plus rejection audit columns
*   Records in quarantine are never promoted to Silver without a backfill (out of scope)

**Quarantine audit columns:**

| Column | Type | Description |
| --- | --- | --- |
| _source_file | STRING | Originating CSV filename |
| _pipeline_run_id | STRING | Pipeline run that rejected this record |
| _rejected_at | TIMESTAMP | When this record was rejected |
| _rejection_reason | STRING | Rejection reason code — see Section 5 |

## 4.3 Gold Layer

Gold contains analyst-facing aggregations computed exclusively from Silver. Gold is never computed from Bronze directly.

### 4.3.1 Gold — Daily Transaction Summary

One record per calendar day (by transaction\_date). Stored at: gold/daily\_summary/data.parquet.

| Column | Type | Description |
| --- | --- | --- |
| transaction_date | DATE | Calendar date of transactions |
| total_transactions | INTEGER | Count of Silver transactions with _is_resolvable = true |
| total_signed_amount | DECIMAL | Sum of _signed_amount from Silver transactions |
| transactions_by_type | STRUCT | Count and sum of _signed_amount per transaction_type |
| online_transactions | INTEGER | Count of ONLINE channel transactions |
| instore_transactions | INTEGER | Count of IN_STORE channel transactions |
| _computed_at | TIMESTAMP | When this record was last computed |
| _pipeline_run_id | STRING | Pipeline run that produced this record |
| _source_period_start | DATE | Earliest transaction_date in source Silver records |
| _source_period_end | DATE | Latest transaction_date in source Silver records |

### 4.3.2 Gold — Weekly Account Transaction Aggregates

One record per account per calendar week (Monday to Sunday, using transaction\_date). Only accounts with at least one resolvable transaction in the week are included. Stored at: gold/weekly\_account\_summary/data.parquet.

| Column | Type | Description |
| --- | --- | --- |
| week_start_date | DATE | Monday of the calendar week (ISO week, Monday start) |
| week_end_date | DATE | Sunday of the calendar week |
| account_id | STRING | Account identifier |
| total_purchases | INTEGER | Count of PURCHASE type transactions |
| avg_purchase_amount | DECIMAL | Average _signed_amount for PURCHASE transactions |
| total_payments | DECIMAL | Sum of _signed_amount for PAYMENT transactions |
| total_fees | DECIMAL | Sum of _signed_amount for FEE transactions |
| total_interest | DECIMAL | Sum of _signed_amount for INTEREST transactions |
| closing_balance | DECIMAL | current_balance from Silver Accounts as of week_end_date (or most recent available) |
| _computed_at | TIMESTAMP | When this record was last computed |
| _pipeline_run_id | STRING | Pipeline run that produced this record |

# 5\. Quality Rules and Rejection Reason Codes

Records that fail Silver promotion are written to quarantine with a \_rejection\_reason code. The following codes are pre-defined and exhaustive for this exercise — no additional codes are required.

## 5.1 Transaction Rejection Rules

| Code | Condition | Quarantine or Flag |
| --- | --- | --- |
| NULL_REQUIRED_FIELD | transaction_id, account_id, transaction_date, amount, transaction_code, or channel is null or empty | Quarantine |
| INVALID_AMOUNT | amount is zero, negative, or non-numeric | Quarantine |
| DUPLICATE_TRANSACTION_ID | transaction_id already exists in any Silver transactions partition | Quarantine |
| INVALID_TRANSACTION_CODE | transaction_code not found in Silver transaction_codes reference | Quarantine |
| INVALID_CHANNEL | channel value is not ONLINE or IN_STORE | Quarantine |
| UNRESOLVABLE_ACCOUNT_ID | account_id not found in Silver Accounts at promotion time | Flag only — record enters Silver with _is_resolvable = false. Excluded from Gold. |

## 5.2 Account Rejection Rules

| Code | Condition | Quarantine or Flag |
| --- | --- | --- |
| NULL_REQUIRED_FIELD | account_id, open_date, credit_limit, current_balance, billing_cycle_start, billing_cycle_end, or account_status is null or empty | Quarantine |
| INVALID_ACCOUNT_STATUS | account_status value is not ACTIVE, SUSPENDED, or CLOSED | Quarantine |

**_Note:_** _UNRESOLVABLE\_ACCOUNT\_ID is the only rejection condition that produces a Silver record rather than a quarantine record. This reflects a deliberate design decision: a transaction with an unknown account may be a timing issue (account delta not yet received) rather than a genuine data error. Correcting unresolvable records requires a backfill pipeline, which is out of scope for this exercise._

# 6\. Pipeline Control and Run Log

## 6.1 Pipeline Control Table

A single Parquet file that tracks the watermark for the incremental pipeline. Stored at: pipeline/control.parquet.

| Column | Type | Description |
| --- | --- | --- |
| last_processed_date | DATE | The most recent date for which all three layers completed successfully |
| updated_at | TIMESTAMP | When the watermark was last advanced |
| updated_by_run_id | STRING | The pipeline run that last advanced the watermark |

**_Note:_** _The watermark advances only after Bronze, Silver, and Gold all complete successfully for a given date. A pipeline failure after Bronze but before Silver completes must not advance the watermark — the date must be reprocessable on next run._

## 6.2 Pipeline Run Log

A Parquet file recording execution metadata at model level — one row per dbt model (or Bronze loader) per pipeline invocation. Stored at: pipeline/run\_log.parquet. New rows are appended on each run — the file is never overwritten.

| Column | Type | Description |
| --- | --- | --- |
| run_id | STRING | Unique identifier for the pipeline invocation — shared across all model rows from the same run |
| pipeline_type | STRING | HISTORICAL or INCREMENTAL |
| model_name | STRING | Name of the dbt model or Bronze loader (e.g. bronze_transactions, silver_transactions, gold_daily_summary) |
| layer | STRING | BRONZE, SILVER, or GOLD |
| started_at | TIMESTAMP | When this model execution started |
| completed_at | TIMESTAMP | When this model execution completed |
| status | STRING | SUCCESS, FAILED, or SKIPPED |
| records_processed | INTEGER | Records read by this model |
| records_written | INTEGER | Records written to output |
| records_rejected | INTEGER | Records written to quarantine (Silver models only — null otherwise) |
| error_message | STRING | Null on success. Error detail on failure — must not include file paths, credentials, or internal system detail |

**_Note:_** _run\_id is the connective tissue between the run log and the audit columns in every layer. Given a suspicious Gold aggregate, an analyst can trace: which run\_id computed it, what that run's Silver record counts were, and which Bronze records fed that Silver promotion._

# 7\. Stack (Fixed)

| Concern | Fixed Choice |
| --- | --- |
| Containerisation | Docker Compose — all services run locally, single-command startup |
| Transformation tool | dbt-core 1.7.x with dbt-duckdb 1.7.x adapter |
| Query engine | DuckDB — embedded, no separate server process |
| Storage format | Parquet files on local filesystem (bind-mounted into container) |
| Source data | Static CSV files in source/ directory — 7 daily transaction files, 7 daily account delta files, 1 transaction codes file |
| Pipeline runner | pipeline.py — Python 3.11 script that sequences Bronze loaders and dbt runs |
| Bronze ingestion | Python + DuckDB directly — dbt is not used for raw file loading |
| Silver and Gold models | dbt models exclusively — no ad-hoc SQL outside dbt |
| Run log and control table | Parquet files — no metadata database |
| dbt project structure | See companion scaffold repository |

**_Note:_** _The companion scaffold repository provides the dbt project skeleton (dbt\_project.yml, profiles.yml, models/ directory structure with empty stub files), all source CSV files with correct naming conventions and pre-seeded data including intentional quality issues, Docker Compose and Dockerfile stubs, and a pipeline.py stub with TODO markers. The scaffold fixes the directory layout and file naming so Phase 1 exploration focuses on pipeline design and invariant definition rather than project structure conventions._

# 8\. Constraints

*   The system must run end-to-end from docker compose up with no manual steps beyond providing a .env file
*   No external service calls — all data is local, no outbound HTTP
*   No database server — DuckDB operates as an embedded engine against Parquet files
*   Source files in source/ are read-only — the pipeline must never modify or delete CSV extracts
*   All layer outputs are Parquet files — no intermediate databases, no CSV outputs beyond source/
*   dbt models are the exclusive mechanism for Silver and Gold transformations
*   Bronze ingestion uses Python + DuckDB directly — dbt is not used for raw file loading
*   The pipeline must be re-runnable on the same input without manual cleanup — idempotency is required at every layer
*   The pipeline control table watermark must never advance past the last successfully completed full pipeline run

# 9\. Out of Scope

*   Backfill pipeline — reprocessing specific historical dates to correct errors. Documented as a known production pattern requiring a dedicated pipeline with watermark guard logic
*   SCD Type 2 for Accounts — full history of account attribute changes
*   Transaction code dimension changes — adding or modifying codes during pipeline operation
*   Streaming or near-realtime ingestion — this is a batch pipeline
*   A serving API layer — Gold outputs are queried directly via DuckDB CLI
*   Schema evolution — the CSV schema is fixed for this exercise
*   Data encryption at rest or in transit
*   Production deployment, monitoring, or alerting infrastructure
*   Resolution of \_is\_resolvable = false records — requires backfill (out of scope above)

# 10\. Verification Expectations

The following conditions constitute Phase 8 sign-off evidence. Each must be expressible as an exact DuckDB CLI command before Phase 3 is complete. Exact values depend on the seed data in the companion scaffold.

## 10.1 Bronze Completeness

*   Row count in bronze/transactions across all 7 date partitions equals total rows across all 7 source CSV files
*   Row count in bronze/accounts across all 7 date partitions equals total rows across all 7 accounts CSV files
*   bronze/transaction\_codes/data.parquet row count equals transaction\_codes.csv row count

## 10.2 Silver Quality

*   Total Silver transactions rows + total quarantine rows = total Bronze transactions rows across all partitions
*   No transaction\_id appears more than once across all Silver transactions partitions
*   Every Silver transactions record has a valid transaction\_code present in Silver transaction\_codes
*   No Silver transactions record has a null \_signed\_amount
*   Every quarantine record has a non-null \_rejection\_reason from the pre-defined code list

## 10.3 Gold Correctness

*   Gold daily\_summary contains exactly one row per distinct transaction\_date in Silver transactions where \_is\_resolvable = true
*   Gold weekly\_account\_summary total\_purchases count matches COUNT(\*) from Silver transactions filtered to PURCHASE type and \_is\_resolvable = true for the corresponding week and account
*   Gold total\_signed\_amount for each day matches SUM(\_signed\_amount) from Silver transactions for that transaction\_date where \_is\_resolvable = true

## 10.4 Idempotency

*   Running the full pipeline twice on the same input produces identical Bronze row counts, identical Silver row counts, identical quarantine row counts, and identical Gold output
*   Running the incremental pipeline when no new file is available produces no change to any layer

## 10.5 Audit Trail

*   Every Bronze record has a non-null \_pipeline\_run\_id
*   Every Silver record has a non-null \_pipeline\_run\_id
*   Every Gold record has a non-null \_pipeline\_run\_id
*   For any given \_pipeline\_run\_id appearing in Silver, a corresponding row exists in the run log with status = SUCCESS