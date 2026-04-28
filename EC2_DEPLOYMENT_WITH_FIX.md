# EC2 Deployment - dbt-duckdb Path Bug FIX

**Status:** ✅ Ready for EC2 deployment  
**Fix Applied:** Path bug patched in dbt-duckdb source  
**CloudFormation:** Already deployed yesterday  
**EC2 Instance:** Running and ready  

---

## 🎯 Summary: What Changed & Why

### The Problem (What You Discovered)
- ✅ CloudFormation deployed successfully
- ✅ EC2 instance is running
- ❌ dbt models fail because `render()` function corrupts S3 paths

### The Root Cause
```jinja
# BEFORE (broken)
{%- set location = render(config.get('location', default=external_location(this, config))) -%}

# Path result: s3:bucketsilverapoaccountsdata.parquet ❌ (slashes removed!)
```

### The Fix Applied
```jinja
# AFTER (fixed)
{%- set location = config.get('location', default=external_location(this, config)) -%}

# Path result: s3://bucket/silver/accounts/data.parquet ✅
```

### Files Modified
- ✅ `Infra/dbt-duckdb-source/dbt/include/duckdb/macros/materializations/external.sql`
  - Removed problematic `render()` call on line 2
  - Added explanatory comment

---

## 🚀 EC2 Deployment Steps (Sequential)

### Phase 1: SSH Into EC2 Instance

```bash
# Get your EC2 IP from CloudFormation
EC2_IP=$(aws cloudformation describe-stacks \
  --stack-name cc-transactions-lake-stack \
  --region us-east-1 \
  --query 'Stacks[0].Outputs[?OutputKey==`EC2InstancePublicIP`].OutputValue' \
  --output text)

echo "Connecting to: $EC2_IP"

# SSH in
ssh -i ~/.ssh/cc-transactions-lake-key.pem ec2-user@$EC2_IP
```

### Phase 2: Fix the Repository (On EC2)

```bash
# Once logged into EC2
cd /app

# Remove the current (wrong) repository clone
rm -rf .git

# Clone the CORRECT repository with the patch
git clone https://github.com/SaiKrishnaAkulaDG/credit-card-transactions-lake-v2.git .

# Checkout the fix branch
git checkout session/s6_verification

# Verify the patch is present
grep -n "FIXED" dbt/include/duckdb/macros/materializations/external.sql
# Should show: Line with "FIXED: Removed render()"
```

### Phase 3: Build Docker Image with Patched dbt-duckdb (On EC2)

```bash
cd /app

# Build the patched Docker image
# NOTE: This uses Dockerfile.patched which installs dbt-duckdb from patched source
docker build -f Dockerfile.patched -t app-pipeline:fixed .

# Verify build succeeded
docker images | grep app-pipeline
```

### Phase 4: Run Bronze Layer Test (Verification)

```bash
# Test Bronze ingestion (should work without patch)
docker-compose run --rm pipeline python3 << 'EOF'
import sys
sys.path.insert(0, '/app')
from pipeline.bronze_loader import load_bronze_layer
from datetime import datetime
import uuid

run_id = str(uuid.uuid4())
print(f"Testing Bronze layer with run_id: {run_id}")
result = load_bronze_layer("2024-01-01", "/app", run_id)
print(f"Status: {result['status']}")
print(f"Records: {result}")
EOF
```

**Expected Output:**
```
Status: SUCCESS
Records written: X accounts + Y transactions
```

### Phase 5: Run Silver Layer Test (THE FIX!)

```bash
# This is where the fix matters!
docker-compose run --rm pipeline dbt run --select silver_accounts

# BEFORE FIX: 
#   ERROR: IO Error: Cannot open file "s3:cc-transactions-lake..."
#
# AFTER FIX:
#   Compiled code for silver_accounts
#   sqlglot: A SQL parser
#   ...
#   Created sql_models.silver_accounts
```

### Phase 6: Full Pipeline Run

```bash
# Run the complete pipeline with the fix
docker-compose run --rm pipeline python3 pipeline/pipeline_historical.py \
  --start-date 2024-01-01 \
  --end-date 2024-01-06

# Expected output:
# ✓ Bronze ingestion complete
# ✓ Silver transformation complete
# ✓ Gold aggregation complete
# ✓ Run log updated
# ✓ Watermark advanced to 2024-01-06
```

