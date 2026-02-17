# Quick Start Guide

## 🚀 Get Started in 3 Steps

### Step 1: Setup (One-time)

```bash
# Create directory structure
mkdir -p config input output/validated output/responses src

# Install dependencies
pip install requests python-dotenv

# Create .env file with your credentials in project root
cat > .env << EOF
SARDINE_CLIENT_ID=your-client-id
SARDINE_CLIENT_SECRET=your-client-secret
SARDINE_API_URL=https://api.sandbox.sardine.ai/v1/businesses
RATE_LIMIT_DELAY=0.5
NUM_PROCESSES=4
EOF
```

### Step 2: Place Your Files

```bash
# Copy the Python files to src/
src/
├── validator.py
├── converter.py
├── api_sender.py
└── main.py

# Copy validation rules to config/
config/
└── validation_rules.json

# Put your CSV in input/
input/
└── your_data.csv
```

### Step 3: Run

**Option A: Validate & Convert Only**
```bash
cd src
python main.py ../input/your_data.csv
```

**Option B: Full Pipeline (Validate + Convert + Send to API)**
```bash
cd src
python main.py ../input/your_data.csv --send-api
```

**Option C: Retry Failed Records**
```bash
# Retry specific indexes
python main.py ../input/your_data.csv --send-api --retry-indexes 5 12 47

# OR retry from failed file
python main.py ../input/your_data.csv --send-api --retry-failed ../output/responses/failed_20250216.json
```

## 📋 CSV Header Format

Your CSV must have these exact headers (adjust based on your data):

```csv
business.trackingId,business.name,business.taxId,business.website,business.address.street1,business.address.city,business.address.regionCode,business.address.postalCode,business.address.countryCode,business.phone,business.emailAddress,config.kybLevel
```

**Key Points:**
- Use dot notation: `business.address.city` (not `city`)
- Required: `business.name`, `config.kybLevel`
- Phone format: `+14151234567` (E.164)
- Multiple phones: `+1234|+5678` or `+1234,+5678`
- Website: Must have `https://` or `http://`

## ✅ What Gets Validated

- ✓ Required fields present
- ✓ Data types (string, integer, boolean)
- ✓ Formats (email, phone, URL, country codes)
- ✓ Conditional rules (taxId required when kybLevel ≠ disable)
- ✓ Length limits and ranges

## 📤 What Happens with --send-api

1. **Test-First Mode** - Tests first record, shows result, asks permission
2. **Parallel Processing** - Sends records using 4 workers (configurable)
3. **Continue-on-Error** - Processes all records, logs failures
4. **Smart Retry** - Retry only failed records by index

**Example Flow:**
```
🧪 TESTING FIRST RECORD
Testing record 1 of 100...
✅ TEST SUCCESSFUL!
Status Code: 200

Continue with remaining 99 records? (yes/no): yes

📤 Sending 99 records to Sardine API...
   Parallel workers: 4
   Rate limit: 0.5s per request

   Processing requests...
   [10/99] Processed - 10 successful, 0 failed
   [20/99] Processed - 20 successful, 0 failed
   ...
   [99/99] Processed - 96 successful, 3 failed

⏱️  Total time: 28.5s
   Average rate: 208.4 requests/min
   Successful rate: 202.1 successful/min

⚠️  BATCH PROCESSING COMPLETE - SOME FAILURES
Total records: 100
Successful:    97 (97.0%)
Failed:        3 (3.0%)

First 5 Errors:
  Row 23: HTTP 400: Invalid taxId format
  Row 45: Request timeout (30s)
  Row 78: HTTP 500: Internal server error
```

## 📁 Output Files

```
output/
├── validated/
│   └── your_data_20250216_143022.json    # Converted JSON
└── responses/
    ├── success_20250216_143500.json      # Successful API responses
    └── failed_20250216_143500.json       # Failed responses (for retry)
```

## 🔧 Common Issues

**"Missing required header: business.name"**
→ Check your CSV headers match exactly (case-sensitive)

**"Required when config.kybLevel is 'standard'"**
→ Add `business.taxId` or set `config.kybLevel` to `disable`

**"Phone numbers in E.164 format"**
→ Use `+14151234567` format (country code + number)

**"HTTP 401: Unauthorized"**
→ Check `.env` file has correct `SARDINE_CLIENT_ID` and `SARDINE_CLIENT_SECRET`

**"Too slow / rate limited"**
→ Adjust `.env`: Increase `NUM_PROCESSES` (try 6-8) or decrease `RATE_LIMIT_DELAY`

## 🔄 Retry Workflow

### Scenario: Batch with Failures

1. **Initial run:**
```bash
python main.py input.csv --send-api
# Result: 97 success, 3 failed (rows 23, 45, 78)
```

