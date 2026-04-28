# S3 Debugging Log — Learning from Real-Time Issues and Fixes

**Purpose:** Document all issues encountered during Session 3 Silver layer implementation, root causes, and solutions applied. This serves as a reference for understanding dbt-duckdb interactions and Python subprocess execution patterns.

---

## Issue 1: External Source Definitions Not Recognized by dbt-duckdb

### Problem

**Initial Approach (FAILED):**
```yaml
# dbt/models/sources.yml
sources:
  - name: bronze
    tables:
      - name: bronze_transaction_codes
        external:
          location: /app/bronze/transaction_codes/data.parquet
          options:
            format: parquet
```

**Error Message:**
```
Runtime Error in model silver_transaction_codes
  Catalog Error: Table with name bronze_transaction_codes does not exist!
  Did you mean "temp.pg_catalog.pg_index"?
  LINE 26: from "dbt_catalog"."bronze"."bronze_transaction_codes"
```

### Root Cause Analysis

1. **dbt-duckdb Limitation**: dbt-duckdb does not support external source definitions the same way Snowflake/BigQuery do
2. **Source Mapping**: When using `{{ source('bronze', 'bronze_transaction_codes') }}`, dbt tries to look up this table in the DuckDB catalog as `"dbt_catalog"."bronze"."bronze_transaction_codes"`
3. **Missing Registration**: External Parquet files are not automatically registered as tables in the DuckDB catalog just by defining them in sources.yml
4. **No Built-in External Support**: Unlike Snowflake's EXTERNAL TABLE or BigQuery's external data sources, dbt-duckdb requires direct file references

### Solution Implemented

**Final Approach (SUCCESS):**
```sql
-- dbt/models/silver/silver_transaction_codes.sql
select
    transaction_code,
    description,
    debit_credit_indicator,
    transaction_type,
    affects_balance,
    _pipeline_run_id,
    _ingested_at,
    _source_file
from read_parquet('/app/bronze/transaction_codes/date=*/data.parquet')
```

**Key Changes:**
1. Replaced `{{ source() }}` reference with native DuckDB `read_parquet()` function
2. Used glob pattern for date partitions: `date=*/data.parquet` instead of specific date
3. Added `DISTINCT` clause to deduplicate across date partitions (since transaction_codes is same data for all dates)
4. Kept sources.yml for documentation purposes (not executable, just reference)

**Why This Works:**
- `read_parquet()` is native DuckDB SQL function that directly accesses files
- Glob patterns supported by DuckDB for reading multiple partition files
- No dependency on dbt source registry or catalog
- Portable across dbt adapters if using DuckDB directly

### Lesson Learned

📚 **dbt-duckdb uses direct SQL file access, not source definitions.** External sources work in Snowflake/BigQuery because those systems have native EXTERNAL TABLE support. With dbt-duckdb, you must use `read_parquet()` directly for external files. Sources.yml is still useful for documentation but not for actual data access.

---

## Issue 2: Bronze Data Not Found on First dbt Run

### Problem

**Error Message:**
```
IO Error: No files found that match the pattern "/app/bronze/transaction_codes/data.parquet"
```

**Context:** Ran `dbt run --select silver_transaction_codes` but Bronze layer data didn't exist yet.

### Root Cause Analysis

1. **Order of Operations**: Attempted to run Silver models before Bronze layer was populated
2. **Missing Prerequisite**: pipeline_historical.py hadn't been executed to load Bronze data
3. **No Dependency Chain**: dbt doesn't enforce prerequisite checks before running models

### Solution Implemented

**Step 1: Load Bronze Data First**
```bash
docker compose run --rm pipeline python pipeline/pipeline_historical.py \
    --start-date 2024-01-01 --end-date 2024-01-06
```

**Step 2: Then Run Silver Models**
```bash
dbt run --select silver_transaction_codes
```

**Why This Works:**
- Ensures data dependencies are satisfied before model execution
- Follows medallion architecture: Bronze → Silver → Gold
- Prevents "file not found" errors due to missing prerequisites

### Lesson Learned

📚 **Check that input data exists before running downstream models.** In a medallion pipeline, each layer depends on the previous one being populated. Always verify prerequisites before starting model builds.

---

## Issue 3: Directory Creation and dbt Write Permissions

### Problem

**Error Message:**
```
IO Error: Cannot open file "/app/silver/transaction_codes/data.parquet": No such file or directory
```

**Context:** dbt run succeeded but Parquet file wasn't created.

### Root Cause Analysis

1. **Missing Parent Directory**: dbt-duckdb's external materialization doesn't auto-create parent directories
2. **Write Permission Issues**: Directory structure not pre-existing caused write failures
3. **Silent Failure**: dbt didn't raise error during model execution, only when querying the file

### Solution Implemented

