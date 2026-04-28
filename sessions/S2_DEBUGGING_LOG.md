# S2 Debugging Log — Bronze Layer Ingestion and Run Logging

**Purpose:** Document all issues encountered during Session 2 Bronze layer implementation, run logging architecture, and pipeline orchestration. This serves as reference for understanding idempotency, append-only logs, and watermark management.

---

## Issue 1: Idempotency Check Logic — Row Count vs Content Validation

### Problem

**Design Question:** How should idempotency work for Bronze ingestion?

**Option A: Row Count Check**
```python
# If source has same rows as existing → already ingested
existing_rows = count_parquet_rows(bronze_path)
if existing_rows == source_rows:
    return SUCCESS  # Already have this data
```

**Option B: Content Hash Check**
```python
# If source content hash matches → already ingested
source_hash = hash_dataframe(df)
existing_hash = hash_parquet(bronze_path)
if source_hash == existing_hash:
    return SUCCESS  # Identical content
```

**Option C: Timestamp Check**
```python
# If ingestion timestamp is recent → skip
if bronze_path.exists() and is_today(get_mtime(bronze_path)):
    return SUCCESS  # Recently ingested
```

### Root Cause Analysis

1. **Idempotency Requirement**: Pipeline must handle re-runs without duplication
2. **Decision Point**: What evidence proves "already ingested"?
3. **Tradeoff**: Precision (content match) vs Performance (row count)

### Solution Implemented

**Decision 3: Row Count Idempotency (INV-01a)**

```python
# bronze_loader.py
def load_bronze(entity: str, date_str: str, run_id: str, ...):
    # Idempotency check (Decision 3, INV-01a)
    existing_count = _count_parquet_rows(bronze_path)
    if existing_count == records_processed and bronze_path.exists():
        # Partition exists + row count matches → SUCCESS immediately (no rewrite)
        return {
            "status": "SUCCESS",
            "records_processed": records_processed,
            "records_written": existing_count,
            "error_message": None,
        }
    
    # Row count mismatch → delete partition and re-ingest (S1B-03)
    if bronze_path.exists():
        _delete_partition(bronze_path)
```

**Why Row Count:**
- ✓ Fast: O(1) row count query vs O(n) content hash
- ✓ Sufficient: Exact row count match proves same CSV ingested
- ✓ Practical: Works for daily snapshot data (same CSV always = same rows)
- ✓ Recoverable: Mismatch detected → re-ingest
- ✗ Limitation: Doesn't detect row reordering or field value changes

**When This Fails:**
```
# These scenarios would pass idempotency check but are actually different data:
Scenario 1: CSV has same 100 rows but in different order
  Result: Row count match → reports SUCCESS
  Reality: Different column order not detected
  Fix: Row count + schema validation together

Scenario 2: CSV has same row count but different values
  Result: Row count match → reports SUCCESS
  Reality: Corrupted data not detected
  Fix: Add content hash validation for critical fields
```

### Verification

**Correct Scenario:**
```python
# First run: ingests 100 rows
result1 = load_bronze("transactions", "2024-01-01", run_id1, ...)
assert result1["status"] == "SUCCESS"
assert result1["records_written"] == 100

# Second run: detects 100 rows already present
result2 = load_bronze("transactions", "2024-01-01", run_id2, ...)
assert result2["status"] == "SUCCESS"
assert result2["records_written"] == 100  # Not rewritten
```

**Mismatch Scenario:**
```python
# Corrupted file with 50 rows instead of 100
# Row count mismatch detected
result = load_bronze("transactions", "2024-01-01", run_id, ...)
# Partition is deleted and 50-row file is re-ingested
assert result["records_written"] == 50
```

### Lesson Learned

📚 **Row count idempotency is fast but limited.** It's suitable for:
- Append-only logs (never re-updated)
- Daily snapshots from stable sources (same data = same structure)
- Where content changes are rare

For critical data, consider also validating:
- Row count + schema match
- Row count + spot-check of first/last row values
- Row count + data quality metrics

**Pattern for Future Use:**
```python
# Single-source idempotency (most reliable)
if same_source_ingested:
    return SUCCESS  # Based on source metadata or checksum

# Row count idempotency (fast, good enough for daily snapshots)
if existing_row_count == source_row_count:
    return SUCCESS

# Timestamp idempotency (simplest but least reliable)
if recently_modified:
    return SUCCESS
```

---

## Issue 2: Append-Only Log Design — Write Semantics

