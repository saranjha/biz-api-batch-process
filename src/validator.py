"""
Validation module for CSV data against API schema rules.
Handles field validation, conditional requirements, and error/warning collection.
"""

import re
import json
from typing import Dict, List, Any, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum


class WarningType(Enum):
    """Types of validation warnings."""
    MISSING_RECOMMENDED = "missing_recommended"
    CONDITIONAL_MISSING = "conditional_missing"
    FORMAT_SUGGESTION = "format_suggestion"


class ErrorType(Enum):
    """Types of validation errors."""
    REQUIRED_FIELD = "required_field"
    PATTERN_MISMATCH = "pattern_mismatch"
    ENUM_VALIDATION = "enum_validation"
    TYPE_VALIDATION = "type_validation"
    LENGTH_VALIDATION = "length_validation"
    RANGE_VALIDATION = "range_validation"
    CONDITIONAL_REQUIRED = "conditional_required"


@dataclass
class ValidationError:
    """Represents a validation error."""
    row_number: int
    field: str
    error_type: ErrorType
    message: str


@dataclass
class ValidationWarning:
    """Represents a validation warning."""
    row_number: int
    field: str
    warning_type: WarningType
    message: str


@dataclass
class ValidationSummary:
    """Summary statistics for validation results."""
    total_rows: int
    valid_rows: int
    invalid_rows: int
    rows_with_warnings: int
    error_breakdown: Dict[str, int] = field(default_factory=dict)
    warning_breakdown: Dict[str, int] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """Complete validation results."""
    errors: List[ValidationError]
    warnings: List[ValidationWarning]
    summary: ValidationSummary
    header_errors: List[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """Returns True if no errors and no header errors."""
        return len(self.errors) == 0 and len(self.header_errors) == 0


class Validator:
    """Validates CSV data against schema rules."""

    def __init__(self, rules_path: str):
        """
        Initialize validator with validation rules.

        Args:
            rules_path: Path to validation_rules.json file
        """
        with open(rules_path, 'r') as f:
            self.rules = json.load(f)

    def _matches_pattern(self, field_name: str, pattern: str) -> bool:
        """
        Check if field_name matches a wildcard pattern.

        Args:
            field_name: Actual field name (e.g., 'business.businessTags.salesforceId')
            pattern: Pattern with wildcard (e.g., 'business.businessTags.*')

        Returns:
            True if field matches pattern
        """
        if '*' not in pattern:
            return field_name == pattern

        # Convert pattern to regex
        # Escape dots, replace * with one or more non-dot characters
        regex_pattern = pattern.replace('.', '\\.').replace('*', '[^.]+')
        regex_pattern = f'^{regex_pattern}$'

        return bool(re.match(regex_pattern, field_name))

    def _get_matching_rule(self, field_name: str) -> tuple:
        """
        Get validation rule for a field, including wildcard matches.

        Args:
            field_name: Field name to find rule for

        Returns:
            Tuple of (rule_key, rule_dict) or (None, None) if no match
        """
        # Try exact match first (faster)
        if field_name in self.rules:
            return field_name, self.rules[field_name]

        # Try wildcard patterns
        for rule_key, rule in self.rules.items():
            if '*' in rule_key and self._matches_pattern(field_name, rule_key):
                return rule_key, rule

        return None, None

    def _extract_tag_name(self, field_name: str, pattern: str) -> str | None:
        """
        Extract the wildcard part from a field name given a pattern.

        Args:
            field_name: e.g., 'business.businessTags.salesforceId'
            pattern: e.g., 'business.businessTags.*'

        Returns:
            The part matching the wildcard, e.g., 'salesforceId'
        """
        if '*' not in pattern:
            return None

        # Split both by dots
        pattern_parts = pattern.split('.')
        field_parts = field_name.split('.')

        # Find the index of the wildcard
        try:
            wildcard_index = pattern_parts.index('*')
            if wildcard_index < len(field_parts):
                return field_parts[wildcard_index]
        except (ValueError, IndexError):
            return None

        return None

    def validate_headers(self, csv_headers: List[str]) -> List[str]:
        """
        Validate CSV headers against expected fields.

        Args:
            csv_headers: List of column headers from CSV

        Returns:
            List of header error messages
        """
        header_errors = []
        csv_headers_set = set(csv_headers)

        # Check for required fields (non-wildcard only)
        for field_name, rule in self.rules.items():
            if '*' in field_name:  # Skip wildcard patterns
                continue
            if rule.get('required', False):
                if field_name not in csv_headers_set:
                    header_errors.append(f"Missing required header: '{field_name}'")

        # Check for unknown headers and validate wildcard patterns
        for header in csv_headers:
            if not header:  # Skip empty headers
                continue

            # Check if exact match exists
            if header in self.rules:
                continue

            # Check if it matches a wildcard pattern
            rule_key, rule = self._get_matching_rule(header)
            if rule:
                # Validate the tag name for businessTags fields
                if 'business.businessTags.' in header:
                    tag_name = self._extract_tag_name(header, rule_key)
                    if tag_name:
                        # Validate tag name is alphanumeric + underscores only
                        if not re.match(r'^[a-zA-Z0-9_]+$', tag_name):
                            header_errors.append(
                                f"Invalid tag name in '{header}': '{tag_name}' - "
                                "Tag names may only contain letters, numbers, and underscores"
                            )
                continue

            # Unknown header - try to suggest similar
            suggestions = self._find_similar_fields(header, set(self.rules.keys()))
            if suggestions:
                header_errors.append(
                    f"Unknown header: '{header}' (did you mean '{suggestions[0]}'?)"
                )
            else:
                header_errors.append(f"Unknown header: '{header}'")

        return header_errors

    def validate_rows(self, rows: List[Dict[str, str]]) -> ValidationResult:
        """
        Validate all rows of data.

        Args:
            rows: List of row dictionaries (field_name -> value)

        Returns:
            ValidationResult containing errors, warnings, and summary
        """
        all_errors = []
        all_warnings = []
        rows_with_errors = set()
        rows_with_warnings = set()

        for idx, row in enumerate(rows, start=1):
            row_errors, row_warnings = self._validate_row(idx, row)

            if row_errors:
                all_errors.extend(row_errors)
                rows_with_errors.add(idx)

            if row_warnings:
                all_warnings.extend(row_warnings)
                rows_with_warnings.add(idx)

        # Build summary
        summary = self._build_summary(
            total_rows=len(rows),
            rows_with_errors=rows_with_errors,
            rows_with_warnings=rows_with_warnings,
            errors=all_errors,
            warnings=all_warnings
        )

        return ValidationResult(
            errors=all_errors,
            warnings=all_warnings,
            summary=summary
        )

    def _validate_row(self, row_num: int, row: Dict[str, str]) -> Tuple[List[ValidationError], List[ValidationWarning]]:
        """
        Validate a single row.

        Args:
            row_num: Row number (1-indexed)
            row: Dictionary of field values

        Returns:
            Tuple of (errors, warnings) lists
        """
        errors = []
        warnings = []

        # Track which fields we've already validated
        validated_fields = set()

        # First pass: Validate fields with exact rules (non-wildcard)
        for field_name, rule in self.rules.items():
            if '*' in field_name:  # Skip wildcard patterns for now
                continue

            value = row.get(field_name, "").strip()
            validated_fields.add(field_name)

            # Check conditional requirements first
            if 'conditionalRequired' in rule:
                cond_errors, cond_warnings = self._check_conditional_required(
                    row_num, field_name, value, rule, row
                )
                errors.extend(cond_errors)
                warnings.extend(cond_warnings)

                # If conditionally required and missing, skip other validations
                if cond_errors:
                    continue

            # Check basic required fields
            if rule.get('required', False):
                if not value:
                    errors.append(ValidationError(
                        row_number=row_num,
                        field=field_name,
                        error_type=ErrorType.REQUIRED_FIELD,
                        message=f"{field_name}: Field is required"
                    ))
                    continue

            # Skip validation if field is empty and not required
            if not value:
                continue

            # Validate type and format
            field_errors = self._validate_field(row_num, field_name, value, rule)
            errors.extend(field_errors)

        # Second pass: Validate fields that match wildcard patterns
        for field_name, value in row.items():
            if field_name in validated_fields:  # Already validated
                continue

            # Try to find a matching wildcard rule
            rule_key, rule = self._get_matching_rule(field_name)
            if not rule:
                continue

            value = value.strip()

            # Skip empty values for optional fields
            if not value:
                continue

            # Validate the field
            field_errors = self._validate_field(row_num, field_name, value, rule)
            errors.extend(field_errors)

        return errors, warnings

    def _check_conditional_required(
            self,
            row_num: int,
            field_name: str,
            value: str,
            rule: Dict[str, Any],
            row: Dict[str, str]
    ) -> Tuple[List[ValidationError], List[ValidationWarning]]:
        """
        Check conditional requirement rules.

        Returns:
            Tuple of (errors, warnings)
        """
        errors = []
        warnings = []
        cond = rule['conditionalRequired']

        # Handle single field dependency (e.g., business.taxId depends on config.kybLevel)
        if 'dependsOn' in cond and isinstance(cond['dependsOn'], str):
            depends_on_field = cond['dependsOn']
            depends_on_value = row.get(depends_on_field, "").strip()
            when_not_in = cond.get('whenNotIn', [])

            # Check if field is required based on dependency
            if depends_on_value not in when_not_in:
                if not value:
                    message = cond.get('message', '').replace('{value}', depends_on_value)
                    errors.append(ValidationError(
                        row_number=row_num,
                        field=field_name,
                        error_type=ErrorType.CONDITIONAL_REQUIRED,
                        message=f"{field_name}: {message}"
                    ))

        # Handle multiple field dependencies (e.g., countryCode depends on any address field)
        elif 'dependsOn' in cond and isinstance(cond['dependsOn'], list):
            depends_on_fields = cond['dependsOn']
            when_any_present = cond.get('whenAnyPresent', False)

            if when_any_present:
                # Check if any of the dependent fields have values
                any_present = any(row.get(f, "").strip() for f in depends_on_fields)

                if any_present and not value:
                    message = cond.get('message', 'Required based on other fields')
                    errors.append(ValidationError(
                        row_number=row_num,
                        field=field_name,
                        error_type=ErrorType.CONDITIONAL_REQUIRED,
                        message=f"{field_name}: {message}"
                    ))

        return errors, warnings

    def _validate_field(self, row_num: int, field_name: str, value: str, rule: Dict[str, Any]) -> List[ValidationError]:
        """
        Validate a single field's value against its rule.

        Returns:
            List of validation errors
        """
        errors = []
        field_type = rule.get('type', 'string')

        # Validate based on type
        if field_type == 'string':
            errors.extend(self._validate_string(row_num, field_name, value, rule))

        elif field_type == 'integer':
            errors.extend(self._validate_integer(row_num, field_name, value, rule))

        elif field_type == 'boolean':
            errors.extend(self._validate_boolean(row_num, field_name, value, rule))

        elif field_type == 'enum':
            errors.extend(self._validate_enum(row_num, field_name, value, rule))

        elif field_type == 'array':
            errors.extend(self._validate_array(row_num, field_name, value, rule))

        return errors

    def _validate_string(self, row_num: int, field_name: str, value: str, rule: Dict[str, Any]) -> List[
        ValidationError]:
        """Validate string field."""
        errors = []

        # Check length constraints
        min_length = rule.get('minLength')
        max_length = rule.get('maxLength')

        if min_length and len(value) < min_length:
            errors.append(ValidationError(
                row_number=row_num,
                field=field_name,
                error_type=ErrorType.LENGTH_VALIDATION,
                message=f"{field_name}: Minimum length is {min_length} characters"
            ))

        if max_length and len(value) > max_length:
            errors.append(ValidationError(
                row_number=row_num,
                field=field_name,
                error_type=ErrorType.LENGTH_VALIDATION,
                message=f"{field_name}: Maximum length is {max_length} characters"
            ))

        # Check pattern
        pattern = rule.get('pattern')
        if pattern:
            if not re.match(pattern, value):
                errors.append(ValidationError(
                    row_number=row_num,
                    field=field_name,
                    error_type=ErrorType.PATTERN_MISMATCH,
                    message=f"{field_name}: {rule.get('description', 'Invalid format')}"
                ))

        return errors

    def _validate_integer(self, row_num: int, field_name: str, value: str, rule: Dict[str, Any]) -> List[
        ValidationError]:
        """Validate integer field."""
        errors = []

        # Check if value is a valid integer
        try:
            int_value = int(value)
        except ValueError:
            errors.append(ValidationError(
                row_number=row_num,
                field=field_name,
                error_type=ErrorType.TYPE_VALIDATION,
                message=f"{field_name}: Must be a valid integer"
            ))
            return errors

        # Check range
        min_val = rule.get('min')
        max_val = rule.get('max')

        if min_val is not None and int_value < min_val:
            errors.append(ValidationError(
                row_number=row_num,
                field=field_name,
                error_type=ErrorType.RANGE_VALIDATION,
                message=f"{field_name}: Minimum value is {min_val}"
            ))

        if max_val is not None and int_value > max_val:
            errors.append(ValidationError(
                row_number=row_num,
                field=field_name,
                error_type=ErrorType.RANGE_VALIDATION,
                message=f"{field_name}: Maximum value is {max_val}"
            ))

        return errors

    def _validate_boolean(self, row_num: int, field_name: str, value: str, rule: Dict[str, Any]) -> List[
        ValidationError]:
        """Validate boolean field."""
        errors = []

        if value.lower() not in ['true', 'false']:
            errors.append(ValidationError(
                row_number=row_num,
                field=field_name,
                error_type=ErrorType.TYPE_VALIDATION,
                message=f"{field_name}: Must be 'true' or 'false'"
            ))

        return errors

    def _validate_enum(self, row_num: int, field_name: str, value: str, rule: Dict[str, Any]) -> List[ValidationError]:
        """Validate enum field."""
        errors = []

        allowed_values = rule.get('values', [])
        if value not in allowed_values:
            errors.append(ValidationError(
                row_number=row_num,
                field=field_name,
                error_type=ErrorType.ENUM_VALIDATION,
                message=f"{field_name}: Must be one of: {', '.join(allowed_values)}"
            ))

        return errors

    def _validate_array(self, row_num: int, field_name: str, value: str, rule: Dict[str, Any]) -> List[ValidationError]:
        """Validate array field (pipe or comma separated)."""
        errors = []

        # Split by pipe or comma
        items = self._split_array_value(value)

        # Validate each item against pattern if specified
        item_pattern = rule.get('itemPattern')
        if item_pattern:
            for item in items:
                if not re.match(item_pattern, item):
                    errors.append(ValidationError(
                        row_number=row_num,
                        field=field_name,
                        error_type=ErrorType.PATTERN_MISMATCH,
                        message=f"{field_name}: Item '{item}' - {rule.get('description', 'Invalid format')}"
                    ))

        # Validate against enum values if specified
        enum_values = rule.get('enumValues')
        if enum_values:
            for item in items:
                if item not in enum_values:
                    errors.append(ValidationError(
                        row_number=row_num,
                        field=field_name,
                        error_type=ErrorType.ENUM_VALIDATION,
                        message=f"{field_name}: Item '{item}' must be one of: {', '.join(enum_values)}"
                    ))

        return errors

    def _split_array_value(self, value: str) -> List[str]:
        """Split array value by pipe or comma, trim whitespace."""
        if '|' in value:
            return [item.strip() for item in value.split('|') if item.strip()]
        elif ',' in value:
            return [item.strip() for item in value.split(',') if item.strip()]
        else:
            return [value.strip()] if value.strip() else []

    def _find_similar_fields(self, header: str, known_fields: Set[str], max_suggestions: int = 1) -> List[str]:
        """Find similar field names for typo suggestions (simple string distance)."""
        suggestions = []
        header_lower = header.lower()

        for field in known_fields:
            field_lower = field.lower()

            # Simple similarity: check if one contains the other or very close match
            if header_lower in field_lower or field_lower in header_lower:
                suggestions.append(field)
            elif self._levenshtein_distance(header_lower, field_lower) <= 2:
                suggestions.append(field)

        return suggestions[:max_suggestions]

    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """Calculate Levenshtein distance between two strings."""
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)

        if len(s2) == 0:
            return len(s1)

        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]

    def _build_summary(
            self,
            total_rows: int,
            rows_with_errors: Set[int],
            rows_with_warnings: Set[int],
            errors: List[ValidationError],
            warnings: List[ValidationWarning]
    ) -> ValidationSummary:
        """Build validation summary statistics."""

        # Count errors by type
        error_breakdown = {}
        for error in errors:
            key = f"{error.field}: {error.message.split(': ', 1)[1] if ': ' in error.message else error.message}"
            error_breakdown[key] = error_breakdown.get(key, 0) + 1

        # Count warnings by type
        warning_breakdown = {}
        for warning in warnings:
            key = f"{warning.field}: {warning.message.split(': ', 1)[1] if ': ' in warning.message else warning.message}"
            warning_breakdown[key] = warning_breakdown.get(key, 0) + 1

        return ValidationSummary(
            total_rows=total_rows,
            valid_rows=total_rows - len(rows_with_errors),
            invalid_rows=len(rows_with_errors),
            rows_with_warnings=len(rows_with_warnings),
            error_breakdown=error_breakdown,
            warning_breakdown=warning_breakdown
        )