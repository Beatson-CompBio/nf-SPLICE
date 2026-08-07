"""Validate analysis_output.json against its generated Draft 7 schema."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from jsonschema import Draft7Validator, FormatChecker  # type: ignore[import-untyped]


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One stable, path-addressed JSON Schema validation failure."""

    json_pointer: str
    rule: str
    message: str


@dataclass(frozen=True, slots=True)
class AnalysisOutputValidationReport:
    """Structured validity and record summary for one runtime inventory."""

    valid: bool
    issues: tuple[ValidationIssue, ...]
    record_count: int
    by_category: tuple[tuple[str, int], ...]
    by_scope: tuple[tuple[str, int], ...]


def _pointer(parts: list[object]) -> str:
    if not parts:
        return ""
    escaped = [str(item).replace("~", "~0").replace("/", "~1") for item in parts]
    return "/" + "/".join(escaped)


def validate_analysis_output(
    document: object, schema: dict[str, Any]
) -> AnalysisOutputValidationReport:
    """Return every deterministic schema failure and output-record counts."""
    Draft7Validator.check_schema(schema)
    validator = Draft7Validator(schema, format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(document),
        key=lambda item: (list(item.absolute_path), item.validator, item.message),
    )
    issues = tuple(
        ValidationIssue(
            json_pointer=_pointer(list(error.absolute_path)),
            rule=str(error.validator),
            message=error.message,
        )
        for error in errors
    )
    files = document.get("files", []) if isinstance(document, dict) else []
    records = [item for item in files if isinstance(item, dict)]
    by_category = Counter(
        str(item["category"]) for item in records if item.get("category")
    )
    by_scope = Counter(str(item["scope"]) for item in records if item.get("scope"))
    return AnalysisOutputValidationReport(
        valid=not issues,
        issues=issues,
        record_count=len(files) if isinstance(files, list) else 0,
        by_category=tuple(sorted(by_category.items())),
        by_scope=tuple(sorted(by_scope.items())),
    )
