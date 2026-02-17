"""
API Sender module for posting business data to Sardine API.
Handles authentication, rate limiting, and response logging.
"""

import json
import time
import base64
import uuid
import os
import sys
from typing import List, Dict, Any, Tuple
from datetime import datetime
from multiprocessing import Pool, Manager

try:
    import requests
except ImportError:
    print("❌ Error: 'requests' library not found.")
    print("Please install it: pip install requests")
    sys.exit(1)

try:
    from dotenv import load_dotenv
except ImportError:
    print("❌ Error: 'python-dotenv' library not found.")
    print("Please install it: pip install python-dotenv")
    sys.exit(1)


class APIConfig:
    """API configuration loaded from environment variables."""

    def __init__(self, env_path: str = None):
        """
        Load API configuration from .env file.

        Args:
            env_path: Path to .env file (default: looks in parent directories)
        """
        if env_path:
            load_dotenv(env_path)
        else:
            load_dotenv()  # Looks for .env in current and parent directories

        self.client_id = os.getenv('SARDINE_CLIENT_ID')
        self.client_secret = os.getenv('SARDINE_CLIENT_SECRET')
        self.api_url = os.getenv('SARDINE_API_URL', 'https://api.sandbox.sardine.ai/v1/businesses')
        self.rate_limit_delay = float(os.getenv('RATE_LIMIT_DELAY', '0.5'))
        self.num_processes = int(os.getenv('NUM_PROCESSES', '4'))

        # Validate required variables
        if not self.client_id or not self.client_secret:
            raise ValueError(
                "Missing required environment variables. "
                "Please set SARDINE_CLIENT_ID and SARDINE_CLIENT_SECRET in .env file."
            )

    def get_basic_auth_header(self) -> str:
        """
        Generate Basic Auth header value.

        Returns:
            Base64 encoded 'clientID:clientSecret'
        """
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"


def _send_single_request(args: Tuple) -> Dict[str, Any]:
    """
    Worker function to send a single request (used by multiprocessing).
    Must be a module-level function for pickle serialization.

    Args:
        args: Tuple of (record, record_index, api_url, auth_header, rate_limit_delay)

    Returns:
        Response data dictionary
    """
    record, record_index, api_url, auth_header, rate_limit_delay = args

    # Generate request ID
    request_id = str(uuid.uuid4())

    # Prepare headers
    headers = {
        'Authorization': auth_header,
        'Content-Type': 'application/json',
        'X-Request-Id': request_id
    }

    result = {
        'record_index': record_index,
        'request_id': request_id,
        'timestamp': datetime.now().isoformat(),
        'request_body': record,
        'success': False
    }

    try:
        # Send POST request
        response = requests.post(
            api_url,
            headers=headers,
            json=record,
            timeout=30
        )

        # Parse response
        result['status_code'] = response.status_code
        result['response_body'] = response.json() if response.text else {}
        result['success'] = (200 <= response.status_code < 300)

        if not result['success']:
            result['error'] = f"HTTP {response.status_code}: {response.text[:500]}"

    except requests.exceptions.Timeout:
        result['status_code'] = None
        result['error'] = "Request timeout (30s)"

    except requests.exceptions.ConnectionError:
        result['status_code'] = None
        result['error'] = "Connection error - unable to reach API"

    except requests.exceptions.RequestException as e:
        result['status_code'] = None
        result['error'] = f"Request error: {str(e)}"

    except Exception as e:
        result['status_code'] = None
        result['error'] = f"Unexpected error: {str(e)}"

    # Rate limiting - sleep after each request
    if rate_limit_delay > 0:
        time.sleep(rate_limit_delay)

    return result


def extract_failed_indexes(failed_file_path: str) -> List[int]:
    """
    Extract record indexes from a failed responses JSON file.

    Args:
        failed_file_path: Path to failed_*.json file

    Returns:
        List of failed record indexes
    """
    with open(failed_file_path, 'r', encoding='utf-8') as f:
        failed_records = json.load(f)

    indexes = [record['record_index'] for record in failed_records]
    return sorted(indexes)

