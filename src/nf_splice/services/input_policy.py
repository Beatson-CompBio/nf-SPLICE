"""Deterministic enforcement of the published input contract.

The principal (user, platform or agent) is always supplied by the calling
platform service, never read from the schema or from the request itself.
Visibility hints never authorise writes, and platform-only parameters stay in
the contract: filtering happens at view/API time.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]

from nf_splice.domain.access import Principal, Visibility
from nf_splice.layers.inputs import iter_parameters

#: URI schemes accepted for file/directory references; no network probing.
ALLOWED_DATA_SCHEMES = frozenset({"", "s3", "https", "gs", "az"})
_UNSET = object()


@dataclass(frozen=True, slots=True)
class PolicyViolation:
    """One rejected parameter value with a stable reason code."""

    parameter: str
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class FormField:
    """One parameter as presented to a viewer with its effective rights."""

    name: str
    group: str | None
    title: str
    visibility: str
    editable: bool
    schema: Mapping[str, Any]


def _policies(schema: Mapping[str, Any]) -> dict[str, tuple[set[str], str, Any]]:
    result = {}
    for item in iter_parameters(schema):
        visibility = (item.schema.get("x-splice-ui") or {}).get("visibility")
        if visibility is None:
            visibility = (
                Visibility.HIDDEN.value
                if item.schema.get("hidden")
                else Visibility.STANDARD.value
            )
        result[item.name] = (set(item.editable_by or ()), str(visibility), item)
    return result


def authorise_changes(
    schema: Mapping[str, Any],
    principal: Principal,
    values: Mapping[str, Any],
    *,
    baseline: Mapping[str, Any] | None = None,
) -> tuple[PolicyViolation, ...]:
    """Reject values the principal is not permitted to set.

    A value equal to the baseline (or the schema default when no baseline is
    supplied) is not a change and is always allowed.
    """
    policies = _policies(schema)
    violations = []
    for name, value in sorted(values.items()):
        if name not in policies:
            violations.append(
                PolicyViolation(
                    name, "unknown_parameter", f"{name!r} is not a parameter"
                )
            )
            continue
        allowed, _visibility, parameter = policies[name]
        if baseline is not None and name in baseline:
            reference = baseline[name]
        else:
            reference = parameter.schema.get("default", _UNSET)
        if reference is not _UNSET and value == reference:
            continue
        if principal.value not in allowed:
            violations.append(
                PolicyViolation(
                    name,
                    "not_permitted",
                    f"{principal.value} may not change {name!r} "
                    f"(editable by: {', '.join(sorted(allowed)) or 'nobody'})",
                )
            )
    return tuple(violations)


def validate_data_references(
    schema: Mapping[str, Any], values: Mapping[str, Any]
) -> tuple[PolicyViolation, ...]:
    """Check file/directory references syntactically without touching storage.

    ``exists`` and MIME constraints are annotations enforced by the execution
    environment that can see the data; they are never probed here.
    """
    violations = []
    for item in iter_parameters(schema):
        data = item.schema.get("x-splice-data")
        value = values.get(item.name)
        if not isinstance(data, Mapping) or not isinstance(value, str):
            continue
        parsed = urlparse(value)
        scheme = parsed.scheme.lower()
        if "\x00" in value or not value.strip():
            violations.append(
                PolicyViolation(item.name, "invalid_reference", "empty or NUL path")
            )
        elif scheme not in ALLOWED_DATA_SCHEMES:
            violations.append(
                PolicyViolation(
                    item.name,
                    "unsupported_scheme",
                    f"scheme {scheme!r} is not an allowed data location",
                )
            )
        elif parsed.username or parsed.password:
            violations.append(
                PolicyViolation(
                    item.name,
                    "credential_url",
                    "data references must not embed credentials",
                )
            )
    return tuple(violations)


def validate_submission(
    schema: Mapping[str, Any],
    values: Mapping[str, Any],
    *,
    principal: Principal,
    baseline: Mapping[str, Any] | None = None,
) -> tuple[PolicyViolation, ...]:
    """Validate a parameter submission: authorisation, schema and references."""
    violations = list(authorise_changes(schema, principal, values, baseline=baseline))
    validator = Draft202012Validator(dict(schema), format_checker=FormatChecker())
    for error in sorted(
        validator.iter_errors(dict(values)), key=lambda item: item.message
    ):
        location = "/".join(str(part) for part in error.absolute_path) or "/"
        violations.append(PolicyViolation(location, "schema", error.message))
    violations.extend(validate_data_references(schema, values))
    return tuple(violations)


def form_fields(
    schema: Mapping[str, Any], principal: Principal
) -> tuple[FormField, ...]:
    """Return the fields a principal may see; hidden fields are omitted for users."""
    fields = []
    for name, (allowed, visibility, parameter) in _policies(schema).items():
        editable = principal.value in allowed
        if visibility == Visibility.HIDDEN.value and not editable:
            continue
        fields.append(
            FormField(
                name=name,
                group=parameter.group,
                title=str(parameter.schema.get("title") or name),
                visibility=visibility,
                editable=editable,
                schema=parameter.schema,
            )
        )
    return tuple(fields)


def engine_parameters(
    schema: Mapping[str, Any], values: Mapping[str, Any], *, engine: str = "nextflow"
) -> dict[str, Any]:
    """Map validated generic parameters to native engine bindings.

    Only the Nextflow adapter (``params.<name>``) is implemented in 0.3.0.
    """
    if engine != "nextflow":
        raise ValueError(f"no input adapter is implemented for engine {engine!r}")
    mapped = {}
    for item in iter_parameters(schema):
        if item.name not in values:
            continue
        source = item.schema.get("x-splice-source") or {}
        binding = source.get("binding") if source.get("engine") == engine else None
        if not isinstance(binding, str) or not binding.startswith("params."):
            binding = f"params.{item.name}"
        mapped[binding.removeprefix("params.")] = values[item.name]
    return mapped