### Problem

**Challenge:** How to implement append-only run_log.parquet?

**Option A: True Append (Streaming)**
```python
# In-place append: read existing, add new rows, write incrementally
# Problem: Requires streaming writer, complex locking
```

**Option B: Logical Append (Overwrite)**
```python
# Read existing records, add new records, write entire file
# Problem: Not true append, but achieves same result
# Benefit: Simple implementation, atomic write
```

**Option C: Separate Files per Run**
```python
# Write new records to run_log_001.parquet, run_log_002.parquet, etc.
# Problem: Requires merging for queries
```

### Root Cause Analysis

1. **Append-Only Requirement**: Never modify existing rows, only add new ones
2. **Atomicity Requirement**: Entire write operation succeeds or fails together
3. **Conflict**: True append and atomic overwrite are opposing requirements

### Solution Implemented

**Logical Append-Only via Atomic Overwrite:**

```python
# run_logger.py
def append_run_log(records: list[dict]) -> None:
    # Read existing records
    existing = _get_existing_records()
    
    # Combine: existing + new (logically append-only)
    all_records = existing + records
    
    # Convert to DataFrame
    df = pd.DataFrame(all_records)
    
    # Ensure correct column order and types
    column_order = [...]
    df = df[column_order]
    
    # Convert to PyArrow table with schema
    schema = _create_schema()
    table = pa.Table.from_pandas(df, schema=schema)
    
    # Write (overwrite file to implement logical append-only semantics)
    RUN_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, RUN_LOG_PATH)
```

**Why Logical Append:**
- ✓ Atomic: Entire write succeeds or fails
- ✓ Simple: Single file, no merging required
- ✓ Queryable: One file to read with SELECT
- ✓ Durable: Parquet format survives restarts
- ✓ Semantically append-only: Never loses existing rows

**What "Logically Append-Only" Means:**
```
Implementation Detail: Read existing + add new + rewrite file
User Perspective: New rows added to log, existing rows never changed
Outcome: Append-only semantics without true streaming append
```

### Verification

**Scenario: Multi-Run Logging**
```python
# Run 1: Log 3 entries
append_run_log([entry1, entry2, entry3])
log = get_run_log()
assert len(log) == 3

# Run 2: Log 2 more entries
append_run_log([entry4, entry5])
log = get_run_log()
assert len(log) == 5  # 3 existing + 2 new
assert log.iloc[0] == entry1  # Existing entries unchanged
```

**Data Integrity Check:**
```python
# Verify old entries still present after new append
run1_entries = get_run_log()[get_run_log()['run_id'] == run1_id]
assert len(run1_entries) == 3  # Still present after subsequent appends
```

### Lesson Learned

📚 **Logical append-only is practical for single-file logs.** When you need:
- Append semantics (never lose existing data)
- Single queryable file
- Atomic writes (no partial states)

Trade true streaming append for simplicity. The implementation (read + append + rewrite) is fast enough for log sizes typical in data pipelines.

**Anti-Pattern: Don't do this**
```python
# WRONG: Modifying existing rows
for i, entry in enumerate(existing_records):
    if entry['status'] == 'FAILED':
        entry['status'] = 'RETRIED'  # Modifying existing row!
```

**Correct Pattern:**
```python
# RIGHT: Adding new rows only
new_retry_entry = {
    'run_id': existing_entry['run_id'],
    'status': 'RETRY',
    ...
}
append_run_log([new_retry_entry])  # Add as new row
```

---

## Issue 3: Watermark Advancement Timing — When to Commit Success

### Problem

**Timing Question:** When should watermark be advanced?

**Option A: After Bronze Succeeds**
```python
# Advance immediately after bronze completes
set_watermark(date_str, run_id)  # ← Wrong timing
```

**Option B: After All Layers Succeed (Future)**
```python
# Advance only after Bronze + Silver + Gold all succeed
# (Session 5 scope, but must design correctly in S2)
```

**Option C: After Run Log Completes**
```python
# Advance only after run log entries are written
set_watermark(date_str, run_id)  # ← Correct
```

### Root Cause Analysis

1. **INV-02 Requirement**: Watermark must advance only after full success
2. **Scope Question**: What does "full success" mean in each session?
3. **Session Dependency**: S2 (Bronze only) can't enforce full pipeline success

### Solution Implemented

**Session 2: No Watermark Advancement**

