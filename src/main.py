"""
Main entry point for CSV validation and JSON conversion.
Handles CSV reading, validation, and output generation.
"""

import csv
import sys
import os
from pathlib import Path
from validator import Validator
import argparse
from datetime import datetime
from converter import Converter
from api_sender import APIConfig, APISender, extract_failed_indexes


def load_csv(file_path: str):
    """
    Load CSV file and return headers and rows.

    Args:
        file_path: Path to CSV file

    Returns:
        Tuple of (headers list, rows list of dicts)
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        headers = list(reader.fieldnames)
        rows = list(reader)
    return headers, rows


def print_validation_results(result, header_errors):
    """
    Print formatted validation results to console.

    Args:
        result: ValidationResult object
        header_errors: List of header error messages
    """
    print("\n" + "=" * 80)

    # Print header errors
    if header_errors:
        print("❌ HEADER ERRORS:")
        print("-" * 80)
        for error in header_errors:
            print(f"  ✗ {error}")
        print()

    # Print validation results
    if result.is_valid and not header_errors:
        print("✅ VALIDATION PASSED!")
        print("-" * 80)
        print(f"Total rows: {result.summary.total_rows}")
        print(f"Valid rows: {result.summary.valid_rows}")

        if result.warnings:
            print(f"\n⚠️  Rows with warnings: {result.summary.rows_with_warnings}")
            print("\nWarning Summary:")
            for warning_msg, count in result.summary.warning_breakdown.items():
                print(f"  • {count} rows: {warning_msg}")
            print("\n✅ No errors found. Ready for JSON conversion.")
    else:
        print("❌ VALIDATION FAILED!")
        print("-" * 80)
        print(f"Total rows: {result.summary.total_rows}")
        print(f"Valid rows: {result.summary.valid_rows}")
        print(f"Invalid rows: {result.summary.invalid_rows}")

        if result.summary.error_breakdown:
            print("\nError Summary:")
            for error_msg, count in result.summary.error_breakdown.items():
                print(f"  • {count} rows: {error_msg}")

            # Show first 5 detailed error examples
            print("\nFirst 5 Error Examples:")
            for error in result.errors[:5]:
                print(f"  Row {error.row_number}: {error.message}")

            if len(result.errors) > 5:
                print(f"  ... and {len(result.errors) - 5} more errors")

        print("\n❌ Please fix errors before JSON conversion can proceed.")

    print("=" * 80 + "\n")


def generate_output_filename(csv_file_path: str) -> str:
    """
    Generate output filename based on input CSV filename and timestamp.

    Args:
        csv_file_path: Path to input CSV file

    Returns:
        Output filename for JSON file
    """
    # Get base filename without extension
    csv_filename = Path(csv_file_path).stem

    # Generate timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Create output filename
    output_filename = f"{csv_filename}_{timestamp}.json"

    return output_filename


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description='CSV to JSON Converter with optional API submission',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate and convert only
  python main.py input.csv

  # Validate, convert, and send to API
  python main.py input.csv --send-api

  # Retry specific failed records
  python main.py input.csv --send-api --retry-indexes 5 12 47

  # Retry all failed records from a failed response file
  python main.py input.csv --send-api --retry-failed output/responses/failed_20250216.json

  # Use custom paths
  python main.py input.csv --rules config/rules.json --output output/json --send-api
        """
    )

    parser.add_argument('csv_file', help='Path to input CSV file')
    parser.add_argument('--rules', default='../config/validation_rules.json',
                        help='Path to validation rules file (default: ../config/validation_rules.json)')
    parser.add_argument('--output', default='../output/validated',
                        help='Output directory for JSON files (default: ../output/validated)')
    parser.add_argument('--send-api', action='store_true',
                        help='Send data to API after conversion')
    parser.add_argument('--env-file', default=None,
                        help='Path to .env file (default: auto-detect)')
    parser.add_argument('--retry-indexes', type=int, nargs='+',
                        help='Retry specific record indexes (e.g., --retry-indexes 5 12 47)')
    parser.add_argument('--retry-failed', type=str,
                        help='Path to failed_*.json file to retry all failed records')

    return parser.parse_args()


