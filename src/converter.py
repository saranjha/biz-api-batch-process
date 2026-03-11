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
            rules_path: Path to validation_rules_business.json file
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

    def csv_to_json_grouped(self, rows: List[Dict[str, str]], group_by_field: str) -> List[Dict[str, Any]]:
        """
        Convert CSV rows to JSON, grouping by a specific field.

        Used for entities endpoint where multiple CSV rows (entities) are grouped
        by businessId into a single JSON object with an entities array.

        Args:
            rows: List of CSV rows
            group_by_field: Field to group by (e.g., 'businessId')

        Returns:
            List of JSON objects (one per unique group value)
        """
        from collections import defaultdict

        # Group rows by the specified field
        grouped_rows = defaultdict(list)
        for row in rows:
            group_key = row.get(group_by_field, '').strip()
            if not group_key:
                continue  # Skip rows without a group key
            grouped_rows[group_key].append(row)
        child_prefix = self._detect_child_prefix(rows)

        # Convert each group to a JSON object
        json_objects = []
        for group_key, group_rows in grouped_rows.items():
            json_obj = {}
            json_obj[group_by_field] = group_key

            # Extract any non-child fields from the first row
            first_row = group_rows[0]
            for field_name, value in first_row.items():
                value = value.strip()
                if not value:
                    continue
                if field_name == group_by_field:
                    continue
                if child_prefix and field_name.startswith(child_prefix):
                    continue
                rule = self.rules.get(field_name, {})
                converted_value = self._convert_value(value, rule)
                self._set_nested_value(json_obj, field_name, converted_value)

            # Build child array from all rows in this group
            children = []
            for row in group_rows:
                child = self._convert_child_row(row, child_prefix)
                if child:
                    children.append(child)

            if children:
                array_key = self._child_array_key(child_prefix)
                json_obj[array_key] = children

            json_objects.append(json_obj)

        return json_objects

    def csv_to_json_locations(self, rows: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        json_objects = []
        for row in rows:
            json_obj = self._convert_location_row_flat(row)
            json_objects.append(json_obj)
        return json_objects

    def _convert_location_row_flat(self, row: Dict[str, str]) -> Dict[str, Any]:
        result = {}
        location_tags = self._extract_location_tags_flat(row)

        for field_name, value in row.items():
            value = value.strip()
            if not value:
                continue
            if field_name.startswith('locationTags.'):
                continue
            rule = self.rules.get(field_name, {})
            converted_value = self._convert_value(value, rule)
            self._set_nested_value(result, field_name, converted_value)

        if location_tags:
            result['locationTags'] = location_tags

        return result

    def _extract_location_tags_flat(self, row: Dict[str, str]) -> List[Dict[str, Any]]:
        location_tags = {}

        for field_name, value in row.items():
            if not field_name.startswith('locationTags.'):
                continue
            value = value.strip()
            if not value:
                continue

            parts = field_name.split('.')
            if len(parts) < 2:
                continue

            if parts[-1] == 'type':
                tag_name = '.'.join(parts[1:-1])
                if tag_name not in location_tags:
                    location_tags[tag_name] = {}
                location_tags[tag_name]['type'] = value
            else:
                tag_name = '.'.join(parts[1:])
                if tag_name not in location_tags:
                    location_tags[tag_name] = {}
                location_tags[tag_name]['value'] = value

        result = []
        for tag_name, tag_data in location_tags.items():
            if 'value' not in tag_data:
                continue

            tag_type = tag_data.get('type', 'string')
            tag_value = tag_data['value']

            if tag_type == 'int':
                try:
                    tag_value = int(tag_value)
                except ValueError:
                    pass
            elif tag_type == 'float':
                try:
                    tag_value = float(tag_value)
                except ValueError:
                    pass

            result.append({
                'name': tag_name,
                'value': tag_value,
                'type': tag_type
            })

        return result

    def _detect_child_prefix(self, rows: List[Dict[str, str]]) -> str | None:
        if not rows:
            return None
        for field_name in rows[0].keys():
            if field_name.startswith('entities.'):
                return 'entities.'
            if field_name.startswith('location.'):
                return 'location.'
        return None

    def _child_array_key(self, child_prefix: str | None) -> str:
        if child_prefix == 'entities.':
            return 'entities'
        if child_prefix == 'location.':
            return 'locations'
        return 'items'

    def _convert_child_row(self, row: Dict[str, str], child_prefix: str | None) -> Dict[str, Any]:
        if child_prefix == 'location.':
            return self._convert_location_row(row)
        else:
            return self._convert_entity_row(row, child_prefix)

    def _convert_entity_row(self, row: Dict[str, str], child_prefix: str | None) -> Dict[str, Any]:
        entity = {}
        for field_name, value in row.items():
            value = value.strip()
            if not field_name.startswith(child_prefix or 'entities.'):
                continue
            if not value:
                continue

            entity_field = field_name.replace(child_prefix or 'entities.', '', 1)
            rule = self.rules.get(field_name, {})
            if not rule:
                rule_pattern = f"entities.*.{entity_field}"
                rule = self.rules.get(rule_pattern, {})

            converted_value = self._convert_value(value, rule)
            self._set_nested_value(entity, entity_field, converted_value)

        return entity

    def _convert_location_row(self, row: Dict[str, str]) -> Dict[str, Any]:
        location = {}
        location_tags = self._extract_location_tags(row)

        for field_name, value in row.items():
            value = value.strip()
            if not field_name.startswith('location.'):
                continue
            if not value:
                continue
            if field_name.startswith('location.locationTags.'):
                continue

            location_field = field_name.replace('location.', '', 1)
            rule = self.rules.get(field_name, {})
            converted_value = self._convert_value(value, rule)
            self._set_nested_value(location, location_field, converted_value)

        if location_tags:
            location['locationTags'] = location_tags

        return location

    def _extract_location_tags(self, row: Dict[str, str]) -> List[Dict[str, Any]]:
        location_tags = {}

        for field_name, value in row.items():
            if not field_name.startswith('location.locationTags.'):
                continue
            value = value.strip()
            if not value:
                continue

            parts = field_name.split('.')
            if len(parts) < 3:
                continue

            if parts[-1] == 'type':
                tag_name = '.'.join(parts[2:-1])
                if tag_name not in location_tags:
                    location_tags[tag_name] = {}
                location_tags[tag_name]['type'] = value
            else:
                tag_name = '.'.join(parts[2:])
                if tag_name not in location_tags:
                    location_tags[tag_name] = {}
                location_tags[tag_name]['value'] = value

        result = []
        for tag_name, tag_data in location_tags.items():
            if 'value' not in tag_data:
                continue

            tag_type = tag_data.get('type', 'string')
            tag_value = tag_data['value']

            if tag_type == 'int':
                try:
                    tag_value = int(tag_value)
                except ValueError:
                    pass
            elif tag_type == 'float':
                try:
                    tag_value = float(tag_value)
                except ValueError:
                    pass

            result.append({
                'name': tag_name,
                'value': tag_value,
                'type': tag_type
            })

        return result
    
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

        # Extract business tags first (special handling)
        business_tags = self._extract_business_tags(row)

        # Process each field in the row
        for field_name, value in row.items():
            value = value.strip()

            # Skip empty values (omit from JSON)
            if not value:
                continue

            # Skip businessTags columns (already processed above)
            if field_name.startswith('business.businessTags.'):
                continue

            # Get the rule for this field to determine type
            rule = self.rules.get(field_name, {})

            # Convert value based on type
            converted_value = self._convert_value(value, rule)

            # Build nested structure
            self._set_nested_value(result, field_name, converted_value)

        # Add business tags if any exist
        if business_tags:
            if 'business' not in result:
                result['business'] = {}
            result['business']['businessTags'] = business_tags

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

    def _extract_business_tags(self, row: Dict[str, str]) -> List[Dict[str, Any]]:
        """
        Extract business tags from flattened columns and build array of tag objects.

        Args:
            row: Flat row dictionary with dot notation keys

        Returns:
            List of {name, value, type} objects
        """
        business_tags = {}

        # Find all businessTags columns
        for field_name, value in row.items():
            if not field_name.startswith('business.businessTags.'):
                continue

            value = value.strip()
            if not value:  # Skip empty values
                continue

            # Extract parts after 'business.businessTags.'
            parts = field_name.split('.')
            if len(parts) < 3:
                continue

            # Check if this is a .type column
            if parts[-1] == 'type':
                # This is a type column: business.businessTags.tagName.type
                tag_name = '.'.join(parts[2:-1])  # Everything between businessTags and type
                if tag_name not in business_tags:
                    business_tags[tag_name] = {}
                business_tags[tag_name]['type'] = value
            else:
                # This is a value column: business.businessTags.tagName
                tag_name = '.'.join(parts[2:])  # Everything after businessTags
                if tag_name not in business_tags:
                    business_tags[tag_name] = {}
                business_tags[tag_name]['value'] = value

        # Build array of tag objects
        result = []
        for tag_name, tag_data in business_tags.items():
            if 'value' not in tag_data:
                continue  # Skip if no value provided

            tag_type = tag_data.get('type', 'string')  # Default to 'string' if no type specified
            tag_value = tag_data['value']

            # Convert value based on type
            if tag_type == 'int' or tag_type == 'score':
                try:
                    tag_value = int(tag_value)
                except ValueError:
                    # Keep as string if conversion fails
                    pass
            elif tag_type == 'float':
                try:
                    tag_value = float(tag_value)
                except ValueError:
                    # Keep as string if conversion fails
                    pass
            # For 'string' and 'level', keep as string (no conversion needed)

            result.append({
                'name': tag_name,
                'value': tag_value,
                'type': tag_type
            })

        return result


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