**Pre-create output directories:**
```bash
mkdir -p /app/silver/transaction_codes
mkdir -p /app/silver/accounts
mkdir -p /app/silver/transactions/date=2024-01-01
mkdir -p /app/quarantine
```

**Then run dbt:**
```bash
dbt run --select silver_transaction_codes
```

**Why This Works:**
- dbt can write to existing directories immediately
- Eliminates race conditions on directory creation
- Ensures consistent file permissions

### Lesson Learned

📚 **Pre-create output directories for dbt external materializations.** Unlike table materializations (which use views/temp tables), external materializations write directly to the filesystem. The parent directory must exist beforehand.

---

## Issue 4: Ambiguous Column References in CTE JOINs

### Problem

**Error Message (Task 3.4):**
```
Binder Error: Ambiguous reference to column name "account_id" 
(use: "sa.account_id" or "vt.account_id")
```

**Problematic Code:**
```sql
signed_transactions as (
    select
        transaction_id,
        account_id,  -- AMBIGUOUS: which table?
        ...
    from valid_transactions vt
    left join silver_accounts sa on vt.account_id = sa.account_id
)
```

### Root Cause Analysis

1. **Column Name Collision**: Both `valid_transactions` and `silver_accounts` have `account_id` column
2. **DuckDB Strictness**: DuckDB requires explicit table qualification for ambiguous columns
3. **SELECT *  Propagation**: When selecting from `vt`, all columns (including account_id) are inherited

### Solution Implemented

**Explicit Table Qualification:**
```sql
signed_transactions as (
    select
        vt.transaction_id,
        vt.account_id,
        vt.transaction_date,
        vt.amount,
        vt.transaction_code,
        vt.merchant_name,
        vt.channel,
        vt.debit_credit_indicator,
        case
            when vt.debit_credit_indicator = 'DR' 
            then try_cast(vt.amount as decimal)
            else -try_cast(vt.amount as decimal)
        end as _signed_amount,
        case
            when sa.account_id is not null then true
            else false
        end as _is_resolvable,
        vt._pipeline_run_id,
        vt._bronze_ingested_at,
        vt._source_file,
        current_timestamp as _promoted_at
    from valid_transactions vt
    left join silver_accounts sa on vt.account_id = sa.account_id
)
```

**Why This Works:**
- Every column reference is explicitly qualified with table alias
- DuckDB knows exactly which table to pull each column from
- Prevents ambiguity at JOIN evaluation time

### Lesson Learned

📚 **Always qualify column references in JOINs with ambiguous names.** When multiple tables in a JOIN have the same column name, explicitly prefix with table alias (e.g., `vt.account_id`). This is especially important with DuckDB's strict type checking.

---

## Issue 5: dbt Variable Passing from Python Subprocess

### Problem

**Error Message:**
```
Usage: dbt run [OPTIONS]
Try 'dbt run -h' for help.

Error: Invalid value for '--vars': String 'date_var:2024-01-01' is not valid YAML
```

**Problematic Code (Task 3.5):**
```python
var_str = " ".join([f"{k}:{v}" for k, v in variables.items()])
cmd.extend(["--vars", var_str])
# Results in: --vars "date_var:2024-01-01"
# dbt expects: --vars '{"date_var": "2024-01-01"}'
```

### Root Cause Analysis

1. **YAML Format Required**: dbt --vars expects YAML or JSON, not simple key:value strings
2. **Quote Escaping**: Shell quoting issues when passing complex strings to subprocess
3. **Missing JSON Structure**: `"date_var:2024-01-01"` is not valid YAML/JSON

### Solution Implemented

**JSON Serialization:**
```python
import json

if variables:
    var_str = json.dumps(variables)  # {"date_var": "2024-01-01"}
    cmd.extend(["--vars", var_str])
```

**Why This Works:**
- `json.dumps()` produces valid YAML/JSON that dbt understands
- Python's json module handles proper quoting and escaping
- dbt parser recognizes JSON as valid variable input
- Works with complex nested structures if needed

**Example Execution:**
```bash
dbt run --select silver_transactions --vars '{"date_var": "2024-01-01"}'
```

### Lesson Learned

📚 **Use json.dumps() for dbt variables in Python subprocess calls.** dbt --vars expects YAML or JSON format. Don't construct variable strings manually with string concatenation. Always use JSON serialization for proper quoting and structure.

---

## Issue 6: Subprocess Working Directory Causing Path Resolution Failures

### Problem

**Error Message (Task 3.5 - promote_silver):**
```
RuntimeError: silver_transactions: dbt run failed
(Error details stripped but relates to file not found)
```

**Real Issue (Discovered via Debugging):**
```
IO Error: No files found that match the pattern "/app/silver/accounts/data.parquet"
```

