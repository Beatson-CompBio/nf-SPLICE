"""OpenAI provider over the Responses API (no OpenAI SDK needed).

Two authentication modes, never mixed and never chosen silently:

``chatgpt`` (default)
    Sign in with ChatGPT (:mod:`.openai_auth`); usage counts against the
    person's ChatGPT plan when they granted ``chatgpt.tokens.use.direct``.
``api-key``
    An OpenAI Platform API key, only when the person chose this mode
    explicitly (``nf-splice provider auth openai --api-key``). Billed to the
    Platform organisation.

Inference goes only through ``POST /v1/responses`` with ``store: false`` and
``stream: true``. The model sees exactly the nf-splice tools the engine
offers for this turn, as function tools; no hosted tools (web search, file
search, code interpreter, computer use, remote MCP) are ever requested, and a
call to anything else is refused and reported. Because nothing is stored at
OpenAI, the conversation is kept in memory for the process and the engine
supplies its own session summary when a session resumes elsewhere.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nf_splice import credentials
from nf_splice.agents.protocol import (
    AgentEvent,
    EventKind,
    ProviderCapabilities,
    TurnRequest,
    resolve_effort,
)
from nf_splice.agents.providers import openai_auth
from nf_splice.agents.providers.base import (
    Check,
    Diagnosis,
    ModelInfo,
    ProviderError,
    ProviderErrorKind,
    classify_http,
)
from nf_splice.agents.providers.http import request_json, stream_events

API_KEY_VARIABLE = "OPENAI_API_KEY"
AUTH_MODES = ("chatgpt", "api-key")

#: OpenAI error codes mapped to nf-splice error kinds.
_CODES: dict[str, ProviderErrorKind] = {
    "invalid_api_key": ProviderErrorKind.INVALID_CREDENTIALS,
    "invalid_token": ProviderErrorKind.INVALID_CREDENTIALS,
    "token_expired": ProviderErrorKind.AUTH_REQUIRED,
    "insufficient_quota": ProviderErrorKind.USAGE_EXHAUSTED,
    "subscription_sharing_usage_limit_exceeded": ProviderErrorKind.USAGE_EXHAUSTED,
    "subscription_sharing_user_not_eligible": ProviderErrorKind.PERMISSION_DENIED,
    "subscription_sharing_usage_unavailable": ProviderErrorKind.PROVIDER_UNAVAILABLE,
    "usage_limit_reached": ProviderErrorKind.USAGE_EXHAUSTED,
    "usage_not_included": ProviderErrorKind.CONSENT_REQUIRED,
    "insufficient_scope": ProviderErrorKind.CONSENT_REQUIRED,
    "rate_limit_exceeded": ProviderErrorKind.RATE_LIMITED,
    "model_not_found": ProviderErrorKind.MODEL_INCOMPATIBLE,
    "unsupported_model": ProviderErrorKind.MODEL_INCOMPATIBLE,
    "context_length_exceeded": ProviderErrorKind.FAILED_TURN,
    "server_error": ProviderErrorKind.PROVIDER_UNAVAILABLE,
    "server_overloaded": ProviderErrorKind.PROVIDER_UNAVAILABLE,
}

_GUIDANCE: dict[ProviderErrorKind, str] = {
    ProviderErrorKind.INVALID_CREDENTIALS: (
        "Sign in again with `nf-splice provider auth openai --sign-in`, or check "
        "the API key."
    ),
    ProviderErrorKind.AUTH_REQUIRED: "Run `nf-splice provider auth openai --sign-in`.",
    ProviderErrorKind.USAGE_EXHAUSTED: (
        "The ChatGPT plan's usage limit or the API organisation's quota is used "
        "up. See ChatGPT Settings > Usage for when it resets (nf-splice does not "
        "guess), switch provider with `nf-splice session resume --provider ...`, "
        "or continue manually. Nothing is retried."
    ),
    ProviderErrorKind.PERMISSION_DENIED: (
        "This ChatGPT account or workspace is not eligible to share its plan with "
        "nf-splice, or the account may not use this model. Choose another provider, "
        "or an API key explicitly; nothing is charged without that choice."
    ),
    ProviderErrorKind.CONSENT_REQUIRED: (
        "Allow nf-splice to use your ChatGPT plan when signing in, or choose an "
        "API key explicitly."
    ),
    ProviderErrorKind.MODEL_INCOMPATIBLE: (
        "Choose another model: `nf-splice provider models openai`."
    ),
}


def _code(body: str) -> str | None:
    try:
        loaded = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return None
    error = loaded.get("error") if isinstance(loaded, dict) else None
    if isinstance(error, dict):
        return str(error.get("code") or error.get("type") or "") or None
    return None


#: The Responses API's control. Values every reasoning model accepts; a model
#: may reject one, which is reported as an incompatible-model error.
REASONING_CONTROL = "Responses API reasoning.effort"
REASONING_EFFORTS = ("low", "medium", "high")


def classify(status: int, body: str, headers: Mapping[str, str]) -> ProviderError:
    """Refine the generic HTTP mapping with OpenAI's error codes."""
    error = classify_http(
        status,
        body,
        retry_after=headers.get("retry-after"),
        request_id=headers.get("x-request-id"),
        vendor="OpenAI",
    )
    code = _code(body)
    if code in _CODES:
        error.kind = _CODES[code]
        error.guidance = _GUIDANCE.get(error.kind, error.guidance)
    elif error.kind in _GUIDANCE:
        error.guidance = _GUIDANCE[error.kind]
    return error