class APISender:
    """Sends business data to Sardine Business API."""

    def __init__(self, config: APIConfig, output_dir: str = '../output/responses'):
        """
        Initialize API sender.

        Args:
            config: APIConfig instance with credentials
            output_dir: Directory to save response files
        """
        self.config = config
        self.output_dir = output_dir

        # Create output directory
        os.makedirs(output_dir, exist_ok=True)

        # Storage for responses
        self.successful_responses = []
        self.failed_responses = []

    def send_batch(self, json_file_path: str, retry_indexes: List[int] = None) -> Tuple[int, int, float]:
        """
        Send all records from JSON file to API using parallel processing.
        Always tests first record before continuing with batch.

        Args:
            json_file_path: Path to JSON file with business records
            retry_indexes: Optional list of specific record indexes to retry (1-based)

        Returns:
            Tuple of (successful_count, failed_count, duration_seconds)
        """
        # Load JSON data
        with open(json_file_path, 'r', encoding='utf-8') as f:
            all_records = json.load(f)

        if not isinstance(all_records, list):
            raise ValueError("JSON file must contain an array of objects")

        # Filter records if retrying specific indexes
        if retry_indexes:
            print(f"\n🔁 RETRY MODE - Processing {len(retry_indexes)} specific records")
            print(f"   Indexes: {', '.join(map(str, retry_indexes))}\n")

            # Filter records (retry_indexes are 1-based, convert to 0-based)
            records = []
            actual_indexes = []
            for idx in retry_indexes:
                if 1 <= idx <= len(all_records):
                    records.append(all_records[idx - 1])
                    actual_indexes.append(idx)
                else:
                    print(f"⚠️  Warning: Index {idx} out of range (max: {len(all_records)}), skipping")

            if not records:
                print("❌ No valid indexes to retry")
                return 0, 0, 0.0

            # Use actual indexes for record numbering
            record_index_map = actual_indexes
        else:
            records = all_records
            record_index_map = list(range(1, len(records) + 1))

        if len(records) == 0:
            print("❌ No records to process")
            return 0, 0, 0.0

        total_records = len(records)

        # Test first record (always, unless only 1 record total)
        if total_records > 1:
            # Create test record with correct index
            test_record = records[0]
            test_index = record_index_map[0]

            success, test_result = self._test_single_record(test_record, test_index)

            # Store test result
            if success:
                self.successful_responses.append(test_result)
            else:
                self.failed_responses.append(test_result)

            # Ask user to continue
            user_input = input(f"Continue with remaining {total_records - 1} records? (yes/no): ").strip().lower()

            if user_input not in ['yes', 'y']:
                print("\n❌ Batch processing cancelled by user")
                self._save_responses()
                return len(self.successful_responses), len(self.failed_responses), 0.0

            # Process remaining records
            records_to_process = records[1:]
            indexes_to_process = record_index_map[1:]
        else:
            # Only 1 record - just process it
            print(f"\n📤 Processing single record...")
            records_to_process = records
            indexes_to_process = record_index_map

        # If no records left to process
        if len(records_to_process) == 0:
            print("\n✅ Single record test complete")
            self._save_responses()
            return len(self.successful_responses), len(self.failed_responses), 0.0

        # Process batch
        print(f"\n📤 Sending {len(records_to_process)} records to Sardine API...")
        print(f"   Endpoint: {self.config.api_url}")
        print(f"   Parallel workers: {self.config.num_processes}")
        print(f"   Rate limit: {self.config.rate_limit_delay}s per request\n")

        start_time = datetime.now()

        # Prepare arguments for parallel processing
        auth_header = self.config.get_basic_auth_header()
        args_list = [
            (record, idx, self.config.api_url, auth_header, self.config.rate_limit_delay)
            for record, idx in zip(records_to_process, indexes_to_process)
        ]

        # Execute requests in parallel with progress tracking
        print("   Processing requests...")
        results = []

        try:
            with Pool(processes=self.config.num_processes) as pool:
                # Use imap_unordered for progress tracking
                for i, result in enumerate(pool.imap_unordered(_send_single_request, args_list), 1):
                    results.append(result)

                    # Print progress every 10 records or at the end
                    if i % 10 == 0 or i == len(records_to_process):
                        success_so_far = sum(1 for r in results if r['success'])
                        print(
                            f"   [{i}/{len(records_to_process)}] Processed - {success_so_far} successful, {i - success_so_far} failed")

        except KeyboardInterrupt:
            print("\n\n⚠️  Upload interrupted by user")
            pool.terminate()
            pool.join()
            raise

        # Separate successful and failed responses
        for result in results:
            if result['success']:
                self.successful_responses.append(result)
            else:
                self.failed_responses.append(result)

        # Calculate duration and rates
        end_time = datetime.now()
        duration = end_time - start_time
        duration_seconds = duration.total_seconds()

        # Save responses
        self._save_responses()

        # Print timing statistics
        print(f"\n⏱️  Total time: {duration_seconds:.2f}s")
        if duration_seconds > 0:
            requests_per_min = (len(records_to_process) / duration_seconds) * 60
            successful_count = sum(1 for r in results if r['success'])
            successful_per_min = (successful_count / duration_seconds) * 60
            print(f"   Average rate: {requests_per_min:.1f} requests/min")
            print(f"   Successful rate: {successful_per_min:.1f} successful/min")

        return len(self.successful_responses), len(self.failed_responses), duration_seconds

    def test_first_record(self, records: List[Dict[str, Any]]) -> Tuple[bool, Dict[str, Any]]:
        """
        Test the first record before processing the batch.

        Args:
            records: List of business records

        Returns:
            Tuple of (success, result_data)
        """
        if not records:
            return False, {'error': 'No records to test'}

        return self._test_single_record(records[0], 1)

    def _test_single_record(self, record: Dict[str, Any], record_index: int) -> Tuple[bool, Dict[str, Any]]:
        """
        Test a single record.

        Args:
            record: Business record
            record_index: Index of the record

        Returns:
            Tuple of (success, result_data)
        """
        print("=" * 80)
        print(f"🧪 TESTING FIRST RECORD (Index {record_index})")
        print("=" * 80)
        print(f"Testing record {record_index}...\n")

        # Prepare arguments
        auth_header = self.config.get_basic_auth_header()
        args = (record, record_index, self.config.api_url, auth_header, 0)  # No delay for test

        # Send test request
        result = _send_single_request(args)

        # Display result
        if result['success']:
            print("✅ TEST SUCCESSFUL!")
            print("-" * 80)
            print(f"Status Code: {result['status_code']}")
            print(f"Request ID: {result['request_id']}")
            if result.get('response_body'):
                print(f"\nResponse Preview:")
                response_preview = json.dumps(result['response_body'], indent=2)
                # Show first 500 chars of response
                if len(response_preview) > 500:
                    print(response_preview[:500] + "...")
                else:
                    print(response_preview)
        else:
            print("❌ TEST FAILED!")
            print("-" * 80)
            print(f"Status Code: {result.get('status_code', 'N/A')}")
            print(f"Error: {result.get('error', 'Unknown error')}")

        print("=" * 80 + "\n")

        return result['success'], result

    def _send_single_record(self, record: Dict[str, Any], record_index: int) -> Dict[str, Any]:
        """
        Send a single record to the API.

        Args:
            record: Business record dictionary
            record_index: Index of record in batch

        Returns:
            Response data dictionary

        Raises:
            Exception: If request fails
        """
        # Generate request ID
        request_id = str(uuid.uuid4())

        # Prepare headers
        headers = {
            'Authorization': self.config.get_basic_auth_header(),
            'Content-Type': 'application/json',
            'X-Request-Id': request_id
        }

        # Send POST request
        try:
            response = requests.post(
                self.config.api_url,
                headers=headers,
                json=record,
                timeout=30
            )

            # Check for HTTP errors
            response.raise_for_status()

            # Parse response
            response_body = response.json() if response.text else {}

            # Build response data
            response_data = {
                'record_index': record_index,
                'request_id': request_id,
                'status_code': response.status_code,
                'request_body': record,
                'response_body': response_body,
                'timestamp': datetime.now().isoformat()
            }

            return response_data

        except requests.exceptions.HTTPError as e:
            # HTTP error (4xx, 5xx)
            error_msg = f"HTTP {response.status_code}"
            try:
                error_body = response.json()
                error_msg += f": {json.dumps(error_body)}"
            except:
                error_msg += f": {response.text}"
            raise Exception(error_msg)

        except requests.exceptions.Timeout:
            raise Exception("Request timeout (30s)")

        except requests.exceptions.ConnectionError:
            raise Exception("Connection error - unable to reach API")

        except requests.exceptions.RequestException as e:
            raise Exception(f"Request error: {str(e)}")

    def _save_responses(self) -> None:
        """Save response data to files."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save successful responses
        if self.successful_responses:
            success_file = os.path.join(self.output_dir, f"success_{timestamp}.json")
            with open(success_file, 'w', encoding='utf-8') as f:
                json.dump(self.successful_responses, f, indent=2, ensure_ascii=False)
            print(f"\n✓ Successful responses saved to: {success_file}")

        # Save failed responses
        if self.failed_responses:
            failed_file = os.path.join(self.output_dir, f"failed_{timestamp}.json")
            with open(failed_file, 'w', encoding='utf-8') as f:
                json.dump(self.failed_responses, f, indent=2, ensure_ascii=False)
            print(f"✓ Failed responses saved to: {failed_file}")

    def print_summary(self, success_count: int, failed_count: int, total_count: int) -> None:
        """Print summary of batch processing."""
        print("\n" + "=" * 80)
        if failed_count == 0:
            print("✅ BATCH PROCESSING COMPLETE - ALL SUCCESSFUL")
        else:
            print("⚠️  BATCH PROCESSING COMPLETE - SOME FAILURES")
        print("=" * 80)
        print(f"Total records: {total_count}")
        print(f"Successful:    {success_count} ({success_count / total_count * 100:.1f}%)")
        print(f"Failed:        {failed_count} ({failed_count / total_count * 100:.1f}%)")
        print("=" * 80 + "\n")

        # Show first few errors if any
        if failed_count > 0:
            print("First 5 Errors:")
            for result in self.failed_responses[:5]:
                print(f"  Row {result['record_index']}: {result.get('error', 'Unknown error')}")
            if failed_count > 5:
                print(f"  ... and {failed_count - 5} more errors")
            print()


def main():
    """Main execution for standalone usage."""

    print("\n📡 Sardine API Sender\n")

    # Parse arguments
    if len(sys.argv) < 2:
        print("Usage: python api_sender.py <json_file_path> [env_file_path] [options]")
        print("\nOptions:")
        print("  --retry-indexes INDEX [INDEX ...]  Retry specific record indexes")
        print("  --retry-failed FAILED_FILE         Retry all records from failed response file")
        print("\nExamples:")
        print("  python api_sender.py ../output/validated/sample_20250216.json")
        print("  python api_sender.py ../output/validated/sample_20250216.json ../.env")
        print("  python api_sender.py ../output/validated/sample_20250216.json --retry-indexes 5 12 47")
        print("  python api_sender.py ../output/validated/sample_20250216.json ../.env --retry-indexes 5 12 47")
        print(
            "  python api_sender.py ../output/validated/sample_20250216.json --retry-failed ../output/responses/failed_20250216.json")
        sys.exit(1)

    json_file_path = sys.argv[1]

    # Check if second argument is env file or a flag
    env_file_path = None
    start_idx = 2
    if len(sys.argv) > 2 and not sys.argv[2].startswith('--'):
        env_file_path = sys.argv[2]
        start_idx = 3

    # Parse retry options from remaining arguments
    retry_indexes = None
    remaining_args = sys.argv[start_idx:]

    if '--retry-indexes' in remaining_args:
        idx = remaining_args.index('--retry-indexes')
        # Collect all numbers after --retry-indexes until next flag or end
        retry_indexes = []
        for arg in remaining_args[idx + 1:]:
            if arg.startswith('--'):
                break
            try:
                retry_indexes.append(int(arg))
            except ValueError:
                break

        if not retry_indexes:
            print("❌ Error: --retry-indexes requires at least one index")
            sys.exit(1)

    elif '--retry-failed' in remaining_args:
        idx = remaining_args.index('--retry-failed')
        if idx + 1 >= len(remaining_args):
            print("❌ Error: --retry-failed requires a file path")
            sys.exit(1)

        failed_file = remaining_args[idx + 1]
        if not os.path.exists(failed_file):
            print(f"❌ Error: Failed file not found: {failed_file}")
            sys.exit(1)

        print(f"Loading failed indexes from: {failed_file}")
        retry_indexes = extract_failed_indexes(failed_file)
        print(f"Found {len(retry_indexes)} failed records to retry\n")

    # Validate JSON file exists
    if not os.path.exists(json_file_path):
        print(f"❌ Error: JSON file not found: {json_file_path}")
        sys.exit(1)

    try:
        # Load configuration
        print("Loading API configuration from .env file...")
        config = APIConfig(env_file_path)
        print("✓ Configuration loaded\n")

        # Initialize sender
        sender = APISender(config)

        # Send batch
        success_count, failed_count, duration = sender.send_batch(json_file_path, retry_indexes=retry_indexes)

        # Print summary
        sender.print_summary(success_count, failed_count, success_count+failed_count)

        # Exit with appropriate code
        if failed_count == 0:
            sys.exit(0)
        else:
            sys.exit(1)

    except ValueError as e:
        print(f"❌ Configuration error: {e}")
        print("\nPlease create a .env file with your credentials.")
        print("See .env.template for the required format.")
        sys.exit(1)

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()