# CSV to JSON Converter & Sardine API Integration

A robust Python tool for validating CSV batch files, converting them to JSON, and submitting them to the Sardine API with parallel processing and intelligent retry mechanisms.

## Features

✅ **CSV Validation** - Comprehensive validation against API schema
- Required field checks
- Data type validation (string, integer, boolean, enum, array)
- Pattern matching (regex for emails, phones, URLs, etc.)
- Conditional requirements (e.g., taxId required when kybLevel ≠ disable)
- Length and range constraints

✅ **JSON Conversion** - Smart flat-to-nested transformation
- Dot notation to nested objects (`business.address.city` → `{"business": {"address": {"city": "..."}}}`)
- Type conversion (strings → integers/booleans)
- Array parsing (pipe or comma separated)
- Empty field omission

✅ **API Integration** - High-performance batch submission
- **Parallel processing** with configurable workers (default: 4)
- **Test-first mode** - Tests first payload before batch processing
- Basic authentication with Sardine API
- Automatic UUID generation for request tracking (X-Request-Id header)
- Rate limiting (configurable, default: 0.5s per request)
- **Continue-on-error** - Processes all records, logs failures
- **Intelligent retry** - Retry specific failed records by index

## Project Structure

```
csv-to-json-validator/
├── .env                           # API credentials (create from template)
├── config/
│   ├── .env.template              # Environment configuration template
│   └── validation_rules.json     # API schema validation rules
├── input/
│   └── *.csv                      # Input CSV files
├── output/
│   ├── validated/                 # Generated JSON files
│   └── responses/                 # API response logs
│       ├── success_*.json         # Successful submissions
│       └── failed_*.json          # Failed submissions (for retry)
├── src/
│   ├── validator.py               # Validation logic
│   ├── converter.py               # CSV to JSON conversion
│   ├── api_sender.py              # API submission with parallel processing
│   └── main.py                    # Main orchestration
├── requirements.txt
├── README.md
└── QUICK_START.md
```

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure API Credentials

Create a `.env` file in the project root:

```bash
cp config/.env.template .env
```

Edit `.env` with your Sardine credentials:

```bash
SARDINE_CLIENT_ID=your-client-id-here
SARDINE_CLIENT_SECRET=your-client-secret-here
SARDINE_API_URL=https://api.sandbox.sardine.ai/v1/businesses
RATE_LIMIT_DELAY=0.5
NUM_PROCESSES=4
```

### 3. Prepare CSV File

Your CSV must use dot notation headers matching the API schema:

```csv
business.trackingId,business.name,business.taxId,business.website,business.address.street1,business.address.city,business.address.regionCode,business.address.postalCode,business.address.countryCode,business.phone,business.emailAddress,config.kybLevel
track-001,Acme Corp,123456789,https://acme.com,123 Main St,San Francisco,CA,94117,US,+14151234567,contact@acme.com,standard
```

## Usage

### Option 1: Validate & Convert Only

```bash
cd src
python main.py ../input/sample.csv
```

**Output:**
- Validates CSV data
- Generates JSON file in `output/validated/`
- No API submission

### Option 2: Full Pipeline (Validate + Convert + Send to API)

```bash
cd src
python main.py ../input/sample.csv --send-api
```

**Output:**
- Validates CSV data
- Generates JSON file
- **Tests first record** and prompts for confirmation
- Sends all records to Sardine API (parallel processing)
- Saves responses in `output/responses/`

### Option 3: Retry Failed Records

After a batch run with failures:

```bash
# Retry specific indexes
python main.py ../input/sample.csv --send-api --retry-indexes 5 12 47

# OR retry all failed records from a failed response file
python main.py ../input/sample.csv --send-api --retry-failed ../output/responses/failed_20250216_143522.json
```

### Option 4: Standalone API Sender

Send an existing JSON file:

```bash
cd src
python api_sender.py ../output/validated/sample_20250216_143022.json

# With retry
python api_sender.py ../output/validated/sample_20250216_143022.json --retry-indexes 5 12 47
python api_sender.py ../output/validated/sample_20250216_143022.json --retry-failed ../output/responses/failed_20250216.json
```

## Command-Line Options

