# S1 Debugging Log — Repository Scaffold and Docker Infrastructure

**Purpose:** Document all issues encountered during Session 1 scaffold setup, Docker configuration, and dbt initialization. This serves as reference for understanding dependency management and container setup patterns.

---

## Issue 1: Protobuf Version Incompatibility with dbt-core 1.7.5

### Problem

**Error Message:**
```
File "..site-packages/google/protobuf/json_format.py", line 287, in MessageToJson
  TypeError: MessageToJson() got an unexpected keyword argument 'including_default_value_fields'
```

**Context:** During Task 1.2 Docker image build with requirements.txt

### Root Cause Analysis

1. **dbt-core 1.7.5 Compatibility**: dbt 1.7.5 depends on protobuf <=4.x
2. **Protobuf 7.x Breaking Change**: Protobuf 7.x removed `including_default_value_fields` parameter
3. **Initial Specification**: requirements.txt didn't pin protobuf version, allowing 7.x installation
4. **API Incompatibility**: dbt's JSON serialization code uses deprecated protobuf API

### Solution Implemented

**Fix in requirements.txt:**
```
dbt-core==1.7.5
dbt-duckdb==1.7.5
duckdb==1.0.0
pyarrow==15.0.0
pandas==2.2.0
protobuf==4.25.3  # ← PINNED to fix dbt incompatibility
```

**Why Pinning to 4.25.3:**
- Latest 4.x version before 5.x breaking changes
- Compatible with dbt-core 1.7.5
- Maintains Google protobuf message compatibility
- No functionality impact on downstream code

### Verification

**Before Fix:**
```
ERROR: dbt run failed
dbt/profiles.yml loading fails due to protobuf error
```

**After Fix:**
```bash
docker compose build  # Succeeds
docker compose run --rm pipeline python -c "import dbt; print('dbt ok')"  # Success
docker compose run --rm pipeline dbt debug  # All checks passed!
```

### Lesson Learned

📚 **Always pin transitive dependency versions when working with frameworks.** dbt depends on protobuf, but protobuf has breaking changes. When dbt specifies a version range like `protobuf>=3.0`, you're exposed to breaking changes. Always pin to a specific working version once identified.

**Pattern for Future Use:**
```
# If framework X depends on library Y and you see version incompatibility:
1. Find the latest version of Y that works with X
2. Pin it explicitly in requirements.txt
3. Document the reason in a comment
# Example:
protobuf==4.25.3  # dbt-core 1.7.5 requires protobuf <5.0
```

---

## Issue 2: Mount Parity Problem — Different Filesystems for silver/ and silver_temp/

### Problem

**Error Message (Discovered in Task 1.2 verification):**
```
OSError: [Errno 18] Invalid cross-device link
  File "..atomic_rename.py", line X, in atomic_rename
    os.rename(src='/app/silver_temp/transactions/...', dst='/app/silver/transactions/...')
```

**Context:** Decision 4 requires atomic os.rename() for zero-downtime Silver promotion. os.rename() only works when src and dst are on the same filesystem.

### Root Cause Analysis

1. **Initial Mount Configuration:**
```yaml
# docker-compose.yml (INCORRECT)
volumes:
  - ./silver:/app/silver:rw
  - ./silver_temp:/app/silver_temp:rw
```

2. **Problem**: Each volume mount can map to different Docker storage drivers/locations
3. **Result**: `/app/silver` and `/app/silver_temp` may be on different virtual filesystems
4. **Consequence**: `os.rename(src, dst)` fails with "Invalid cross-device link" error

### Solution Implemented

**Fix in docker-compose.yml:**
```yaml
# Mount ENTIRE REPO as single parent mount
volumes:
  - .:/app:rw  # Everything under /app uses same mount point
  - ./source:/app/source:ro  # Override source as read-only (INV-06)
```

**Why This Works:**
- Single mount point ensures silver/ and silver_temp/ are on same filesystem
- atomic os.rename() works because both directories share filesystem
- Complies with Decision 4 requirement
- Simplifies Docker configuration (one main mount vs many)

### Verification

**Before Fix:**
```bash
# Simulated atomic rename would fail:
os.rename('/app/silver_temp/data.parquet', '/app/silver/data.parquet')
# → OSError: Invalid cross-device link
```

