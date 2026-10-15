"""Engine-neutral parameter access policy vocabulary."""

from __future__ import annotations

from enum import Enum

from nf_splice.domain.inputs import InputClassification


class Principal(str, Enum):
    """Party that may change a runnable parameter value."""

    USER = "user"
    PLATFORM = "platform"
    AGENT = "agent"


class Visibility(str, Enum):
    """Presentation hint only; visibility never authorises a write."""

    STANDARD = "standard"
    ADVANCED = "advanced"
    HIDDEN = "hidden"


#: Conservative migration of 0.1.0 classifications (never widens access).
LEGACY_CLASSIFICATION_ACCESS: dict[
    InputClassification, tuple[tuple[Principal, ...], Visibility | None]
] = {
    InputClassification.USER_CONFIGURABLE: ((Principal.USER,), None),
    InputClassification.PLATFORM_MANAGED: ((Principal.PLATFORM,), None),
    InputClassification.EXECUTION_ENVIRONMENT_MANAGED: (
        (Principal.PLATFORM,),
        Visibility.HIDDEN,
    ),
    InputClassification.HIDDEN_OR_UNSUPPORTED: ((), Visibility.HIDDEN),
}