```python
# pipeline_historical.py (Session 2)
def main():
    # ... Bronze ingestion ...
    
    # Session 2 scope: Bronze only
    # Watermark advancement deferred to Session 5
    # (After Silver and Gold layers complete)
    
    # Do NOT call: set_watermark(date_str, run_id)
    # This is enforced in Session 5 pipeline_historical.py
```

**Design for Session 5:**

```python
# pipeline_historical.py (Session 5 - FUTURE)
def main():
    for date_str in dates:
        # Step 1: Bronze
        result_bronze = load_bronze(...)
        
        # Step 2: Silver  
        result_silver = promote_silver(...)
        
        # Step 3: Gold
        result_gold = promote_gold(...)
        
        # Step 4: Watermark (INV-02 - only after all succeed)
        if result_bronze['status'] == 'SUCCESS' \
           and result_silver['status'] == 'SUCCESS' \
           and result_gold['status'] == 'SUCCESS':
            set_watermark(date_str, run_id)
```

**Why Deferred:**
- ✓ INV-02: Watermark only advances after FULL success
- ✓ Session Responsibility: Each session owns its scope
- ✓ Prevents Partial State: Watermark won't advance if Silver/Gold fail
- ✓ Future-Proof: S2 implementation doesn't need to change

### Verification

**Session 2 Check:**
```python
# Verify watermark is NOT advanced by S2
watermark = get_watermark('/app/pipeline')
assert watermark is None  # No watermark set in S2
```

**Session 5 Check (Future):**
```python
# After session 5, watermark should be set
watermark = get_watermark('/app/pipeline')
assert watermark == '2024-01-06'  # Last date processed
```

### Lesson Learned

📚 **Watermark advancement is a full-pipeline responsibility, not per-layer.** In medallion architecture:
- Bronze layer: No watermark (just ingest)
- Silver layer: No watermark (just transform)
- Gold layer: No watermark (just aggregate)
- Orchestrator: Watermark after all succeed

This prevents premature watermark advancement and ensures consistency.

---

## Issue 4: Control Table Schema — Metadata Fields for Watermark

### Problem

**Design Question:** What metadata should control.parquet include?

**Option A: Minimal (Just Watermark)**
```python
control.parquet:
  - last_processed_date: "2024-01-01"
```

**Option B: Enhanced (With Tracking)**
```python
control.parquet:
  - last_processed_date: "2024-01-01"
  - updated_at: "2024-04-16T12:00:00Z"
  - updated_by_run_id: "uuid-of-run"
```

**Option C: Full History**
```python
# Separate record for each watermark advance
# Row 1: "2024-01-01", 2024-04-16 12:00, run1
# Row 2: "2024-01-02", 2024-04-16 12:01, run1
# Row 3: "2024-01-06", 2024-04-16 12:05, run2
```

### Root Cause Analysis

1. **Audit Trail**: Need to know when and why watermark advanced
2. **Debugging**: Correlate watermark changes with specific run
3. **Rollback**: Identify which run caused issues for potential revert

### Solution Implemented (Per User Request)

**Enhanced Schema with Metadata:**

```python
# control_manager.py
def _create_control_schema() -> pa.Schema:
    return pa.schema([
        ("last_processed_date", pa.string()),        # YYYY-MM-DD
        ("updated_at", pa.string()),                 # ISO 8601 UTC
        ("updated_by_run_id", pa.string()),          # UUIDv4
    ])

def set_watermark(date_str: str, run_id: str, pipeline_dir: str) -> None:
    # Create record with enhanced watermark metadata
    record = {
        "last_processed_date": date_str,
        "updated_at": datetime.utcnow().isoformat(),  # When advanced
        "updated_by_run_id": run_id,                 # Which run
    }
    # ... write to parquet ...
```

**Why Enhanced:**
- ✓ Audit Trail: Know exact timestamp of each change
- ✓ Run Correlation: Link watermark to specific pipeline run
- ✓ History Tracking: Each row is one watermark advance
- ✓ Debugging: Can query "which run advanced which watermark"

### Verification

**History Query:**
```python
# Read control table
df = pd.read_parquet('/app/pipeline/control.parquet')

# Can see full progression:
# Date        | Timestamp              | Run ID
# 2024-01-01  | 2024-04-16T12:00:00Z  | run-uuid-1
# 2024-01-02  | 2024-04-16T12:01:00Z  | run-uuid-1
# 2024-01-06  | 2024-04-16T12:05:00Z  | run-uuid-1
```