### Phase 7: Verify S3 Output

```bash
# Check that files exist in S3 with CORRECT paths
aws s3 ls s3://cc-transactions-lake-deploy-2026/silver/ --recursive

# Should show paths like:
# 2026-04-28 12:34:56       5678 silver/accounts/data.parquet
# 2026-04-28 12:34:56       9012 silver/transactions/date=2024-01-01/data.parquet
# 2026-04-28 12:34:56       3456 silver/quarantine/data.parquet

aws s3 ls s3://cc-transactions-lake-deploy-2026/gold/ --recursive

# Should show:
# 2026-04-28 12:34:56       1234 gold/daily_summary/data.parquet
# 2026-04-28 12:34:56       5678 gold/weekly_account_summary/data.parquet
```

---

## ✅ Verification Checklist

As you complete each phase, check off:

- [ ] SSH into EC2 successful
- [ ] Repository cloned with patch applied
- [ ] Verified patch in external.sql
- [ ] Docker image builds successfully (Dockerfile.patched)
- [ ] Bronze layer test passes (returns SUCCESS)
- [ ] Silver layer runs without path errors
- [ ] Full pipeline completes (all 3 phases)
- [ ] S3 files exist with correct paths
- [ ] Watermark advanced to final date
- [ ] No errors in CloudWatch logs

---

## 🔍 Troubleshooting

### Issue: "File not found" errors with S3 paths

```
ERROR: IO Error: Cannot open file "s3:cc-transactions..."
```

**Solution:** Patch not applied. Verify:
```bash
grep "FIXED" dbt/include/duckdb/macros/materializations/external.sql
```

Should show the FIXED comment. If not, re-run:
```bash
git checkout session/s6_verification
```

### Issue: Docker build fails

```
ERROR: unable to prepare context: path does not exist
```

**Solution:** Make sure you're in /app directory:
```bash
cd /app && docker build -f Dockerfile.patched -t app-pipeline:fixed .
```

### Issue: AWS credentials not working

```
ERROR: Unable to assume IAM role
```

**Solution:** The EC2 instance has IAM role attached (via CloudFormation). Verify:
```bash
aws sts get-caller-identity
# Should show EC2 role, not user credentials
```

---

## 📊 Expected Results After Fix

### Bronze Layer
- ✅ 6 CSV files ingested
- ✅ 2 entity types (accounts, transactions)
- ✅ ~500 total records per entity
- ✅ _pipeline_run_id populated

### Silver Layer (NOW WORKS WITH FIX!)
- ✅ Accounts deduplicated
- ✅ Transactions validated
- ✅ Invalid records in quarantine
- ✅ Files in `s3://bucket/silver/`

### Gold Layer (NOW WORKS WITH FIX!)
- ✅ Daily summaries computed
- ✅ Weekly summaries computed
- ✅ Files in `s3://bucket/gold/`

### Watermark
- ✅ Advances to 2024-01-06
- ✅ Prevents re-processing

---

## 🎓 Why This Works

| Component | Before Fix | After Fix |
|-----------|-----------|-----------|
| Bronze (Python) | ✅ Works | ✅ Works |
| Silver (dbt) | ❌ render() corrupts path | ✅ Path preserved |
| Gold (dbt) | ❌ render() corrupts path | ✅ Path preserved |
| Architecture | dbt models required | ✅ dbt models work |

---

## 🎉 Success Criteria

Pipeline is successful when:

1. ✅ All phases complete without errors
2. ✅ S3 has files in correct locations with correct paths
3. ✅ Watermark shows 2024-01-06
4. ✅ Run log shows all models with status=SUCCESS
5. ✅ No "Cannot open file" errors in logs

---

## 📝 Next Actions

1. **SSH into EC2** (use your EC2 IP from CloudFormation)
2. **Clone repo** with the patch from GitHub
3. **Build Docker image** using Dockerfile.patched
4. **Run pipeline** to test Bronze → Silver → Gold
5. **Verify S3 output** to confirm paths are correct
6. **Update S6_SESSION_LOG.md** with deployment results

---

**Status:** ✅ READY TO DEPLOY  
**Fix Location:** `Infra/dbt-duckdb-source/dbt/include/duckdb/macros/materializations/external.sql`  
**Patch Applied:** Line 2 - Removed `render()` call  
**Testing:** Local S3 path test confirmed bug, fix validated
