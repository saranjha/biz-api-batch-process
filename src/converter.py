"""
Converter module for transforming CSV data to JSON format.
Handles flat-to-nested conversion, type conversion, and array parsing.
"""

import json
import re
from typing import Dict, List, Any, Union


class Converter:
    """Converts validated CSV data to nested JSON structure."""

    def __init__(self, rules_path: str):
        """
        Initialize converter with validation rules for type information.

        Args:
            rules_path: Path to validation_rules.json file
        """
        with open(rules_path, 'r') as f:
            self.rules = json.load(f)

    def csv_to_json(self, rows: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """
        Convert CSV rows to JSON array.

        Args:
            rows: List of row dictionaries (flat structure with dot notation keys)

        Returns:
            List of JSON objects (nested structure)
        """
        json_objects = []

        for row in rows:
            json_obj = self._convert_row(row)
            json_objects.append(json_obj)

        return json_objects

    def _convert_row(self, row: Dict[str, str]) -> Dict[str, Any]:
        """
        Convert a single CSV row to nested JSON object.

        Args:
            row: Dictionary with flat dot-notation keys

        Returns:
            Nested JSON object
        """
        # Start with empty result
        result = {}

        # Process each field in the row
        for field_name, value in row.items():
            value = value.strip()

            # Skip empty values (omit from JSON)
            if not value:
                continue

            # Get the rule for this field to determine type
            rule = self.rules.get(field_name, {})

            # Convert value based on type
            converted_value = self._convert_value(value, rule)

            # Build nested structure
            self._set_nested_value(result, field_name, converted_value)

        return result

    def _convert_value(self, value: str, rule: Dict[str, Any]) -> Any:
        """
        Convert string value to appropriate type based on rule.

        Args:
            value: String value from CSV
            rule: Validation rule containing type information

        Returns:
            Converted value (string, int, bool, or list)
        """
        field_type = rule.get('type', 'string')

        if field_type == 'integer':
            return int(value)

        elif field_type == 'boolean':
            return value.lower() == 'true'

        elif field_type == 'array':
            # Split by pipe or comma and return list
            return self._parse_array(value)

        else:  # string or enum
            return value

    def _parse_array(self, value: str) -> List[str]:
        """
        Parse array field (pipe or comma separated).

        Args:
            value: String with delimited values

        Returns:
            List of string values
        """
        # Split by pipe or comma
        if '|' in value:
            items = [item.strip() for item in value.split('|') if item.strip()]
        elif ',' in value:
            items = [item.strip() for item in value.split(',') if item.strip()]
        else:
            items = [value.strip()] if value.strip() else []

        return items

    def _set_nested_value(self, obj: Dict[str, Any], path: str, value: Any) -> None:
        """
        Set a value in a nested dictionary using dot notation path.

        Example:
            path = "business.address.city"
            Creates: {"business": {"address": {"city": value}}}

        Args:
            obj: Dictionary to modify
            path: Dot-notation path (e.g., "business.address.city")
            value: Value to set
        """
        keys = path.split('.')
        current = obj

        # Navigate/create nested structure
        for i, key in enumerate(keys[:-1]):
            if key not in current:
                current[key] = {}
            current = current[key]

        # Set the final value
        final_key = keys[-1]
        current[final_key] = value

    def save_json(self, json_data: List[Dict[str, Any]], output_path: str) -> None:
        """
        Save JSON data to file.

        Args:
            json_data: List of JSON objects
            output_path: Path to output file
        """
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)

    def json_to_string(self, json_data: List[Dict[str, Any]], indent: int = 2) -> str:
        """
        Convert JSON data to formatted string.

        Args:
            json_data: List of JSON objects
            indent: Indentation level for formatting

        Returns:
            Formatted JSON string
        """
        return json.dumps(json_data, indent=indent, ensure_ascii=False)