"""Agent provider adapters.

``claude`` (Claude Agent SDK, optional extra) and ``scripted`` (offline,
deterministic) are implemented. A Codex, OpenCode or local-model adapter
implements :class:`nf_splice.agents.protocol.AgentProvider` here: a
``capabilities`` description and ``open()`` returning a session whose
``turn()`` streams events and calls the supplied tool invoker. The engine,
permissions, validation and persistence need no change. Providers without
structured tool calling are refused rather than run without the guarantees.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nf_splice.agents.protocol import AgentProvider

NAMES = ("claude", "scripted")


def provider_for(
    name: str,
    *,
    script: str | Path | None = None,
    progress: Path | None = None,
) -> AgentProvider:
    """Construct a provider by name; nothing is ever selected implicitly."""
    if name == "claude":
        from nf_splice.agents.providers.claude import ClaudeProvider

        return ClaudeProvider()
    if name == "scripted":
        import json

        from nf_splice.agents.providers.scripted import ScriptedProvider

        if script is None:
            raise ValueError("the scripted provider needs --script")
        loaded: Any = json.loads(Path(script).read_text(encoding="utf-8"))
        if not isinstance(loaded, list):
            raise ValueError("a provider script must be a JSON list of turns")
        return ScriptedProvider(loaded, progress=progress)
    raise ValueError(f"unknown provider {name!r}; choose from {', '.join(NAMES)}")