```bash
python main.py <csv_file> [OPTIONS]

Required:
  csv_file              Path to input CSV file

Optional:
  --rules PATH          Path to validation rules (default: ../config/validation_rules.json)
  --output PATH         Output directory for JSON (default: ../output/validated)
  --send-api            Send data to API after conversion
  --env-file PATH       Path to .env file (default: auto-detect)
  --retry-indexes N...  Retry specific record indexes (e.g., 5 12 47)
  --retry-failed PATH   Retry all records from failed response file
  -h, --help            Show help message
```

## CSV Header Requirements

### Required Fields
- `business.name` - Business name (max 128 chars)
- `config.kybLevel` - One of: `international`, `standard`, `tin-only`, `disable`

### Conditional Requirements
- `business.taxId` - Required when `config.kybLevel` ≠ `disable` (9-digit EIN)
- `business.address.countryCode` - Required when any address field is present (2-letter ISO code)

### Common Fields
- `business.trackingId` - Optional tracking identifier
- `business.website` - Must start with `http://` or `https://`
- `business.address.*` - street1, street2, city, regionCode, postalCode, countryCode
- `business.phone` - E.164 format (e.g., `+14151234567`). Multiple: `+1234|+5678` or `+1234,+5678`
- `business.emailAddress` - Valid email address

See `config/validation_rules.json` for complete field specifications.

## Performance

### Speed Comparison

| Configuration | Records/Min | Use Case |
|--------------|-------------|----------|
| Sequential (old) | ~120/hour | Testing, small batches |
| **Parallel (4 workers)** | **~480/min** | Production batches |
| Parallel (8 workers) | ~800/min | High-volume processing |

### Tuning Performance

Edit `.env` to adjust:

```bash
# Number of parallel workers (default: 4)
NUM_PROCESSES=8

# Delay between requests per worker (default: 0.5s)
RATE_LIMIT_DELAY=0.3
```

**Recommendation:** Start with defaults, increase gradually if no rate limit errors occur.

## Output Files

### JSON Output
`output/validated/{filename}_{timestamp}.json`

```json
[
  {
    "business": {
      "name": "Acme Corp",
      "taxId": "123456789",
      "address": {
        "street1": "123 Main St",
        "city": "San Francisco",
        "regionCode": "CA",
        "postalCode": "94117",
        "countryCode": "US"
      },
      "phone": ["+14151234567"],
      "emailAddress": "contact@acme.com"
    },
    "config": {
      "kybLevel": "standard"
    }
  }
]
```

### API Response Files

**Success:** `output/responses/success_{timestamp}.json`
```json
[
  {
    "record_index": 1,
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "status_code": 200,
    "request_body": {...},
    "response_body": {
      "sardineID": "biz_123456",
      "trackingID": "track-001"
    },
    "timestamp": "2025-02-16T14:35:22.123456"
  }
]
```

**Failed:** `output/responses/failed_{timestamp}.json`
```json
[
  {
    "record_index": 23,
    "request_id": "uuid-123",
    "status_code": 400,
    "error": "HTTP 400: Invalid taxId format",
    "request_body": {...},
    "timestamp": "2025-02-16T14:35:45.123456"
  }
]
```

## Error Handling

### Validation Errors
If validation fails, the tool will:
- Display all errors grouped by type
- Show example errors with row numbers
- Exit without generating JSON

### API Errors
The tool uses a **continue-on-error** strategy:
- Processes all records even if some fail
- Logs all failures with details
- Saves successful responses
- Enables targeted retry of failed records

## Workflow Examples

### Example 1: First-Time Batch Upload

```bash
cd src
python main.py ../input/merchants.csv --send-api
```

**Output:**
```
🧪 TESTING FIRST RECORD
Testing record 1 of 100...
✅ TEST SUCCESSFUL!

Continue with remaining 99 records? (yes/no): yes

📤 Sending 99 records to Sardine API...
   Parallel workers: 4
   [10/99] Processed - 10 successful, 0 failed
   [20/99] Processed - 19 successful, 1 failed
   ...
   [99/99] Processed - 96 successful, 3 failed

⚠️  BATCH PROCESSING COMPLETE - SOME FAILURES
Total records: 100
Successful:    97 (97.0%)
Failed:        3 (3.0%)

First 5 Errors:
  Row 23: HTTP 400: Invalid taxId format
  Row 45: Request timeout (30s)
  Row 78: HTTP 500: Internal server error
```

### Example 2: Retry Failed Records

```bash
# Check which records failed
cat ../output/responses/failed_20250216_143522.json

# Fix data issues in CSV, then retry just those records
python main.py ../input/merchants.csv --send-api --retry-indexes 23 45 78
```