def _failed(response: Mapping[str, Any]) -> ProviderError:
    error = response.get("error") or {}
    code = str(error.get("code") or "")
    kind = _CODES.get(code, ProviderErrorKind.FAILED_TURN)
    return ProviderError(
        kind,
        f"OpenAI ended the response: {code or 'failed'}",
        _GUIDANCE.get(kind, ""),
        diagnostic=str(error.get("message") or ""),
    )


@dataclass(frozen=True, slots=True)
class Credential:
    """How one request authenticates (the token itself is never logged)."""

    mode: str
    token: str
    account: str | None
    billing: str
    headers: Mapping[str, str] = field(default_factory=dict)


def resolve_credential(
    mode: str | None = None,
    *,
    endpoints: openai_auth.Endpoints | None = None,
    min_seconds: float = 300.0,
) -> Credential:
    """The credential for the chosen mode; never falls back to the other."""
    chosen = mode or auth_mode()
    if chosen not in AUTH_MODES:
        raise ValueError(f"unknown OpenAI auth mode {chosen!r}")
    if chosen == "api-key":
        key, _source = credentials.api_key("openai", API_KEY_VARIABLE)
        if not key:
            raise ProviderError(
                ProviderErrorKind.AUTH_REQUIRED,
                "API-key mode was chosen but no OpenAI API key is configured",
                "Set OPENAI_API_KEY or run `nf-splice provider auth openai --api-key`.",
            )
        return Credential("api-key", key, None, "openai-api-usage")
    token, record = openai_auth.access_token(
        endpoints=endpoints or openai_auth.ENDPOINTS, min_seconds=min_seconds
    )
    return Credential(
        "chatgpt", token, openai_auth.account_label(record), "chatgpt-plan"
    )


def list_models(
    credential: Credential | None = None,
    *,
    base_url: str = openai_auth.ENDPOINTS.resource,
) -> list[ModelInfo]:
    """The selected account's model catalogue (not proof of plan access)."""
    chosen = credential or resolve_credential()
    loaded = request_json(
        "GET",
        f"{base_url}/models",
        headers={"Authorization": f"Bearer {chosen.token}"},
        vendor="OpenAI",
        classifier=classify,
    )
    models = [
        ModelInfo(id=str(item["id"]), name=str(item["id"]), location="remote")
        for item in loaded.get("data", [])
        if isinstance(item, dict) and item.get("id")
    ]
    return sorted(models, key=lambda item: item.id)


def auth_mode() -> str:
    return str(credentials.preferences().get("openai_auth") or "chatgpt")


