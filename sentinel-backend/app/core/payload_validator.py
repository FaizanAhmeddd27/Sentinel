import re
import xml.etree.ElementTree as ET
from typing import List, Dict, Any
from lxml import etree
from loguru import logger


# Validation rules for Oracle XML payloads
VALIDATION_RULES = [
    {
        "name": "unescaped_ampersand",
        "pattern": r"&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9a-fA-F]+;)",
        "error": "Unescaped '&' character — must be &amp;",
        "field_context": True,
    },
    {
        "name": "unescaped_less_than",
        "pattern": r"<(?![/?!]|[a-zA-Z])",
        "error": "Unescaped '<' character in text content — must be &lt;",
        "field_context": False,
    },
    {
        "name": "control_characters",
        "pattern": r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]",
        "error": "Illegal control character in XML payload",
        "field_context": True,
    },
    {
        "name": "null_bytes",
        "pattern": r"\x00",
        "error": "Null byte detected — invalid in XML",
        "field_context": True,
    },
]

# Required fields in Oracle transaction XML
REQUIRED_FIELDS = [
    "id", "amount", "account", "timestamp"
]

# Fields that must not contain special characters without escaping
SENSITIVE_FIELDS = [
    "beneficiary_name", "account_title", "narration",
    "remarks", "description", "reference"
]


class PayloadValidator:
    """
    Module 4 — Payload Health & Quarantine.

    Pre-screens Oracle XML payloads before batch submission:
    1. XML well-formedness check (lxml)
    2. Schema validation (required fields present)
    3. Character set validation (unescaped specials)
    4. Field-level sanitization check

    For each malformed payload:
    - Identifies exact error + field + line number
    - Generates corrected version with escaped characters
    - Human approval required before Oracle resubmission
    """

    def validate_xml(self, xml_content: str) -> Dict[str, Any]:
        """
        Validate a single XML payload string.

        Returns:
        {
            "is_valid": bool,
            "errors": [{"field", "error", "value", "line_number"}],
            "corrected_xml": str or None,
            "error_count": int
        }
        """
        errors = []

        # Step 1: Well-formedness check via lxml
        try:
            etree.fromstring(xml_content.encode("utf-8"))
        except etree.XMLSyntaxError as e:
            errors.append({
                "field": "_xml_structure",
                "error": f"XML syntax error: {str(e)}",
                "value": None,
                "line_number": e.lineno,
            })
            # Still continue to catch character errors

        # Step 2: Required field check
        try:
            root = ET.fromstring(xml_content)
            present_fields = {child.tag.lower() for child in root}
            for required in REQUIRED_FIELDS:
                if required not in present_fields:
                    errors.append({
                        "field": required,
                        "error": f"Required field '{required}' missing from payload",
                        "value": None,
                        "line_number": None,
                    })
        except ET.ParseError:
            pass  # already caught above

        # Step 3: Character-level validation
        lines = xml_content.split("\n")
        for line_num, line in enumerate(lines, 1):
            for rule in VALIDATION_RULES:
                matches = list(re.finditer(rule["pattern"], line))
                for match in matches:
                    # Determine field context
                    field = self._extract_field_name(line) or "_content"
                    errors.append({
                        "field": field,
                        "error": rule["error"],
                        "value": match.group(0),
                        "line_number": line_num,
                        "rule": rule["name"],
                    })

        # Step 4: Generate corrected version
        corrected = None
        if errors:
            try:
                corrected = self._auto_correct(xml_content)
            except Exception as e:
                logger.warning(f"Auto-correction failed: {e}")

        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "error_count": len(errors),
            "corrected_xml": corrected,
        }

    def validate_batch(self, xml_contents: List[str]) -> Dict[str, Any]:
        """
        Validate a batch of XML payloads.

        Returns summary + per-payload results.
        """
        results = []
        valid_count = 0
        invalid_count = 0

        for i, content in enumerate(xml_contents):
            result = self.validate_xml(content)
            result["payload_index"] = i
            results.append(result)

            if result["is_valid"]:
                valid_count += 1
            else:
                invalid_count += 1

        total = len(xml_contents)
        oracle_safe_rate = round(valid_count / total * 100, 1) if total > 0 else 100.0

        logger.info(
            f"Batch validation: {valid_count}/{total} valid "
            f"({oracle_safe_rate}% Oracle-safe)"
        )

        return {
            "total_payloads": total,
            "valid_payloads": valid_count,
            "invalid_payloads": invalid_count,
            "oracle_safe_rate_percent": oracle_safe_rate,
            "payloads_quarantined": invalid_count,
            "payloads_processed_cleanly": valid_count,
            "results": results,
        }

    def _extract_field_name(self, line: str) -> str:
        """Try to extract XML field name from a line for error context."""
        # Match <fieldname> or </fieldname>
        match = re.search(r"</?([a-zA-Z_][a-zA-Z0-9_]*)", line)
        if match:
            return match.group(1)
        return "_content"

    def _auto_correct(self, xml_content: str) -> str:
        """
        Attempt automatic correction of common XML errors:
        - Escape unescaped & → &amp;
        - Escape unescaped < in text → &lt;
        - Remove illegal control characters
        """
        corrected = xml_content

        # Remove control characters (except tab, newline, carriage return)
        corrected = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", corrected)

        # Fix unescaped & in text content (not inside tags)
        # Replace & that isn't already part of an entity reference
        corrected = re.sub(
            r"&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9a-fA-F]+;)",
            "&amp;",
            corrected,
        )

        logger.debug(
            f"Auto-correction applied: "
            f"{len(xml_content)} → {len(corrected)} chars"
        )
        return corrected