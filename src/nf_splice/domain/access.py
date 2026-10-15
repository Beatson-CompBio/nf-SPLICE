"""Engine-neutral parameter access policy vocabulary."""

from __future__ import annotations

from enum import Enum


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