def diagnose(online: bool = False) -> Diagnosis:
    """Sign-in state, granted plan scope and the chosen billing route."""
    import importlib.util

    mode = auth_mode()
    checks = [Check("auth_mode", True, mode)]
    guidance: list[str] = []
    account = None
    authenticated = False
    available = True
    if mode == "chatgpt":
        available = importlib.util.find_spec("jwt") is not None
        checks.append(
            Check(
                "sign_in_support",
                available,
                "PyJWT present" if available else "the openai extra is not installed",
            )
        )
        if not available:
            guidance.append("Install the extra: pip install 'nf-splice[openai]'.")
        saved = openai_auth.accounts()
        record = openai_auth.active_account()
        checks.append(Check("accounts", bool(saved), f"{len(saved)} saved"))
        if record is not None:
            account = openai_auth.account_label(record)
            signed_in = bool(record.get("refresh_token") or record.get("access_token"))
            checks.append(Check("signed_in", signed_in, account))
            checks.append(
                Check(
                    "plan_usage",
                    bool(record.get("plan_usage")),
                    f"{openai_auth.PLAN_SCOPE} "
                    + ("granted" if record.get("plan_usage") else "not granted"),
                )
            )
            authenticated = signed_in and bool(record.get("plan_usage"))
        if not authenticated:
            guidance.append(
                "Run `nf-splice provider auth openai --sign-in` (ChatGPT Plus or Pro; "
                "eligibility is checked by OpenAI per account)."
            )
    else:
        key, source = credentials.api_key("openai", API_KEY_VARIABLE)
        authenticated = key is not None
        checks.append(Check("api_key", authenticated, f"API key from {source}"))
        guidance.append(
            "API-key mode bills the OpenAI Platform organisation per request."
        )
    models: list[ModelInfo] = []
    if online and authenticated and available:
        try:
            models = list_models()
            checks.append(Check("api", True, f"{len(models)} models listed"))
            guidance.append(
                "A listed model is not proof of plan access; run "
                "`nf-splice provider test openai --allow-remote-model`."
            )
        except ProviderError as error:
            checks.append(Check("api", False, f"{error.kind.value}: {error.message}"))
            guidance.append(error.guidance)
            if error.kind in {
                ProviderErrorKind.AUTH_REQUIRED,
                ProviderErrorKind.INVALID_CREDENTIALS,
            }:
                authenticated = False
    return Diagnosis(
        provider="openai",
        available=available,
        authenticated=authenticated,
        auth_method=("Sign in with ChatGPT" if mode == "chatgpt" else "OpenAI API key"),
        account=account,
        inference="remote",
        billing="chatgpt-plan" if mode == "chatgpt" else "openai-api-usage",
        checks=checks,
        guidance=guidance,
        models=models,
    )


@dataclass(slots=True)
class OpenAIProvider:
    """Explicitly selected; the auth mode and the model are explicit too."""

    auth_mode: str | None = None
    model: str | None = None
    base_url: str = openai_auth.ENDPOINTS.resource
    endpoints: openai_auth.Endpoints | None = None

    @property
    def capabilities(self) -> ProviderCapabilities:
        mode = self.auth_mode or auth_mode()
        return ProviderCapabilities(
            name="openai",
            remote=True,
            tool_calling=True,
            streaming=True,
            cancellation=True,
            budgets=False,
            continuation=False,
            inference="remote",
            billing="openai-api-usage" if mode == "api-key" else "chatgpt-plan",
            reasoning_control=REASONING_CONTROL,
            reasoning_efforts=REASONING_EFFORTS,
        )

    def open(self, repository: Path) -> OpenAISession:
        del repository
        return OpenAISession(self)


