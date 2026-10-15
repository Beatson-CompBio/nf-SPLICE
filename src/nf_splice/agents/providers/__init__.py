"""Agent provider adapters and the provider registry.

``claude`` (Claude Agent SDK with a Claude Platform API key), ``openai``
(Responses API with Sign in with ChatGPT or an explicitly chosen API key),
``codex`` (Codex app-server), ``opencode`` (OpenCode server) and ``scripted``
(offline, deterministic) implement
:class:`nf_splice.agents.protocol.AgentProvider`. Each adapter module is
imported only when that provider is used or diagnosed, so manual mode never
imports a provider SDK. Providers without structured tool calling are
refused rather than run without the guarantees.

Selection is always explicit: a ``--provider`` option, or the provider the
person saved with ``nf-splice provider select``. nf-splice never routes to
another provider, model or billing route by itself.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nf_splice import credentials
from nf_splice.agents.protocol import AgentProvider
from nf_splice.agents.providers.base import Check, Diagnosis, ModelInfo


@dataclass(frozen=True, slots=True)
class ProviderInfo:
    """What `nf-splice provider list` says about one provider."""

    name: str
    summary: str
    auth: str
    inference: str
    billing: str


PROVIDERS: dict[str, ProviderInfo] = {
    "claude": ProviderInfo(
        "claude",
        "Claude Agent SDK (extra: nf-splice[claude])",
        "Claude Platform (Console) API key",
        "remote",
        "Console organisation credits (Team/Max plan API credits or paid)",
    ),
    "openai": ProviderInfo(
        "openai",
        "OpenAI Responses API, direct (extra: nf-splice[openai] for sign-in)",
        "Sign in with ChatGPT (Plus/Pro plan), or an API key chosen explicitly",
        "remote",
        "ChatGPT plan usage, or metered OpenAI API usage in API-key mode",
    ),
    "codex": ProviderInfo(
        "codex",
        "Codex app-server 0.162.x, locked to nf-splice tools (install Codex yourself)",
        "the openai provider's sign-in or explicitly chosen API key",
        "remote",
        "as for openai: ChatGPT plan usage, or metered API usage in API-key mode",
    ),
    "opencode": ProviderInfo(
        "opencode",
        "OpenCode 2.0.x server, deny-all permissions (install OpenCode yourself)",
        "the model providers and credentials configured in OpenCode",
        "local (loopback model endpoint) or remote, classified per model",
        "the configured model provider; none for local models",
    ),
    "scripted": ProviderInfo(
        "scripted",
        "Offline, deterministic turns from a JSON script (--script)",
        "none",
        "none (no model)",
        "none",
    ),
}
NAMES = tuple(PROVIDERS)
_MODULES = {
    "claude": "claude",
    "openai": "openai",
    "codex": "codex",
    "opencode": "opencode",
}


def canonical(name: str) -> str:
    """Accept names recorded by earlier sessions of this release."""
    return {"claude-agent-sdk": "claude"}.get(name, name)


def _module(name: str) -> Any:
    return importlib.import_module(f"nf_splice.agents.providers.{_MODULES[name]}")


def selected() -> tuple[str | None, str | None]:
    """The provider and model the person saved, if any."""
    saved = credentials.preferences()
    name = saved.get("provider")
    return (str(name) if name else None), saved.get(f"{name}_model")


def select(name: str, model: str | None = None) -> None:
    name = canonical(name)
    if name not in PROVIDERS or name == "scripted":
        raise ValueError(
            f"choose one of: {', '.join(n for n in NAMES if n != 'scripted')}"
        )
    saved = credentials.preferences()
    saved["provider"] = name
    if model is not None:
        saved[f"{name}_model"] = model
    credentials.save_preferences(saved)


def provider_for(
    name: str,
    *,
    script: str | Path | None = None,
    progress: Path | None = None,
    model: str | None = None,
) -> AgentProvider:
    """Construct a provider by name; nothing is ever selected implicitly."""
    name = canonical(name)
    if name == "claude":
        from nf_splice.agents.providers.claude import ClaudeProvider

        return ClaudeProvider()
    if name == "openai":
        from nf_splice.agents.providers.openai import OpenAIProvider

        return OpenAIProvider(model=model or selected_model("openai"))
    if name == "codex":
        from nf_splice.agents.providers.codex import CodexProvider

        return CodexProvider(model=model or selected_model("codex"))
    if name == "opencode":
        from nf_splice.agents.providers.opencode import OpenCodeProvider

        return OpenCodeProvider(model=model or selected_model("opencode"))
    if name == "scripted":
        from nf_splice.agents.providers.scripted import ScriptedProvider

        if script is None:
            raise ValueError("the scripted provider needs --script")
        loaded: Any = json.loads(Path(script).read_text(encoding="utf-8"))
        if not isinstance(loaded, list):
            raise ValueError("a provider script must be a JSON list of turns")
        return ScriptedProvider(loaded, progress=progress)
    raise ValueError(f"unknown provider {name!r}; choose from {', '.join(NAMES)}")


def selected_model(name: str) -> str | None:
    value = credentials.preferences().get(f"{name}_model")
    return str(value) if value else None


def diagnose(name: str, *, online: bool = False) -> Diagnosis:
    """Availability, authentication and routing, without printing secrets."""
    name = canonical(name)
    if name == "scripted":
        return Diagnosis(
            provider="scripted",
            available=True,
            authenticated=True,
            auth_method="none",
            account=None,
            inference="none",
            billing="none",
            checks=[Check("offline", True, "no network, no model; needs --script")],
        )
    if name not in _MODULES:
        raise ValueError(f"unknown provider {name!r}; choose from {', '.join(NAMES)}")
    diagnosis: Diagnosis = _module(name).diagnose(online=online)
    diagnosis.checks.append(
        Check("selected_model", True, selected_model(name) or "none chosen")
    )
    return diagnosis


def models(name: str) -> list[ModelInfo]:
    name = canonical(name)
    if name not in _MODULES:
        return []
    found: list[ModelInfo] = _module(name).list_models()
    return found