2. **Check failures:**
```bash
cat ../output/responses/failed_20250216_143500.json
# Shows which records failed and why
```

3. **Fix and retry:**
```bash
# Option A: Retry specific indexes
python main.py input.csv --send-api --retry-indexes 23 45 78

# Option B: Automatically retry all failed
python main.py input.csv --send-api --retry-failed ../output/responses/failed_20250216_143500.json
```

## ⚡ Performance Tips

### Default Settings
- **4 parallel workers**
- **0.5s delay per request**
- **~480 records/min**

### For Faster Processing
Edit `.env`:
```bash
NUM_PROCESSES=8          # More workers
RATE_LIMIT_DELAY=0.3     # Less delay (if API allows)
```
Result: **~800 records/min**

### For Safer Processing (Less API Load)
```bash
NUM_PROCESSES=2
RATE_LIMIT_DELAY=1.0
```
Result: **~120 records/min**

## 💡 Pro Tips

- **Test first** - Always run without `--send-api` to validate data before API calls
- **Start small** - Test with 10-20 records before running full batches
- **Use retry** - Don't re-run entire batches, just retry failed records
- **Check responses** - Review `success_*.json` files to verify API responses
- **Monitor rate limits** - If seeing 429 errors, increase `RATE_LIMIT_DELAY`
- **Progressive batching** - For 100k records, split into 10k chunks

## 📞 Need Help?

See full documentation in `README.md` or contact your Sardine account representative.

## 🎯 Quick Command Reference

```bash
# Validate only
python main.py input.csv

# Full pipeline
python main.py input.csv --send-api

# Retry specific records
python main.py input.csv --send-api --retry-indexes 5 12 47

# Retry from failed file
python main.py input.csv --send-api --retry-failed output/responses/failed_*.json

# Custom paths
python main.py input.csv --rules config/custom.json --output output/json

# Standalone API sender
python api_sender.py output/validated/file.json
python api_sender.py output/validated/file.json --retry-indexes 5 12
```

### Step 2: Place Your Files

```bash
# Copy the Python files to src/
src/
├── validator.py
├── converter.py
├── api_sender.py
└── main.py

# Copy validation rules to config/
config/
├── validation_rules.json
└── .env

# Put your CSV in input/
input/
└── your_data.csv
```

### Step 3: Run

**Option A: Validate & Convert Only**
```bash
cd src
python main.py ../input/your_data.csv
```

**Option B: Full Pipeline (Validate + Convert + Send to API)**
```bash
cd src
python main.py ../input/your_data.csv --send-api
```

## 📋 CSV Header Format

Your CSV must have these exact headers (adjust based on your data):

```csv
business.trackingId,business.name,business.taxId,business.website,business.address.street1,business.address.city,business.address.regionCode,business.address.postalCode,business.address.countryCode,business.phone,business.emailAddress,config.kybLevel
```

**Key Points:**
- Use dot notation: `business.address.city` (not `city`)
- Required: `business.name`, `config.kybLevel`
- Phone format: `+14151234567` (E.164)
- Multiple phones: `+1234|+5678` or `+1234,+5678`
- Website: Must have `https://` or `http://`

## ✅ What Gets Validated

- ✓ Required fields present
- ✓ Data types (string, integer, boolean)
- ✓ Formats (email, phone, URL, country codes)
- ✓ Conditional rules (taxId required when kybLevel ≠ disable)
- ✓ Length limits and ranges

## 📤 What Happens

1. **Validation** - Checks all data against rules
2. **Conversion** - Transforms flat CSV → nested JSON
3. **API Submission** (if `--send-api` flag used)
   - Sends one POST request per record
   - Waits 0.5s between requests
   - Stops on first error
   - Saves all responses

## 📁 Output Files

```
output/
├── validated/
│   └── your_data_20250216_143022.json    # Converted JSON
└── responses/
    ├── success_20250216_143500.json      # Successful API responses
    └── failed_20250216_143500.json       # Failed responses (if any)
```

## 🔧 Common Issues

**"Missing required header: business.name"**
→ Check your CSV headers match exactly (case-sensitive)

**"Required when config.kybLevel is 'standard'"**
→ Add `business.taxId` or set `config.kybLevel` to `disable`

**"Phone numbers in E.164 format"**
→ Use `+14151234567` format (country code + number)

**"HTTP 401: Unauthorized"**
→ Check `.env` file has correct `SARDINE_CLIENT_ID` and `SARDINE_CLIENT_SECRET`

## 💡 Pro Tips

- Test without `--send-api` first to validate data
- Check generated JSON before sending to API
- Use `disable` for `config.kybLevel` if you don't have taxId
- Start with small batches to test API integration
- Review `output/responses/` files after API submission

## 📞 Need Help?

See full documentation in `README.md`.