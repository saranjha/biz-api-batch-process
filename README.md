# Sardine Business API Batch Tool

## Requirements
- Python 3.10+
- Git

## Setup

**1. Clone the repo:**
```bash
git clone https://github.com/saranjha/biz-api-batch-process.git
cd biz-api-batch-process
```

**2. Install dependencies:**
```bash
pip install requests python-dotenv
```

**3. Create a `.env` file in the root directory:**
```
SARDINE_CLIENT_ID=your_client_id
SARDINE_CLIENT_SECRET=your_client_secret
SARDINE_BUSINESS_API_URL=https://api.sandbox.sardine.ai/v1/businesses
SARDINE_ENTITIES_API_URL=https://api.sandbox.sardine.ai/v1/businesses/entities
SARDINE_LOCATIONS_API_URL=https://api.sandbox.sardine.ai/v1/businesses/locations
RATE_LIMIT_DELAY=1.2
NUM_PROCESSES=4
```

**4. Create input and output directories:**
```bash
mkdir -p input output/validated output/responses
```

**5. Place your CSV file in the `input/` directory and run:**
```bash
python main.py input/your_file.csv --endpoint business
```