@dataclass(slots=True)
class OpenAISession:
    provider: OpenAIProvider
    history: list[dict[str, Any]] = field(default_factory=list)
    cancelled: bool = False
    effort: str | None = None

    @property
    def conversation_ref(self) -> str | None:
        return None

    async def cancel(self) -> None:
        self.cancelled = True

    def _body(self, request: TurnRequest, model: str) -> dict[str, Any]:
        tools = [
            {
                "type": "function",
                "name": spec["name"],
                "description": spec["description"],
                "parameters": spec["input_schema"],
                "strict": False,
            }
            for spec in request.tools.schemas()
        ]
        return {
            "model": model,
            "instructions": request.system_prompt,
            "input": list(self.history),
            "tools": tools,
            "tool_choice": "auto",
            "parallel_tool_calls": False,
            "store": False,
            "stream": True,
            "include": ["reasoning.encrypted_content"],
        } | ({"reasoning": {"effort": self.effort}} if self.effort else {})

    def _stream(
        self, credential: Credential, body: dict[str, Any], timeout: float
    ) -> Iterator[tuple[str, dict[str, Any]]]:
        return stream_events(
            f"{self.provider.base_url}/responses",
            headers={"Authorization": f"Bearer {credential.token}"}
            | dict(credential.headers),
            json_body=body,
            timeout=timeout,
            vendor="OpenAI",
            classifier=classify,
        )

    def _collect(
        self, credential: Credential, body: dict[str, Any], timeout: float
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Run one streamed response; return its output items and usage."""
        items: list[dict[str, Any]] = []
        usage: dict[str, Any] = {}
        completed = False
        for event, data in self._stream(credential, body, timeout):
            if self.cancelled:
                raise ProviderError(
                    ProviderErrorKind.CANCELLED, "the turn was cancelled"
                )
            if event == "response.output_item.done":
                item = data.get("item")
                if isinstance(item, dict):
                    items.append(item)
            elif event == "response.completed":
                completed = True
                response = data.get("response") or {}
                usage = dict(response.get("usage") or {})
            elif event in {"response.failed", "response.incomplete"}:
                response = data.get("response") or {}
                if event == "response.incomplete":
                    details = response.get("incomplete_details") or {}
                    raise ProviderError(
                        ProviderErrorKind.FAILED_TURN,
                        f"OpenAI stopped early: {details.get('reason', 'incomplete')}",
                    )
                raise _failed(response)
            elif event == "error":
                raise _failed({"error": data.get("error") or data})
        if not completed:
            # A short or cut stream is a failure, never a partial success.
            raise ProviderError(
                ProviderErrorKind.CONNECTION_LOST,
                "the OpenAI stream ended before response.completed",
                "Nothing from the incomplete response was applied; resume to retry.",
            )
        return items, usage

    async def turn(self, request: TurnRequest) -> AsyncIterator[AgentEvent]:
        self.cancelled = False
        model = (
            request.model
            or self.provider.model
            or credentials.preferences().get("openai_model")
        )
        if not model:
            raise ProviderError(
                ProviderErrorKind.MODEL_INCOMPATIBLE,
                "no OpenAI model is selected",
                "List models with `nf-splice provider models openai` and choose one "
                "with `nf-splice provider select openai --model ...`.",
            )
        credential = await asyncio.to_thread(
            resolve_credential,
            self.provider.auth_mode,
            endpoints=self.provider.endpoints,
        )
        offered = {spec["name"] for spec in request.tools.schemas()}
        self.effort, notice = resolve_effort(
            request.reasoning_effort,
            REASONING_EFFORTS,
            provider="openai",
            control=REASONING_CONTROL,
        )
        if notice:
            yield AgentEvent(EventKind.NOTICE, notice)
        self.history.append(
            {
                "role": "user",
                "content": [{"type": "input_text", "text": request.instruction}],
            }
        )
        for _step in range(max(request.max_turns, 1)):
            items, usage = await asyncio.to_thread(
                self._collect,
                credential,
                self._body(request, str(model)),
                request.timeout_seconds,
            )
            if usage:
                yield AgentEvent(
                    EventKind.USAGE,
                    "response",
                    {
                        "input_tokens": usage.get("input_tokens"),
                        "output_tokens": usage.get("output_tokens"),
                        "cost_usd": None,
                        "billing": credential.billing,
                    },
                )
            calls = []
            for item in items:
                kind = item.get("type")
                if kind == "message":
                    self.history.append(item)
                    text = "".join(
                        part.get("text", "")
                        for part in item.get("content") or []
                        if part.get("type") == "output_text"
                    )
                    if text:
                        yield AgentEvent(EventKind.MESSAGE, text)
                elif kind == "reasoning":
                    self.history.append(item)
                elif kind == "function_call":
                    self.history.append(item)
                    calls.append(item)
                else:
                    # Hosted tools are never offered; anything else is refused.
                    yield AgentEvent(
                        EventKind.DENIED,
                        str(kind),
                        {"reason": "only nf-splice function tools are available"},
                    )
            if not calls:
                break
            for call in calls:
                name = str(call.get("name"))
                try:
                    arguments = json.loads(call.get("arguments") or "{}")
                except json.JSONDecodeError:
                    arguments = None
                if name not in offered or not isinstance(arguments, dict):
                    result: dict[str, Any] = {
                        "success": False,
                        "denied": True,
                        "error": f"{name} is not offered or its arguments are invalid",
                    }
                    yield AgentEvent(EventKind.DENIED, name, result)
                else:
                    yield AgentEvent(
                        EventKind.TOOL_CALL, name, {"arguments": arguments}
                    )
                    result = request.tools.call(name, arguments)
                    kind = (
                        EventKind.DENIED
                        if result.get("denied")
                        else EventKind.TOOL_RESULT
                    )
                    yield AgentEvent(kind, name, result)
                self.history.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.get("call_id"),
                        "output": json.dumps(result, default=str),
                    }
                )
            if self.cancelled:
                break
        yield AgentEvent(EventKind.DONE)