**Output:**
```
🔁 RETRY MODE - Processing 3 specific records
   Indexes: 23, 45, 78

🧪 TESTING FIRST RECORD (Index 23)
✅ TEST SUCCESSFUL!

Continue with remaining 2 records? (yes/no): yes

📤 Sending 2 records to Sardine API...
   [2/2] Processed - 2 successful, 0 failed

✅ RETRY COMPLETE - ALL SUCCESSFUL
```

### Example 3: Automatic Retry from Failed File

```bash
# Retry all failed records automatically
python main.py ../input/merchants.csv --send-api --retry-failed ../output/responses/failed_20250216_143522.json
```

## Troubleshooting

### "Missing required environment variables"
- Ensure `.env` file exists in project root
- Check that `SARDINE_CLIENT_ID` and `SARDINE_CLIENT_SECRET` are set

### "Unknown header: 'phone'"
- CSV headers must match validation rules exactly
- Use `business.phone` not `phone`
- Use `business.emailAddress` not `email`

### "Required when config.kybLevel is 'standard'"
- `business.taxId` is required unless `config.kybLevel` is `disable`
- Add taxId or change kybLevel to `disable`

### "HTTP 401: Unauthorized"
- Check your API credentials in `.env`
- Verify clientID and clientSecret are correct

### Rate Limiting / Timeouts
- Adjust `RATE_LIMIT_DELAY` in `.env` (default: 0.5 seconds)
- Reduce `NUM_PROCESSES` if hitting API rate limits
- Check network connectivity to `api.sandbox.sardine.ai`

### Slow Performance
- Increase `NUM_PROCESSES` in `.env` (try 6 or 8)
- Decrease `RATE_LIMIT_DELAY` if API allows
- Use `--retry-indexes` for targeted fixes instead of full re-runs

## Development

### Adding New Validation Rules

Edit `config/validation_rules.json`:

```json
{
  "business.newField": {
    "required": false,
    "type": "string",
    "pattern": "^[A-Z]{2}$",
    "description": "2-letter code",
    "conditionalRequired": {
      "dependsOn": "business.otherField",
      "whenNotIn": ["value1", "value2"]
    }
  }
}
```

Supported types: `string`, `integer`, `boolean`, `enum`, `array`

### Testing

Test with sample data:

```bash
cd src
python main.py ../input/sample.csv
```

Validate without API submission first, then add `--send-api` flag.

## License

This project is proprietary. All rights reserved.

## Support

For issues or questions, contact your Sardine account representative.

```
csv-to-json-validator/
├── config/
│   ├── validation_rules.json     # API schema validation rules
│   └── .env                       # API credentials (create from template)
├── input/
│   └── *.csv                      # Input CSV files
├── output/
│   ├── validated/                 # Generated JSON files
│   └── responses/                 # API response logs
├── src/
│   ├── validator.py               # Validation logic
│   ├── converter.py               # CSV to JSON conversion
│   ├── api_sender.py              # API submission
│   └── main.py                    # Main orchestration
├── requirements.txt
└── README.md
```

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure API Credentials

Create a `.env` file in the `config/` directory:

```bash
cp config/.env.template config/.env
```

Edit `config/.env` with your Sardine credentials:

```bash
SARDINE_CLIENT_ID=your-client-id-here
SARDINE_CLIENT_SECRET=your-client-secret-here
SARDINE_API_URL=https://api.sandbox.sardine.ai/v1/businesses
RATE_LIMIT_DELAY=0.5
```

### 3. Prepare CSV File

Your CSV must use dot notation headers matching the API schema:

```csv
business.trackingId,business.name,business.taxId,business.website,business.address.street1,business.address.city,business.address.regionCode,business.address.postalCode,business.address.countryCode,business.phone,business.emailAddress,config.kybLevel
track-001,Acme Corp,123456789,https://acme.com,123 Main St,San Francisco,CA,94117,US,+14151234567,contact@acme.com,standard
```

## Usage

### Option 1: Validate & Convert Only

```bash
cd src
python main.py ../input/sample.csv
```

**Output:**
- Validates CSV data
- Generates JSON file in `output/validated/`
- No API submission

### Option 2: Full Pipeline (Validate + Convert + Send to API)

```bash
cd src
python main.py ../input/sample.csv --send-api
```

**Output:**
- Validates CSV data
- Generates JSON file
- Sends each record to Sardine API
- Saves responses in `output/responses/`

### Option 3: Send Existing JSON to API

