"""Offline validation of documents against packaged contract definitions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from jsonschema import (  # type: ignore[import-untyped]
    Draft7Validator,
    Draft202012Validator,
    FormatChecker,
)
from jsonschema.exceptions import SchemaError  # type: ignore[import-untyped]

from nf_splice.contracts.registry import (
    FAMILY_IDS,
    ContractFamily,
    ContractRegistryError,
    family,
    meta_schema,
)

_DIALECTS: dict[str, Any] = {
    "https://json-schema.org/draft/2020-12/schema": Draft202012Validator,
    "https://json-schema.org/draft-07/schema#": Draft7Validator,
    "http://json-schema.org/draft-07/schema#": Draft7Validator,
}


@dataclass(frozen=True, slots=True)
class ContractIssue:
    """One stable, path-addressed contract validation finding."""

    json_pointer: str
    rule: str
    message: str


@dataclass(frozen=True, slots=True)
class ContractValidationReport:
    """Outcome of validating one document against one family revision."""

    family_id: str | None
    revision: str | None
    valid: bool
    issues: tuple[ContractIssue, ...]


def _pointer(parts: list[object]) -> str:
    if not parts:
        return ""
    return "/" + "/".join(
        str(item).replace("~", "~0").replace("/", "~1") for item in parts
    )


def declared_contract(document: Mapping[str, Any]) -> tuple[str, str] | None:
    """Return the family URI and revision a document declares, if any."""
    extension = document.get("x-splice-contract")
    if isinstance(extension, Mapping):
        identifier, version = extension.get("id"), extension.get("version")
        if isinstance(identifier, str) and isinstance(version, str):
            return identifier, version
    identifier = document.get("schema_id")
    version = document.get("schema_version")
    if (
        isinstance(identifier, str)
        and identifier in FAMILY_IDS
        and isinstance(version, str)
    ):
        return identifier, version
    return None


def detect_family(
    document: Mapping[str, Any], filename: str | None = None
) -> ContractFamily | None:
    """Identify the family from declared metadata, then from the file name."""
    declared = declared_contract(document)
    if declared is not None:
        try:
            return family(declared[0])
        except ContractRegistryError:
            return None
    if filename is not None:
        try:
            return family(filename.rsplit("/", 1)[-1])
        except ContractRegistryError:
            return None
    return None


def _schema_errors(schema: Mapping[str, Any], document: object) -> list[ContractIssue]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        ContractIssue(
            _pointer(list(error.absolute_path)), str(error.validator), error.message
        )
        for error in sorted(
            validator.iter_errors(document),
            key=lambda item: (list(map(str, item.absolute_path)), item.message),
        )
    ]


def validate_contract_document(
    document: object,
    family_id: str | None = None,
    *,
    filename: str | None = None,
) -> ContractValidationReport:
    """Validate a final artefact against its family's packaged definition.

    JSON Schema documents (inputs, outputs) are first validated *as schemas*
    against their declared dialect, then against the SPLICE meta-schema for
    their extensions. Data documents are validated against the family schema.
    """
    if not isinstance(document, Mapping):
        return ContractValidationReport(
            None,
            None,
            False,
            (ContractIssue("", "type", "document must be an object"),),
        )
    selected = family(family_id) if family_id else detect_family(document, filename)
    if selected is None:
        return ContractValidationReport(
            None,
            None,
            False,
            (
                ContractIssue(
                    "",
                    "family",
                    "document does not declare a known workflow-bundle contract",
                ),
            ),
        )
    declared = declared_contract(document)
    if declared is None:
        return ContractValidationReport(
            selected.id,
            None,
            False,
            (
                ContractIssue(
                    "",
                    "declaration",
                    "document does not declare its contract family and revision "
                    "(legacy documents need a version-aware migration)",
                ),
            ),
        )
    identifier, revision = declared
    issues: list[ContractIssue] = []
    if identifier != selected.id:
        issues.append(
            ContractIssue(
                "", "family", f"declares {identifier}, expected {selected.id}"
            )
        )
    if revision not in selected.revisions:
        return ContractValidationReport(
            selected.id,
            revision,
            False,
            (
                ContractIssue(
                    "",
                    "unsupported_revision",
                    f"{selected.id} revision {revision!r} is not supported by this "
                    f"nf-splice; known revisions: {', '.join(selected.revisions)}",
                ),
            ),
        )
    if selected.is_json_schema_document:
        dialect = _DIALECTS.get(str(document.get("$schema")))
        if dialect is None:
            issues.append(
                ContractIssue(
                    "/$schema",
                    "dialect",
                    f"unsupported dialect {document.get('$schema')!r}",
                )
            )
        else:
            try:
                dialect.check_schema(document)
            except SchemaError as error:
                issues.append(
                    ContractIssue(
                        _pointer(list(error.absolute_path)), "schema", error.message
                    )
                )
    issues.extend(_schema_errors(meta_schema(selected.id, revision), document))
    return ContractValidationReport(selected.id, revision, not issues, tuple(issues))
