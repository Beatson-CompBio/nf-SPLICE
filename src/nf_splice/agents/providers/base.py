"""Shared provider types: typed errors, diagnoses and model descriptions.

Every adapter reports problems as a :class:`ProviderError` with one of a fixed
set of kinds, so the engine can pause, retry or ask the person to act in the
same way whatever the vendor. The vendor's own message is kept, redacted, as
diagnostic text only.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from nf_splice.services.audit import redact


class ProviderErrorKind(str, Enum):
    """Why a provider turn could not complete."""

    AUTH_REQUIRED = "auth_required"
    INVALID_CREDENTIALS = "invalid_credentials"
    CONSENT_REQUIRED = "consent_required"
    RATE_LIMITED = "rate_limited"
    USAGE_EXHAUSTED = "usage_exhausted"
    BUDGET_EXHAUSTED = "budget_exhausted"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    CONNECTION_LOST = "connection_lost"
    MODEL_INCOMPATIBLE = "model_incompatible"
    PERMISSION_DENIED = "permission_denied"
    FAILED_TURN = "failed_turn"
    CANCELLED = "cancelled"


#: Kinds worth retrying automatically, with bounded backoff.
RETRYABLE = frozenset(
    {
        ProviderErrorKind.RATE_LIMITED,
        ProviderErrorKind.PROVIDER_UNAVAILABLE,
        ProviderErrorKind.CONNECTION_LOST,
    }
)


@dataclass(slots=True)
class ProviderError(RuntimeError):
    """A classified provider failure; never contains a credential."""

    kind: ProviderErrorKind
    message: str
    guidance: str = ""
    retry_after: float | None = None
    request_id: str | None = None
    diagnostic: str = ""

    def __post_init__(self) -> None:
        self.message = redact(self.message)
        self.diagnostic = redact(self.diagnostic)[:2000]

    def __str__(self) -> str:
        text = f"{self.kind.value}: {self.message}"
        return f"{text} {self.guidance}".strip()

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "message": self.message,
            "guidance": self.guidance,
            "retry_after": self.retry_after,
            "request_id": self.request_id,
            "diagnostic": self.diagnostic,
        }


@dataclass(frozen=True, slots=True)
class ModelInfo:
    """One model a provider offers, as the provider reports it."""

    id: str
    name: str = ""
    tool_calling: bool | None = None
    location: str = "remote"

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Check:
    """One diagnostic check."""

    name: str
    ok: bool
    detail: str

    def to_json(self) -> dict[str, Any]:
        return {"name": self.name, "ok": self.ok, "detail": redact(self.detail)}


@dataclass(slots=True)
class Diagnosis:
    """What ``nf-splice provider doctor`` reports for one provider."""

    provider: str
    available: bool
    authenticated: bool
    auth_method: str
    account: str | None
    inference: str
    billing: str
    checks: list[Check] = field(default_factory=list)
    guidance: list[str] = field(default_factory=list)
    models: list[ModelInfo] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return self.available and self.authenticated

    def to_json(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "ready": self.ready,
            "available": self.available,
            "authenticated": self.authenticated,
            "auth_method": self.auth_method,
            "account": self.account,
            "inference": self.inference,
            "billing": self.billing,
            "checks": [item.to_json() for item in self.checks],
            "guidance": list(self.guidance),
            "models": [item.to_json() for item in self.models],
        }


def classify_http(
    status: int,
    body: str,
    *,
    retry_after: str | None = None,
    request_id: str | None = None,
    vendor: str = "provider",
) -> ProviderError:
    """Map an HTTP failure to a typed error (vendor codes refined by adapters)."""
    seconds = None
    if retry_after:
        try:
            seconds = max(float(retry_after), 0.0)
        except ValueError:
            seconds = None
    lowered = body.lower()
    if status == 401:
        kind, guidance = (
            ProviderErrorKind.INVALID_CREDENTIALS,
            f"Sign in to {vendor} again or check the API key.",
        )
    elif (
        status == 402 or "credit balance" in lowered or "insufficient_quota" in lowered
    ):
        kind, guidance = (
            ProviderErrorKind.USAGE_EXHAUSTED,
            "The account's credits or quota are used up; nothing will be retried.",
        )
    elif status == 403:
        kind, guidance = (
            ProviderErrorKind.PERMISSION_DENIED,
            "The account is not allowed to use this route or model.",
        )
    elif status == 404:
        kind, guidance = (
            ProviderErrorKind.MODEL_INCOMPATIBLE,
            "The model or endpoint is not available to this account.",
        )
    elif status == 429:
        kind, guidance = (
            ProviderErrorKind.RATE_LIMITED,
            "The provider asked nf-splice to slow down.",
        )
    elif status in {400, 422}:
        kind, guidance = (
            ProviderErrorKind.FAILED_TURN,
            "The provider rejected the request.",
        )
    elif status >= 500:
        kind, guidance = (
            ProviderErrorKind.PROVIDER_UNAVAILABLE,
            "The provider is temporarily unavailable.",
        )
    else:
        kind, guidance = ProviderErrorKind.FAILED_TURN, ""
    return ProviderError(
        kind,
        f"{vendor} returned HTTP {status}",
        guidance,
        retry_after=seconds,
        request_id=request_id,
        diagnostic=body[:2000],
    )