```bash
cd src
python api_sender.py ../output/validated/sample_20250216_143022.json
```

**Output:**
- Reads existing JSON file
- Sends to API
- Saves responses

## Command-Line Options

```bash
python main.py <csv_file> [OPTIONS]

Required:
  csv_file              Path to input CSV file

Optional:
  --rules PATH          Path to validation rules (default: ../config/validation_rules.json)
  --output PATH         Output directory for JSON (default: ../output/validated)
  --send-api            Send data to API after conversion
  --env-file PATH       Path to .env file (default: auto-detect)
  -h, --help            Show help message
```

## CSV Header Requirements

### Required Fields
- `business.name` - Business name (max 128 chars)
- `config.kybLevel` - One of: `international`, `standard`, `tin-only`, `disable`

### Conditional Requirements
- `business.taxId` - Required when `config.kybLevel` ≠ `disable` (9-digit EIN)
- `business.address.countryCode` - Required when any address field is present (2-letter ISO code)

### Common Fields
- `business.trackingId` - Optional tracking identifier
- `business.website` - Must start with `http://` or `https://`
- `business.address.*` - street1, street2, city, regionCode, postalCode, countryCode
- `business.phone` - E.164 format (e.g., `+14151234567`). Multiple: `+1234|+5678` or `+1234,+5678`
- `business.emailAddress` - Valid email address

See `config/validation_rules.json` for complete field specifications.

## Output Files

### JSON Output
`output/validated/{filename}_{timestamp}.json`

```json
[
  {
    "business": {
      "name": "Acme Corp",
      "taxId": "123456789",
      "address": {
        "street1": "123 Main St",
        "city": "San Francisco",
        "regionCode": "CA",
        "postalCode": "94117",
        "countryCode": "US"
      },
      "phone": ["+14151234567"],
      "emailAddress": "contact@acme.com"
    },
    "config": {
      "kybLevel": "standard"
    }
  }
]
```

### API Response Files
- `output/responses/success_{timestamp}.json` - Successful submissions
- `output/responses/failed_{timestamp}.json` - Failed submissions (if any)

## Error Handling

### Validation Errors
If validation fails, the tool will:
- Display all errors grouped by type
- Show example errors with row numbers
- Exit without generating JSON

### API Errors
If any API request fails, the tool will:
- **Stop immediately** (fail-fast behavior)
- Log the error with details (record index, HTTP status, error message)
- Save all successful responses up to that point
- Exit with error code 1

## Examples

### Example 1: Basic Usage
```bash
cd src
python main.py ../input/merchants.csv
```

### Example 2: Full Pipeline with Custom Paths
```bash
cd src
python main.py ../input/batch_001.csv \
  --rules ../config/custom_rules.json \
  --output ../output/batch_001 \
  --send-api
```

### Example 3: Standalone API Sender
```bash
cd src
python api_sender.py ../output/validated/merchants_20250216_143022.json
```

## Troubleshooting

### "Missing required environment variables"
- Ensure `.env` file exists in `config/` directory
- Check that `SARDINE_CLIENT_ID` and `SARDINE_CLIENT_SECRET` are set

### "Unknown header: 'phone'"
- CSV headers must match validation rules exactly
- Use `business.phone` not `phone`
- Use `business.emailAddress` not `email`

### "Required when config.kybLevel is 'standard'"
- `business.taxId` is required unless `config.kybLevel` is `disable`
- Add taxId or change kybLevel to `disable`

### "HTTP 401: Unauthorized"
- Check your API credentials in `.env`
- Verify clientID and clientSecret are correct

### Rate Limiting / Timeouts
- Adjust `RATE_LIMIT_DELAY` in `.env` (default: 0.5 seconds)
- Check network connectivity to `api.sandbox.sardine.ai`

## Development

### Adding New Validation Rules

Edit `config/validation_rules.json`:

```json
{
  "business.newField": {
    "required": false,
    "type": "string",
    "pattern": "^[A-Z]{2}$",
    "description": "2-letter code",
    "conditionalRequired": {
      "dependsOn": "business.otherField",
      "whenNotIn": ["value1", "value2"]
    }
  }
}
```

Supported types: `string`, `integer`, `boolean`, `enum`, `array`

### Testing

Test with sample data:

```bash
cd src
python main.py ../input/sample.csv
```

Validate without API submission first, then add `--send-api` flag.

## Support

For issues or questions, contact your Sardine account representative.