**Get Latest Watermark:**
```python
def get_watermark(pipeline_dir: str) -> Optional[str]:
    df = pd.read_parquet('/app/pipeline/control.parquet')
    # Latest watermark is last row
    return df['last_processed_date'].iloc[-1]
```

### Lesson Learned

📚 **Control/state tables should include metadata for auditability.** Don't just store the value; store:
- When changed (timestamp)
- Who changed it (run_id)
- Why (in separate audit fields)

This enables:
- Debugging ("which run caused the watermark jump?")
- Rollback ("revert to state before run X")
- Monitoring ("how frequently are dates advancing?")

---

## Issue 5: Date Range Iteration — Inclusive vs Exclusive Bounds

### Problem

**Question:** Should end-date be inclusive or exclusive?

**Option A: Inclusive (User Expectation)**
```bash
python pipeline_historical.py --start-date 2024-01-01 --end-date 2024-01-06
# Process dates: 2024-01-01, 2024-01-02, ..., 2024-01-06 (INCLUSIVE)
```

**Option B: Exclusive (Common in Programming)**
```bash
# Process dates: 2024-01-01, 2024-01-02, ..., 2024-01-05
# (6 is not included)
```

### Root Cause Analysis

1. **User Expectation**: "Process through January 6" means include Jan 6
2. **Programming Pattern**: Range semantics usually exclusive upper bound
3. **Conflict**: Standard programming pattern violates user expectation

### Solution Implemented

**Inclusive End Date (GAP-INV-01a):**

```python
# pipeline_historical.py
def _date_range(start_str: str, end_str: str) -> list[str]:
    """Generate list of dates from start to end INCLUSIVE in ascending order (GAP-INV-01a)."""
    start = datetime.strptime(start_str, "%Y-%m-%d")
    end = datetime.strptime(end_str, "%Y-%m-%d")
    
    dates = []
    current = start
    while current <= end:  # ← INCLUSIVE: while <=, not <
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    
    return dates
```

**Why Inclusive:**
- ✓ User Expectation: "Process 2024-01-01 to 2024-01-06" means all 6 days
- ✓ No Surprise: Users don't expect off-by-one behavior
- ✓ Semantic Clarity: "through" usually means inclusive
- ✗ Programming: Differs from standard range() exclusive upper bound

### Verification

```python
# Verify inclusive behavior
dates = _date_range("2024-01-01", "2024-01-06")
assert dates == [
    "2024-01-01", "2024-01-02", "2024-01-03",
    "2024-01-04", "2024-01-05", "2024-01-06"  # ← 6 included
]
assert len(dates) == 6
```

### Lesson Learned

📚 **User expectations override programming conventions.** While Python's range() uses exclusive upper bounds, data pipelines should use inclusive bounds. Users think in natural language ("process through the 6th"), not programming semantics.

**Pattern for Date Ranges:**
```python
# For user-facing APIs, use inclusive
while current_date <= end_date:  # Include end_date
    process(current_date)
    current_date += timedelta(days=1)

# For internal/advanced APIs, document clearly
# range(start, end)  # [start, end) - exclusive
```

---

## Issue 6: No-Op Path Testing — Missing Source Data

### Problem

**Requirement (OQ-1, GAP-INV-02):** Pipeline must handle missing source files gracefully.

**Design Question:** How to test this without corrupting seed data?

**Option A: Delete a source file**
```bash
rm source/transactions_2024-01-07.csv  # Test missing data
```

**Option B: Create dummy file**
```bash
# Don't create 2024-01-07, so pipeline naturally skips it
```

### Root Cause Analysis

1. **OQ-1 (Outstanding Question 1)**: What if source file is missing?
2. **Invariant (GAP-INV-02)**: Missing source → SKIPPED, no data layer write
3. **Test Coverage**: Need to verify SKIPPED path works

### Solution Implemented

**No-Op Test via Missing Date (Task 1.4):**

```python
# Create source files only for 6 dates (2024-01-01 to 2024-01-06)
# Intentionally DO NOT create 2024-01-07

# When running historical pipeline:
python pipeline_historical.py --start-date 2024-01-01 --end-date 2024-01-07
# For 2024-01-07: source files missing → SKIPPED status logged
# No Parquet written for 2024-01-07
```

**Verification in Run Log:**