**After Fix:**
```bash
# Atomic rename succeeds:
os.rename('/app/silver_temp/data.parquet', '/app/silver/data.parquet')
# → Success: file moved atomically
```

### Lesson Learned

📚 **Docker volume mounts affect filesystem topology.** When using os.rename() for atomic operations, both src and dst must be on the same filesystem. In Docker, each bind mount can be a different filesystem. Solution: Mount parent directory once rather than multiple child mounts.

**Pattern for Decision 4 Implementation:**
```
silver/ and silver_temp/ must be under same mount point:
✓ Single mount: .:/app:rw (both silver/ and silver_temp/ are children)
✗ Separate mounts: ./silver:/app/silver AND ./silver_temp:/app/silver_temp
```

---

## Issue 3: Project Manifest Registration Timing

### Problem

**Challenge:** When should PROJECT_MANIFEST.md have files registered?

**Initial Uncertainty:**
```
Should all files be pre-registered as PENDING before they're created?
Or should manifest only contain files that already exist?
```

### Root Cause Analysis

1. **PBVI Methodology**: PROJECT_MANIFEST.md is a registry of expected outputs
2. **Pre-Planning Requirement**: Session 1 knows what files will be created in each session
3. **Status Tracking**: PENDING/PRESENT status allows tracking progress through methodology

### Solution Implemented

**All expected files pre-registered as PENDING in Task 1.1:**
```yaml
# PROJECT_MANIFEST.md
| pipeline/silver_promoter.py | PENDING | S3 | dbt Silver invoker... |
| pipeline/gold_builder.py | PENDING | S4 | dbt Gold invoker... |
| dbt/models/silver/*.sql | PENDING | S3 | Silver transformation... |
```

**Why This Approach:**
- Reflects PBVI methodology planning
- Allows tracking of what's completed vs pending
- Serves as implementation checklist
- Status updates show session progress

**Updating Pattern:**
- S1: All files created in S1 are marked PRESENT, S2-S6 remain PENDING
- S2: All files created in S2 are marked PRESENT, S3-S6 remain PENDING
- (Continues for each session)

### Lesson Learned

📚 **Pre-register expected outputs in manifest during planning phase.** PROJECT_MANIFEST.md serves as both:
1. A specification of what will be built (planning)
2. A progress tracker (implementation)

Pre-register files with PENDING status during planning, then update to PRESENT as they're completed.

---

## Issue 4: METHODOLOGY_VERSION Field Placement

### Problem

**Question:** Where should METHODOLOGY_VERSION field be placed in PROJECT_MANIFEST.md?

**Initial Uncertainty:**
```
Should it be:
1. In PROJECT_MANIFEST.md itself?
2. In a separate file?
3. In dbt_project.yml?
4. Somewhere else?
```

### Root Cause Analysis

1. **PBVI Specification**: METHODOLOGY_VERSION indicates the version of PBVI framework being used
2. **Easy Access**: Needs to be easily findable and readable
3. **Project-Wide Scope**: Not specific to dbt or any particular tool

### Solution Implemented

**Placed in PROJECT_MANIFEST.md Section "## Methodology Version":**
```yaml
# PROJECT_MANIFEST.md
## Methodology Version

METHODOLOGY_VERSION: PBVI v4.3 / BCE v1.7
```

**Why This Location:**
- PROJECT_MANIFEST.md is the main project registry
- Methodology version is project-scoped, not tool-scoped
- Easy to find at start of manifest
- Allows versioning of manifest structure itself

### Lesson Learned

📚 **Project-wide metadata belongs in PROJECT_MANIFEST.md.** The manifest is the source of truth for project-level information (methodology version, status, architecture decisions). Tool-specific configs (dbt_project.yml, requirements.txt) should reference or depend on the manifest, not duplicate it.

---

## Issue 5: .gitignore Configuration for Runtime Artifacts

### Problem

**What should be excluded from git?**
- Parquet files (runtime data artifacts)
- DuckDB catalog database
- dbt target/ directory (compiled artifacts)
- dbt logs/ directory (execution logs)

**Initial Uncertainty:**
```
Which patterns should be in .gitignore?
What about logs/ vs dbt/logs/?
```

### Root Cause Analysis