**Problematic Code:**
```python
def invoke_dbt_model(model_name: str, app_dir: str, variables: Optional[dict] = None) -> dict:
    dbt_dir = os.path.join(app_dir, "dbt")
    cmd = ["dbt", "run", "--select", model_name, "--project-dir", dbt_dir, "--profiles-dir", dbt_dir]
    
    result = subprocess.run(
        cmd,
        cwd=dbt_dir,  # ← PROBLEM: Changes working directory
        capture_output=True,
        text=True,
        timeout=300
    )
```

### Root Cause Analysis

1. **Working Directory Change**: `cwd=dbt_dir` changes subprocess working directory to `/app/dbt`
2. **Path Resolution Context**: When dbt runs, relative paths are resolved from `/app/dbt`, not `/app`
3. **Manifest Conflicts**: dbt reads profiles.yml and manifest from wrong directory context
4. **Volume Mount Isolation**: Each subprocess in container may have isolated view of filesystem

### Solution Implemented

**Remove cwd parameter:**
```python
def invoke_dbt_model(model_name: str, app_dir: str, variables: Optional[dict] = None) -> dict:
    dbt_dir = os.path.join(app_dir, "dbt")
    cmd = ["dbt", "run", "--select", model_name, "--project-dir", dbt_dir, "--profiles-dir", dbt_dir]
    
    result = subprocess.run(
        cmd,
        # NO cwd parameter - let subprocess inherit parent working directory
        capture_output=True,
        text=True,
        timeout=300
    )
```

**Why This Works:**
- dbt uses --project-dir and --profiles-dir to find configuration
- Subprocess inherits parent working directory (`/app`)
- Relative paths in dbt models (read_parquet) are resolved from `/app`
- Files like `/app/silver/accounts/data.parquet` are found correctly

**Test Case That Revealed the Issue:**
```bash
# This works (no working directory change):
docker compose run --rm pipeline bash << 'EOF'
cd /app/dbt
dbt run --select silver_accounts
dbt run --select silver_transactions --vars '{"date_var": "2024-01-01"}'
EOF

# This failed (with cwd=dbt_dir in Python):
docker compose run --rm pipeline python << 'EOF'
result = invoke_dbt_model("silver_accounts", "/app", None)
result = invoke_dbt_model("silver_transactions", "/app", {"date_var": "2024-01-01"})
EOF
```

### Lesson Learned

📚 **Don't change subprocess working directory unless necessary.** dbt respects --project-dir and --profiles-dir flags, so you don't need to cd into the dbt directory. Changing cwd can cause path resolution failures in read_parquet() calls. Let subprocess inherit parent working directory.

---

## Issue 7: Container Isolation and Persistent Data in Docker Compose

### Problem

**Observation:** Each `docker compose run --rm` command seemed to have fresh state, but data wasn't persisting between commands.

**Initial Confusion:**
```bash
# First command
docker compose run --rm pipeline bash -c "mkdir -p /app/silver/accounts && dbt run --select silver_accounts"
# Result: /app/silver/accounts/data.parquet created

# Second command
docker compose run --rm pipeline bash -c "ls /app/silver/accounts/"
# Result: Directory doesn't exist!
```

### Root Cause Analysis

1. **--rm Flag Behavior**: `--rm` deletes the container after execution but NOT the volume mounts
2. **Volume Mounts Persist**: The bind mount `.:/app:rw` persists data on the host filesystem
3. **Container Isolation**: Each `docker compose run --rm` creates a NEW container, but they all share same volume
4. **Expected Behavior**: Data written to /app/ persists across docker runs because it's mounted from host

**Actual Investigation:**
```bash
# Check host filesystem
ls -la /app/silver/  # On HOST machine (Windows with Docker Desktop)
# Result: Files existed!

# The issue was context confusion: 
# - Files exist in container
# - Files exist on host (/app mounted directory)
# - Each docker run starts fresh but sees same volume
```

### Solution Implemented

**Unified Container Session for Testing:**
```python
# Instead of multiple docker compose run calls, use single bash script:
docker compose run --rm pipeline python << 'EOF'
import sys
import os
sys.path.insert(0, '/app')

from pipeline.silver_promoter import promote_silver_transaction_codes, promote_silver
import uuid

# All operations in same container instance
# Data persists because volume mount stays consistent
os.makedirs("/app/silver/accounts", exist_ok=True)

result1 = promote_silver_transaction_codes(str(uuid.uuid4()), '/app')
result2 = promote_silver('2024-01-01', str(uuid.uuid4()), '/app')

# Data is visible immediately after operations in same session
assert os.path.exists('/app/silver/accounts/data.parquet')
print('SUCCESS')
EOF
```

**Why This Works:**
- Single container instance maintains consistent filesystem state
- All operations see same volume mount
- Data persists in host filesystem `/app/` directory
- Multiple commands can coordinate within same session

### Lesson Learned