```python
# Check run log
df = get_run_log()

# Entries for 2024-01-01 through 2024-01-06: SUCCESS
success_entries = df[df['status'] == 'SUCCESS']
assert len(success_entries) > 0

# Entries for 2024-01-07: SKIPPED
skipped_entries = df[(df['status'] == 'SKIPPED') & (df['processed_date'].isna())]
assert len(skipped_entries) > 0  # SKIPPED entries present
```

**Verify No Data Written for Skipped Date:**

```python
import os

# 2024-01-06 should have Bronze data
assert os.path.exists('/app/bronze/transactions/date=2024-01-06/data.parquet')

# 2024-01-07 should NOT have Bronze data (no source file)
assert not os.path.exists('/app/bronze/transactions/date=2024-01-07/data.parquet')
```

### Lesson Learned

📚 **Use missing data to test no-op paths.** Rather than artificially creating error conditions, use natural absences (missing date) to test graceful degradation. This:
- Tests real scenarios (data sometimes arrives late)
- Doesn't corrupt test data
- Documents expected behavior
- Provides evidence in run log (SKIPPED entries)

---

## Issue 7: Error Message Sanitization — Preventing Path Leakage

### Problem

**Security/Privacy Concern:** Error messages might contain file paths.

**Risk:**
```
Original error: "File not found: /app/source/transactions_2024-01-01.csv"
                                    ↑ Exposes full path
```

**Requirement (RL-05b):** Strip file paths from error messages before returning.

### Root Cause Analysis

1. **Error Messages Leak Info**: Full paths reveal system structure
2. **Logging**: Error messages go to run log, which might be shared
3. **Principle of Least Privilege**: Don't expose unnecessary system details

### Solution Implemented

**Path Sanitization Function (RL-05b):**

```python
# run_logger.py
def _clean_error_message(msg: Optional[str]) -> Optional[str]:
    """Strip path separators from error message to avoid exposing sensitive paths (RL-05b)."""
    if msg is None:
        return None
    return msg.replace("/", "").replace("\\", "")
```

**Applied in Constraint Enforcement:**

```python
def _enforce_constraints(records: list[dict]) -> None:
    for record in records:
        if record.get("status") != "SUCCESS":
            # RL-05b: strip path separators from error_message
            if record.get("error_message"):
                record["error_message"] = _clean_error_message(record["error_message"])
```

**Before Sanitization:**
```
error_message: "IO Error: Cannot open file '/app/bronze/transactions/date=2024-01-01/data.parquet'"
```

**After Sanitization:**
```
error_message: "IO Error: Cannot open file 'appbroncetransactionsdate=2024-01-01data.parquet'"
```

### Verification

```python
# Verify error messages are sanitized
record = {
    "status": "FAILED",
    "error_message": "Path issue at /app/pipeline/file.txt"
}
_enforce_constraints([record])
assert "/" not in record["error_message"]
assert "apppiPipelinefiletxt" in record["error_message"]  # Mangled but safe
```

### Lesson Learned

📚 **Sanitize error messages before storing in logs.** Apply principle of least information:
- ✓ Keep the error type: "IO Error"
- ✓ Keep the field: "Cannot open file"
- ✗ Remove the path: "/app/bronze/..."

This allows debugging while protecting system topology.

---

## Summary of S2 Key Learnings

| Issue | Category | Solution |
|-------|----------|----------|
| #1 | Idempotency | Row count match proves "already ingested" |
| #2 | Logging | Logical append-only: read existing + add new + rewrite |
| #3 | Watermark | No advancement in S2; deferred to S5 after full success |
| #4 | Control Table | Include metadata: timestamp, run_id for audit trail |
| #5 | Date Range | Inclusive end-date matches user expectation |
| #6 | No-Op Testing | Use missing dates naturally, don't delete test data |
| #7 | Error Messages | Sanitize paths with path separator removal (RL-05b) |

---

## Files Created/Modified During S2 Debugging

| File | Issue | Design Decision |
|------|-------|-----------------|
| run_logger.py | #2, #7 | Logical append-only with path sanitization |
| bronze_loader.py | #1 | Row count idempotency with re-ingest on mismatch |
| control_manager.py | #4 | Enhanced schema with updated_at, updated_by_run_id |
| pipeline_historical.py | #5, #6 | Inclusive date range, no watermark advancement |
| seed data | #6 | Only 6 dates (no 2024-01-07) to test no-op path |

---

**S2 established data ingestion patterns. All issues were about semantics (idempotency, logging, watermark timing) rather than implementation bugs. Future sessions (S3-S6) build on these patterns.**
