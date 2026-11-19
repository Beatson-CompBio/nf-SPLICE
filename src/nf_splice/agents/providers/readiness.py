"""Whether AI assistance can actually be used, stated once for every interface.

A saved provider name or an installed SDK is not readiness. Readiness is one
of five levels:

- ``not_configured``: no provider is selected;
- ``incomplete``: a provider is selected, but a part or the sign-in is
  missing;
- ``unverified``: everything is in place, but no connection test has passed
  for this provider, model, sign-in method and account;
- ``verified``: a connection test (``nf-splice provider test``, or the
  workspace's AI settings) passed for exactly this configuration;
- ``unavailable``: a configuration that once passed its test is no longer
  usable (for example the key was removed or the program uninstalled).

The verification record lives in the person's preferences, outside every
repository, and holds no secret. The offline ``scripted`` provider has
nothing to verify. Nothing here contacts a provider: tests are run by
:func:`nf_splice.agents.providers.check.tool_call_check`.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from enum import Enum
from typing import Any

from nf_splice import credentials
from nf_splice.agents.providers import canonical, diagnose, selected, selected_model
from nf_splice.agents.providers.base import Diagnosis


class ReadinessLevel(str, Enum):
    NOT_CONFIGURED = "not_configured"
    INCOMPLETE = "incomplete"
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    UNAVAILABLE = "unavailable"


LABELS = {
    ReadinessLevel.NOT_CONFIGURED: "Not configured",
    ReadinessLevel.INCOMPLETE: "Set-up incomplete",
    ReadinessLevel.UNVERIFIED: "Configured, not yet verified",
    ReadinessLevel.VERIFIED: "Verified",
    ReadinessLevel.UNAVAILABLE: "Previously verified, now unavailable",
}
_KEY = "verified"


@dataclass(frozen=True, slots=True)
class ProviderReadiness:
    """One provider configuration's readiness, with what to do next."""

    level: ReadinessLevel
    provider: str | None = None
    model: str | None = None
    inference: str = ""
    billing: str = ""
    account: str | None = None
    verified_at: str | None = None
    detail: str = ""
    guidance: tuple[str, ...] = ()

    @property
    def usable(self) -> bool:
        """Only a verified configuration offers Assisted and Autonomous."""
        return self.level is ReadinessLevel.VERIFIED

    @property
    def label(self) -> str:
        return LABELS[self.level]

    def summary(self) -> str:
        """One line: the level, then provider, model and where it runs."""
        if self.provider is None:
            return self.label
        parts = [self.provider, f"model {self.model or 'provider default'}"]
        if self.inference:
            parts.append(f"runs {self.inference}")
        text = f"{self.label}: " + " · ".join(parts)
        if self.verified_at and self.level is ReadinessLevel.VERIFIED:
            text += f" · tested {self.verified_at[:10]}"
        return text

    def to_json(self) -> dict[str, Any]:
        return {
            "level": self.level.value,
            "usable": self.usable,
            "provider": self.provider,
            "model": self.model,
            "inference": self.inference,
            "billing": self.billing,
            "account": self.account,
            "verified_at": self.verified_at,
            "detail": self.detail,
            "guidance": list(self.guidance),
        }


def _records() -> dict[str, Any]:
    found = credentials.preferences().get(_KEY)
    return dict(found) if isinstance(found, dict) else {}


def verification(name: str) -> dict[str, Any] | None:
    """The last passing test recorded for a provider, if any."""
    record = _records().get(canonical(name))
    return dict(record) if isinstance(record, dict) else None


def _fingerprint(diagnosis: Diagnosis, model: str | None) -> dict[str, Any]:
    return {
        "model": model,
        "auth_method": diagnosis.auth_method,
        "account": diagnosis.account,
    }


def record_verification(name: str, model: str | None) -> dict[str, Any]:
    """Remember that a connection test passed for this exact configuration."""
    name = canonical(name)
    model = model or selected_model(name)
    record = _fingerprint(diagnose(name), model)
    record["verified_at"] = (
        datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    saved = credentials.preferences()
    records = _records()
    records[name] = record
    saved[_KEY] = records
    credentials.save_preferences(saved)
    return record


def clear_verification(name: str) -> None:
    """Forget a provider's verification (a test failed or the set-up changed)."""
    name = canonical(name)
    records = _records()
    if records.pop(name, None) is not None:
        saved = credentials.preferences()
        saved[_KEY] = records
        credentials.save_preferences(saved)


def _problem(diagnosis: Diagnosis) -> str:
    failing = [
        f"{check.name}: {check.detail}"
        for check in diagnosis.checks
        if not check.ok and check.name != "selected_model"
    ]
    return "; ".join(failing) or "the provider is not ready"


def assess(name: str | None = None, model: str | None = None) -> ProviderReadiness:
    """The readiness of a provider (the saved one when ``name`` is omitted).

    Offline: it reads the installed parts, the sign-in and the recorded
    connection test, and never contacts the provider.
    """
    if name is None:
        name, saved_model = selected()
        model = model or saved_model
    if name is None:
        return ProviderReadiness(
            ReadinessLevel.NOT_CONFIGURED,
            detail="No AI provider is selected; everything works manually.",
            guidance=("Choose one with `nf-splice provider select NAME`.",),
        )
    name = canonical(name)
    model = model or selected_model(name)
    if name == "scripted":
        return ProviderReadiness(
            ReadinessLevel.VERIFIED,
            "scripted",
            model,
            inference="offline (no model)",
            billing="none",
            detail="Offline replay of a script: nothing to verify.",
        )
    try:
        diagnosis = diagnose(name)
    except Exception as error:  # a broken adapter must not hide manual work
        return ProviderReadiness(
            ReadinessLevel.INCOMPLETE, name, model, detail=str(error)
        )
    record = verification(name)
    common: dict[str, Any] = {
        "provider": name,
        "model": model,
        "inference": diagnosis.inference,
        "billing": diagnosis.billing,
        "account": diagnosis.account,
    }
    if not diagnosis.ready:
        return ProviderReadiness(
            ReadinessLevel.UNAVAILABLE if record else ReadinessLevel.INCOMPLETE,
            detail=_problem(diagnosis),
            guidance=tuple(item for item in diagnosis.guidance if item),
            **common,
        )
    if record is not None and all(
        record.get(key) == value
        for key, value in _fingerprint(diagnosis, model).items()
    ):
        return ProviderReadiness(
            ReadinessLevel.VERIFIED,
            verified_at=str(record.get("verified_at") or "") or None,
            detail="The connection test passed for this configuration.",
            **common,
        )
    return ProviderReadiness(
        ReadinessLevel.UNVERIFIED,
        detail=(
            "The sign-in, account or model changed since the last connection test."
            if record
            else "No connection test has passed for this configuration yet."
        ),
        guidance=(
            f"Run `nf-splice provider test {name}` (it sends no repository content).",
        ),
        **common,
    )