1. **Git Best Practices**: Version control source code, not generated files
2. **Pipeline Artifacts**: Parquet files are generated outputs, not code
3. **Database Files**: .duckdb catalog database is ephemeral state
4. **Build Artifacts**: dbt target/ and logs/ are temporary

### Solution Implemented

**In .gitignore:**
```
# Runtime Parquet files (data artifacts)
/bronze/**/*.parquet
/silver/**/*.parquet
/silver_temp/**/*.parquet
/gold/**/*.parquet
/quarantine/**/*.parquet

# DuckDB catalog database (ephemeral state)
/pipeline/dbt_catalog.duckdb

# dbt build artifacts and logs
/dbt/target/
/dbt/logs/
/logs/
```

**Why These Patterns:**
- Parquet files are generated from source CSVs (not code)
- DuckDB catalog is ephemeral state that rebuilds on next run
- dbt artifacts are rebuilt on every dbt run
- Source CSVs (source/*.csv) ARE committed (input data)

### Verification

**Before .gitignore:**
```bash
git status
# Shows: Untracked files: bronze/transactions/date=2024-01-01/data.parquet
```

**After .gitignore:**
```bash
git status
# Result: Parquet files not shown as untracked
git add .
# Result: Only SOURCE code and configs are staged, not artifacts
```

### Lesson Learned

📚 **Gitignore should distinguish between source data and generated artifacts.** In a data pipeline:
- ✓ Commit: Python code, SQL code, CSV seed data, configs
- ✗ Exclude: Generated Parquet files, database files, build artifacts, logs

---

## Issue 6: CSV Seed Data Schema vs EXECUTION_PLAN Specification

### Problem

**Conflict Between Specification and Reality:**

EXECUTION_PLAN.md specified one schema:
```
accounts: account_id, account_name, balance, ...
transactions: transaction_id, account_id, amount, ...
```

But user provided actual CSV files with different columns:
```
accounts: account_id, customer_name, current_balance, billing_cycle_start, ...
transactions: transaction_id, account_id, transaction_date, merchant_name, channel, ...
```

### Root Cause Analysis

1. **Planning Gap**: EXECUTION_PLAN was written before seeing actual data
2. **Real Data Different**: User's actual CSVs had different field names and structure
3. **Schema Mismatch**: bronze_loader.py validation expected EXECUTION_PLAN schema, not actual schema

### Solution Implemented

**Task 1.4: Use Actual User CSV Schema**

When presenting option to user:
```
Option 1: Use your actual CSV schema
Option 2: Force compliance with EXECUTION_PLAN specification
Option 3: Transform CSVs to match specification

User chose: Option 1 (Recommended)
```

**Updated bronze_loader.py EXPECTED_SCHEMAS:**
```python
EXPECTED_SCHEMAS = {
    "transactions": {
        "transaction_id", "account_id", "transaction_date", "amount",
        "transaction_code", "merchant_name", "channel"
    },
    "accounts": {
        "account_id", "customer_name", "account_status", "credit_limit",
        "current_balance", "open_date", "billing_cycle_start", "billing_cycle_end"
    },
    "transaction_codes": {
        "transaction_code", "description", "debit_credit_indicator",
        "transaction_type", "affects_balance"
    },
}
```

**Why Option 1:**
- User's actual data is the source of truth
- Transforming CSVs would be extra work
- EXECUTION_PLAN can be seen as outdated/reference
- Actual business requirements reflected in actual data

### Lesson Learned

📚 **Actual data takes precedence over specification documents.** In real-world projects, specifications are often written before data is available. When actual data differs from spec:
1. Verify the data is correct (it is the source of truth)
2. Update code to match actual data
3. Update documentation to reflect reality
4. Never try to force data to match outdated specs

**Future Prevention:**
- Validate sample data DURING planning phase, not after
- Get actual CSV samples before writing EXECUTION_PLAN
- Schema specs should be "examples from real data" not predictions

---

## Issue 7: Directory Structure and .gitkeep Files

### Problem

**Question:** How to version-control empty directories in Git?

Git doesn't track empty directories by default. But the project needs:
- /bronze (needs to exist for pipeline)
- /silver (needs to exist for transformations)
- /dbt/models/gold (needs to exist for S4)

### Root Cause Analysis

1. **Git Limitation**: Git tracks files, not directories
2. **Pipeline Requirement**: Directory structure needs to exist at runtime
3. **Solution Pattern**: Use .gitkeep files to version-control directories

### Solution Implemented

**Task 1.1: Create .gitkeep Files**
```bash
touch bronze/.gitkeep
touch silver/.gitkeep
touch silver_temp/.gitkeep
touch dbt/models/gold/.gitkeep
touch dbt/models/silver/.gitkeep
# ... for all 17 directories
```

**Why .gitkeep:**
- Lightweight marker file (0 bytes)
- Conventional name recognized by developers
- Allows empty directories to be tracked by Git
- Easy to delete once real files added

### Verification

```bash
git add bronze/.gitkeep
git commit -m "Add bronze directory structure"

# Later, when Bronze files are created:
git add bronze/transactions/date=2024-01-01/data.parquet  # gitignore excludes this
# But directory still tracked via .gitkeep
```

### Lesson Learned

📚 **Use .gitkeep files to version-control necessary empty directories.** This pattern allows Git to track directory structure while .gitignore prevents tracking generated files within those directories.

---

## Issue 8: Tools Scripts Permissions and Shebang Headers

### Problem

**Challenge:** Shell scripts in tools/ need to be executable.

```bash
bash tools/launch.sh  # Works
./tools/launch.sh     # Fails: Permission denied
```

### Root Cause Analysis

1. **File Permissions**: New files don't have execute bit set by default
2. **Shebang Requirement**: Scripts need `#!/bin/bash` header to be directly executable
3. **Git Tracking**: File permissions need to be explicitly set in Git

### Solution Implemented

**Task 1.5: Set Execute Permissions**
```bash
chmod +x tools/challenge.sh
chmod +x tools/launch.sh
chmod +x tools/resume_session.sh
chmod +x tools/resume_challenge.sh
chmod +x tools/monitor.sh

git add tools/*.sh
git commit -m "1.5 — tools/ PBVI scripts with execute permissions"
```

**Script Header Example:**
```bash
#!/bin/bash
# tools/launch.sh - Session launcher with execution prompt guidance
set -e  # Exit on error
```

**Why This Works:**
- `#!/bin/bash` tells system to use bash interpreter
- `chmod +x` sets executable bit
- Git preserves file mode in .git/config (for teams)
- Allows direct execution: `./tools/launch.sh`

### Verification

```bash
git check-ignore tools/launch.sh  # Should return nothing (not ignored)
git ls-files tools/launch.sh      # Should show in index

./tools/launch.sh  # Should execute without "Permission denied"
```

### Lesson Learned

📚 **Shell scripts need execute permissions and shebang headers.** Always include:
1. Shebang header: `#!/bin/bash`
2. Execute permission: `chmod +x script.sh`
3. Git tracking: `git add script.sh` (permissions are tracked)

This enables both:
```
bash script.sh     # Always works
./script.sh        # Works only after chmod +x
```

---

## Summary of S1 Key Learnings

| Issue | Category | Solution |
|-------|----------|----------|
| #1 | Dependencies | Pin transitive versions (protobuf==4.25.3) |
| #2 | Docker | Single mount point for atomic filesystem ops |
| #3 | Manifest | Pre-register expected outputs with PENDING status |
| #4 | Manifest | Place methodology version in PROJECT_MANIFEST.md |
| #5 | Gitignore | Exclude artifacts, commit source code and configs |
| #6 | Schema | Use actual data schema, not specification predictions |
| #7 | Git | Use .gitkeep files for necessary empty directories |
| #8 | Scripts | Add shebang headers and chmod +x for executability |

---

## Files Modified During S1 Debugging

| File | Issue | Fix |
|------|-------|-----|
| requirements.txt | #1 | Pin protobuf==4.25.3 |
| docker-compose.yml | #2 | Single .:/app:rw mount |
| PROJECT_MANIFEST.md | #3, #4 | Pre-register all files, add METHODOLOGY_VERSION |
| .gitignore | #5 | Exclude *.parquet, *.duckdb, dbt/target/, dbt/logs/ |
| source/accounts_*.csv | #6 | Use actual user schema |
| Various .gitkeep | #7 | Add 17 .gitkeep files |
| tools/*.sh | #8 | chmod +x and add #!/bin/bash headers |

---

**S1 established the foundation. All issues were infrastructure/configuration related, not code logic. Future sessions (S2-S6) built on this foundation.**