def main():
    """Main execution function."""

    print("\n🔍 CSV to JSON Converter & API Sender\n")

    # Parse arguments
    args = parse_arguments()

    csv_file_path = args.csv_file
    rules_file_path = args.rules
    output_dir = args.output
    send_to_api = args.send_api
    env_file_path = args.env_file

    # Validate file paths
    if not os.path.exists(csv_file_path):
        print(f"❌ Error: CSV file not found: {csv_file_path}")
        sys.exit(1)

    if not os.path.exists(rules_file_path):
        print(f"❌ Error: Rules file not found: {rules_file_path}")
        sys.exit(1)

    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    json_output_path = None

    try:
        # Step 1: Load validation rules
        print(f"📋 Loading validation rules from: {rules_file_path}")
        validator = Validator(rules_file_path)
        print("   ✓ Validation rules loaded\n")

        # Step 2: Load CSV file
        print(f"📂 Loading CSV file: {csv_file_path}")
        headers, rows = load_csv(csv_file_path)
        print(f"   ✓ CSV loaded: {len(rows)} rows, {len(headers)} columns\n")

        # Step 3: Validate headers
        print("🔍 Validating CSV headers...")
        header_errors = validator.validate_headers(headers)

        if header_errors:
            print(f"   ✗ Found {len(header_errors)} header error(s)")
        else:
            print("   ✓ Headers valid")
        print()

        # Step 4: Validate rows
        print("🔍 Validating data rows...")
        result = validator.validate_rows(rows)
        print("   ✓ Validation complete\n")

        # Step 5: Display validation results
        print_validation_results(result, header_errors)

        # Step 6: If validation failed, stop here
        if not result.is_valid or header_errors:
            sys.exit(1)

        # Step 7: Convert to JSON
        print("🔄 Converting to JSON...\n")

        # Initialize converter
        converter = Converter(rules_file_path)

        # Convert rows to JSON
        json_data = converter.csv_to_json(rows)
        print(f"   ✓ Converted {len(json_data)} records to JSON\n")

        # Generate output filename
        output_filename = generate_output_filename(csv_file_path)
        json_output_path = os.path.join(output_dir, output_filename)

        # Save JSON to file
        print(f"💾 Saving JSON to: {json_output_path}")
        converter.save_json(json_data, json_output_path)
        print(f"   ✓ JSON file saved successfully\n")

        # Print conversion summary
        print("=" * 80)
        print("✅ CONVERSION SUCCESSFUL!")
        print("=" * 80)
        print(f"Input:  {csv_file_path}")
        print(f"Output: {json_output_path}")
        print(f"Records: {len(json_data)}")
        print("=" * 80 + "\n")

        # Preview first record
        if json_data:
            print("Preview of first record:")
            print("-" * 80)
            print(converter.json_to_string([json_data[0]], indent=2))
            print("-" * 80 + "\n")

        # Step 8: Send to API if requested
        if send_to_api:
            print("=" * 80)
            print("🚀 SENDING TO API")
            print("=" * 80 + "\n")

            try:
                # Load API configuration
                print("Loading API configuration from .env file...")
                api_config = APIConfig(env_file_path)
                print("✓ API configuration loaded\n")

                # Initialize API sender
                api_sender = APISender(api_config)

                # Handle retry options
                retry_indexes = None
                if args.retry_indexes:
                    retry_indexes = args.retry_indexes
                    print(f"ℹ️  Retry mode: Processing {len(retry_indexes)} specific indexes\n")
                elif args.retry_failed:
                    if not os.path.exists(args.retry_failed):
                        print(f"❌ Error: Failed file not found: {args.retry_failed}")
                        sys.exit(1)

                    print(f"Loading failed indexes from: {args.retry_failed}")
                    retry_indexes = extract_failed_indexes(args.retry_failed)
                    print(f"Found {len(retry_indexes)} failed records to retry\n")

                # Send batch
                success_count, failed_count, duration = api_sender.send_batch(
                    json_output_path,
                    retry_indexes=retry_indexes
                )

                # Print summary
                api_sender.print_summary(success_count, failed_count, success_count + failed_count)

                # Exit based on API results
                if failed_count == 0:
                    print("✅ All records successfully sent to API!\n")
                    sys.exit(0)
                else:
                    print("⚠️  Some records failed to send. Check error logs.\n")
                    sys.exit(1)

            except ValueError as e:
                print(f"❌ API Configuration error: {e}")
                print("\nPlease create a .env file with your Sardine API credentials.")
                print("See .env.template for the required format.\n")
                sys.exit(1)

            except Exception as e:
                print(f"❌ API error: {e}\n")
                sys.exit(1)
        else:
            # No API submission requested
            print("ℹ️  To send data to API, run with --send-api flag\n")
            sys.exit(0)

    except FileNotFoundError as e:
        print(f"❌ File not found: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()