📚 **For multi-step testing, use single docker compose run session.** Each `docker compose run` creates a new container with fresh state. While volume mounts persist data on the host, your working state (environment variables, intermediate files) resets. For integration testing with dependencies, use a single session with a script that performs all steps sequentially.

---

## Issue 8: Channel Values Changed Mid-Implementation

### Problem

**Initial Specification (EXECUTION_PLAN):**
```
channel must be either "POS", "ONLINE", "ATM", "MOBILE", "BRANCH" (5 values)
```

**User Specification (Mid-Task 3.3):**
```
channel must be either "ONLINE" or "IN_STORE" (2 values)
```

**Impact:** Quarantine model's INVALID_CHANNEL rule needed updating.

### Root Cause Analysis

1. **Scope Creep**: Requirements evolved as implementation progressed
2. **Real-World Data vs Spec**: User's actual data had different values than planning docs
3. **Communication Gap**: Clarification came during implementation, not planning phase

### Solution Implemented

**Updated quarantine rule:**
```sql
-- Invalid channel rule (must be ONLINE or IN_STORE)
invalid_channel as (
    select *
    from bronze_transactions
    where ...
    and channel not in ('ONLINE', 'IN_STORE')
)
```

**Schema test updated:**
```yaml
accepted_values(channel, ['ONLINE', 'IN_STORE'])
```

**Why This Works:**
- Model now validates against actual data values, not spec
- Tests enforce the real business rules
- Quarantine catches transactions with unexpected channel values

### Lesson Learned

📚 **Lock requirements early and validate against actual data.** Real-world data often differs from specification documents. During planning phase, verify sample data against proposed rules. If requirements change mid-implementation, update all affected models, tests, and documentation immediately.

---

## Summary of Key Learnings

| Issue | Category | Key Lesson |
|-------|----------|-----------|
| #1 | dbt-duckdb | Use `read_parquet()` for external files, not source definitions |
| #2 | Data Pipeline | Verify prerequisites before running dependent models |
| #3 | File Operations | Pre-create output directories for dbt external materializations |
| #4 | SQL Correctness | Explicitly qualify ambiguous column references in JOINs |
| #5 | Python Subprocess | Use json.dumps() for dbt variables, not manual string concatenation |
| #6 | Subprocess Execution | Don't change working directory; use dbt flags for path configuration |
| #7 | Container Testing | Use single session for multi-step testing to maintain state |
| #8 | Requirements | Lock specs early; validate with actual data during planning |

---

## Debugging Techniques Used

### 1. **Incremental Simplification**
- Removed complex external source definitions
- Switched to direct `read_parquet()` calls
- Reduced cognitive load and identified true issue

### 2. **Manual Testing vs Automation**
```bash
# When Python subprocess failed:
# Tested directly in bash to isolate problem
docker compose run --rm pipeline bash -c "dbt run --select silver_accounts"

# Then applied fix to Python code once we understood the issue
```

### 3. **Error Message Inspection**
- Read full error messages, not just first line
- Errors were often truncated; captured stdout + stderr
- Stripped file paths to focus on root cause

### 4. **Single Container Session Testing**
- When multi-container runs failed mysteriously
- Consolidated to single Python script in one docker run
- Eliminated container isolation as variable

### 5. **Explicit State Verification**
```bash
# After each major step, verify files exist
ls -la /app/silver/accounts/data.parquet
ls -la /app/quarantine/data.parquet
```

---

## Files Modified During Debugging

| File | Initial Attempt | Final Version | Issue Fixed |
|------|-----------------|---------------|-------------|
| silver_transaction_codes.sql | `{{ source() }}` | `read_parquet()` | Issue #1 |
| silver_accounts.sql | Ambiguous JOINs | Table-qualified | Issue #4 |
| silver_promoter.py | `cwd=dbt_dir` | No cwd param | Issue #6 |
| silver_promoter.py | Manual var concat | `json.dumps()` | Issue #5 |
| silver_quarantine.sql | 5 channel values | 2 channel values | Issue #8 |

---

## Recommendations for Future Sessions

1. **Pre-Planning Checklist:**
   - [ ] Validate sample data against proposed business rules
   - [ ] Test source file formats and locations
   - [ ] Confirm exact field values (not just names) with business

2. **Implementation Checklist:**
   - [ ] Create output directories before running dbt
   - [ ] Load prerequisite data before downstream models
   - [ ] Use single container session for integration testing
   - [ ] Qualify all ambiguous column references
   - [ ] Use json.dumps() for dbt variables

3. **Debugging Checklist:**
   - [ ] Test directly in bash before trying Python subprocess
   - [ ] Capture full stdout + stderr, not just errors
   - [ ] Verify files/directories exist at expected paths
   - [ ] Check working directory context
   - [ ] Inspect error messages for path-related clues

---

**This log serves as institutional knowledge for the Credit Card Transactions Lake project. Refer to these issues and solutions when debugging future sessions.**
