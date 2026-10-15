"""Sign in with ChatGPT and the Responses provider against offline fake servers."""

from __future__ import annotations

import asyncio
import json
import stat
import threading
import time
import urllib.request
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

jwt = pytest.importorskip("jwt")
rsa = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.rsa")

from nf_splice import credentials  # noqa: E402
from nf_splice.agents.protocol import EventKind, TurnRequest  # noqa: E402
from nf_splice.agents.providers import openai_auth  # noqa: E402
from nf_splice.agents.providers.base import (  # noqa: E402
    ProviderError,
    ProviderErrorKind,
)
from nf_splice.agents.providers.openai import (  # noqa: E402
    OpenAIProvider,
    resolve_credential,
)

ISSUED = "app_issued_client_1"


def _key() -> Any:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


class FakeOpenAI:
    """Authorisation, token, JWKS, revocation and Responses endpoints."""

    def __init__(self) -> None:
        self.key = _key()
        self.signing_key = self.key
        self.audience: str | None = None
        self.nonce_override: str | None = None
        self.scope = f"openid email offline_access {openai_auth.PLAN_SCOPE}"
        self.subject = "user-1"
        self.email = "person@example.org"
        self.nonces: dict[str, str] = {}
        self.refresh_error: str | None = None
        self.refreshes = 0
        self.revoked: list[str] = []
        self.forms: list[dict[str, str]] = []
        self.responses: list[list[tuple[str, dict[str, Any]]]] = []
        self.response_status: tuple[int, dict[str, Any]] | None = None
        self.bodies: list[dict[str, Any]] = []
        self.authorization: list[str] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args: Any) -> None:
                return

            def _send(
                self, status: int, body: Any, kind: str = "application/json"
            ) -> None:
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:
                path = urlparse(self.path).path
                if path == "/jwks":
                    jwk = json.loads(
                        jwt.algorithms.RSAAlgorithm.to_jwk(fake.key.public_key())
                    )
                    jwk.update({"kid": "k1", "use": "sig", "alg": "RS256"})
                    self._send(200, {"keys": [jwk]})
                elif path == "/v1/models":
                    fake.authorization.append(self.headers.get("Authorization", ""))
                    self._send(200, {"data": [{"id": "gpt-test"}, {"id": "gpt-a"}]})
                else:
                    self._send(404, {})

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length).decode()
                path = urlparse(self.path).path
                if path == "/v1/responses":
                    fake.authorization.append(self.headers.get("Authorization", ""))
                    fake.bodies.append(json.loads(raw))
                    if fake.response_status is not None:
                        status, body = fake.response_status
                        self._send(status, body)
                        return
                    events = fake.responses.pop(0)
                    stream = "".join(
                        f"event: {name}\ndata: {json.dumps(data)}\n\n"
                        for name, data in events
                    )
                    self._send(200, stream.encode(), "text/event-stream")
                    return
                form = {key: values[0] for key, values in parse_qs(raw).items()}
                fake.forms.append(form)
                if path == "/revoke":
                    fake.revoked.append(form["token"])
                    self._send(200, {})
                elif path == "/token" and form["grant_type"] == "authorization_code":
                    self._send(200, fake.tokens(form["client_id"], form["code"]))
                elif path == "/token" and form["grant_type"] == "refresh_token":
                    if fake.refresh_error:
                        self._send(400, {"error": fake.refresh_error})
                        return
                    fake.refreshes += 1
                    self._send(
                        200,
                        {
                            "access_token": f"access-{fake.refreshes + 1}",
                            "refresh_token": f"refresh-{fake.refreshes + 1}",
                            "expires_in": 3600,
                            "scope": fake.scope,
                        },
                    )
                else:
                    self._send(404, {})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.endpoints = openai_auth.Endpoints(
            issuer=self.base,
            authorize=f"{self.base}/authorize",
            token=f"{self.base}/token",
            revoke=f"{self.base}/revoke",
            jwks=f"{self.base}/jwks",
            resource=f"{self.base}/v1",
        )

    def tokens(self, client_id: str, code: str) -> dict[str, Any]:
        now = int(time.time())
        claims = {
            "iss": self.base,
            "aud": self.audience or client_id,
            "sub": self.subject,
            "email": self.email,
            "iat": now,
            "exp": now + 600,
            "nonce": self.nonce_override or self.nonces[code],
        }
        id_token = jwt.encode(
            claims, self.signing_key, algorithm="RS256", headers={"kid": "k1"}
        )
        return {
            "access_token": "access-1",
            "refresh_token": "refresh-1",
            "id_token": id_token,
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": self.scope,
        }

    def browser(
        self, issue: str | None = ISSUED, state: str | None = None, error: str = ""
    ) -> Any:
        """A stand-in for the person approving in their browser."""

        def approve(url: str) -> None:
            query = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
            self.authorize = query
            code = f"code-{len(self.nonces)}"
            self.nonces[code] = query["nonce"]
            reply = {"state": state or query["state"], "code": code}
            if issue:
                reply["client_id"] = issue
            if error:
                reply = {"state": reply["state"], "error": error}
            pairs = "&".join(f"{k}={v}" for k, v in reply.items())
            target = f"{query['redirect_uri']}?{pairs}"
            urllib.request.urlopen(target, timeout=5).read()

        return approve

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def fake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeOpenAI]:
    monkeypatch.setenv("NF_SPLICE_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    server = FakeOpenAI()
    yield server
    server.close()


def sign_in(fake: FakeOpenAI, **kwargs: Any) -> dict[str, Any]:
    browser = kwargs.pop("browser", None) or fake.browser()
    return openai_auth.sign_in(
        open_browser=browser,
        announce=lambda _text: None,
        timeout=10,
        endpoints=fake.endpoints,
        port=0,
        **kwargs,
    )


def test_registration_saves_issued_client_owner_only(
    fake: FakeOpenAI, tmp_path: Path
) -> None:
    record = sign_in(fake)
    assert fake.authorize["client_id"] == openai_auth.REGISTRATION_CLIENT
    assert fake.authorize["agent_name_hint"] == "nf-splice"
    assert fake.authorize["code_challenge_method"] == "S256"
    assert fake.authorize["redirect_uri"].startswith("http://127.0.0.1:")
    assert fake.forms[-1]["client_id"] == ISSUED
    assert "client_secret" not in fake.forms[-1]
    assert record["client_id"] == ISSUED and record["plan_usage"] is True
    host = fake.authorize["ext_agent_host_id"]
    assert host == openai_auth.host_id()  # stable per computer
    stored = tmp_path / "config" / "openai" / "accounts" / f"{ISSUED}.json"
    assert stat.S_IMODE(stored.stat().st_mode) == 0o600
    assert stat.S_IMODE(stored.parent.stat().st_mode) == 0o700
    assert (openai_auth.active_account() or {}).get("subject") == "user-1"


def test_state_mismatch_is_rejected_and_nothing_saved(fake: FakeOpenAI) -> None:
    with pytest.raises(openai_auth.SignInError, match="state"):
        sign_in(fake, browser=fake.browser(state="forged"))
    assert openai_auth.accounts() == []


def test_nonce_signature_and_audience_are_verified(fake: FakeOpenAI) -> None:
    fake.nonce_override = "replayed"
    with pytest.raises(openai_auth.SignInError, match="nonce"):
        sign_in(fake)
    fake.nonce_override = None
    fake.signing_key = _key()
    with pytest.raises(openai_auth.SignInError, match="verified"):
        sign_in(fake)
    fake.signing_key = fake.key
    fake.audience = "someone-else"
    with pytest.raises(openai_auth.SignInError, match="verified"):
        sign_in(fake)
    assert all(not item.get("access_token") for item in openai_auth.accounts())


def test_missing_client_id_and_denial_are_refused(fake: FakeOpenAI) -> None:
    with pytest.raises(openai_auth.SignInError, match="client ID"):
        sign_in(fake, browser=fake.browser(issue=None))
    with pytest.raises(openai_auth.SignInError, match="denied"):
        sign_in(fake, browser=fake.browser(error="access_denied"))


def test_plan_usage_needs_the_scope(fake: FakeOpenAI) -> None:
    fake.scope = "openid email offline_access"
    record = sign_in(fake)
    assert record["plan_usage"] is False
    with pytest.raises(ProviderError) as caught:
        openai_auth.access_token(endpoints=fake.endpoints)
    assert caught.value.kind is ProviderErrorKind.CONSENT_REQUIRED


def test_refresh_rotates_and_terminal_errors_require_sign_in(fake: FakeOpenAI) -> None:
    record = sign_in(fake)
    record["expires_at"] = time.time() - 1
    token, fresh = openai_auth.access_token(record, endpoints=fake.endpoints)
    assert token == "access-2" and fresh["refresh_token"] == "refresh-2"
    saved = credentials.read_secret(f"openai/accounts/{ISSUED}.json")
    assert saved and saved["refresh_token"] == "refresh-2"
    fake.refresh_error = "refresh_token_reused"
    fresh["expires_at"] = time.time() - 1
    with pytest.raises(ProviderError) as caught:
        openai_auth.access_token(fresh, endpoints=fake.endpoints)
    assert caught.value.kind is ProviderErrorKind.AUTH_REQUIRED
    saved = credentials.read_secret(f"openai/accounts/{ISSUED}.json")
    assert saved and "refresh_token" not in saved
    fake.refresh_error = "invalid_client"
    saved["refresh_token"] = "x"
    saved["expires_at"] = 0
    credentials.write_secret(f"openai/accounts/{ISSUED}.json", saved)
    with pytest.raises(ProviderError) as caught:
        openai_auth.refresh(saved, endpoints=fake.endpoints)
    assert caught.value.kind is ProviderErrorKind.INVALID_CREDENTIALS


def test_sign_out_revokes_and_forgets_tokens(fake: FakeOpenAI) -> None:
    record = sign_in(fake)
    assert openai_auth.sign_out(record, endpoints=fake.endpoints) is True
    assert fake.revoked == ["refresh-1"]
    saved = credentials.read_secret(f"openai/accounts/{ISSUED}.json")
    assert saved and not saved.get("access_token") and saved["plan_usage"] is False


def test_multiple_accounts_and_reauthentication(fake: FakeOpenAI) -> None:
    sign_in(fake)
    fake.subject, fake.email = "user-2", "other@example.org"
    sign_in(fake, browser=fake.browser(issue="app_issued_client_2"))
    assert {item["client_id"] for item in openai_auth.accounts()} == {
        ISSUED,
        "app_issued_client_2",
    }
    openai_auth.select_account(ISSUED)
    assert (openai_auth.active_account() or {}).get("subject") == "user-1"
    # Signing in again to the saved client uses it, not a new registration.
    fake.subject = "user-1"
    sign_in(fake, client_id=ISSUED, browser=fake.browser(issue=None))
    assert fake.authorize["client_id"] == ISSUED
    assert "agent_name_hint" not in fake.authorize
    # A different person signing in to a saved client never replaces it.
    fake.subject = "intruder"
    with pytest.raises(openai_auth.SignInError, match="different"):
        sign_in(fake, client_id=ISSUED, browser=fake.browser(issue=None))


def test_no_secret_reaches_errors_or_diagnostics(fake: FakeOpenAI) -> None:
    sign_in(fake)
    fake.refresh_error = "invalid_grant"
    record = openai_auth.active_account()
    assert record is not None
    record["expires_at"] = 0
    with pytest.raises(ProviderError) as caught:
        openai_auth.access_token(record, endpoints=fake.endpoints)
    text = json.dumps(caught.value.to_json()) + str(caught.value)
    assert "refresh-1" not in text and "access-1" not in text


class Tools:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "read_layer",
                "description": "Read a layer.",
                "input_schema": {"type": "object", "properties": {}},
            }
        ]

    def call(self, name: str, arguments: Any) -> dict[str, Any]:
        self.calls.append((name, dict(arguments)))
        return {"success": True, "value": "ok"}


def _turn(provider: OpenAIProvider, tools: Tools) -> list[Any]:
    request = TurnRequest(
        purpose="plan",
        instruction="Plan the inputs layer.",
        system_prompt="You are nf-splice.",
        tools=tools,
        stage="inputs",
        max_turns=5,
        timeout_seconds=30,
    )
    session = provider.open(Path("."))

    async def run() -> list[Any]:
        return [event async for event in session.turn(request)]

    return asyncio.run(run())


def _completed(input_tokens: int = 10) -> tuple[str, dict[str, Any]]:
    return (
        "response.completed",
        {"response": {"usage": {"input_tokens": input_tokens, "output_tokens": 5}}},
    )


def test_responses_tool_loop_is_restricted_and_unstored(fake: FakeOpenAI) -> None:
    sign_in(fake)
    fake.responses = [
        [
            (
                "response.output_item.done",
                {
                    "item": {
                        "type": "function_call",
                        "name": "read_layer",
                        "call_id": "c1",
                        "arguments": "{}",
                    }
                },
            ),
            (
                "response.output_item.done",
                {
                    "item": {
                        "type": "function_call",
                        "name": "shell",
                        "call_id": "c2",
                        "arguments": "{}",
                    }
                },
            ),
            ("response.output_item.done", {"item": {"type": "web_search_call"}}),
            _completed(),
        ],
        [
            (
                "response.output_item.done",
                {
                    "item": {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "Done."}],
                    }
                },
            ),
            _completed(20),
        ],
    ]
    tools = Tools()
    provider = OpenAIProvider(
        model="gpt-test", base_url=fake.endpoints.resource, endpoints=fake.endpoints
    )
    events = _turn(provider, tools)
    assert tools.calls == [("read_layer", {})]
    denied = [event.text for event in events if event.kind is EventKind.DENIED]
    assert sorted(denied) == ["shell", "web_search_call"]
    assert [e.text for e in events if e.kind is EventKind.MESSAGE] == ["Done."]
    for body in fake.bodies:
        assert body["store"] is False and body["stream"] is True
        assert [tool["type"] for tool in body["tools"]] == ["function"]
    outputs = [
        item
        for item in fake.bodies[1]["input"]
        if item.get("type") == "function_call_output"
    ]
    assert [item["call_id"] for item in outputs] == ["c1", "c2"]
    assert all(value == "Bearer access-1" for value in fake.authorization)
    usage = [event.data for event in events if event.kind is EventKind.USAGE]
    assert usage[0]["billing"] == "chatgpt-plan" and usage[0]["cost_usd"] is None


@pytest.mark.parametrize(
    ("status", "code", "kind"),
    [
        (429, "usage_limit_reached", ProviderErrorKind.USAGE_EXHAUSTED),
        (429, "insufficient_quota", ProviderErrorKind.USAGE_EXHAUSTED),
        (429, "rate_limit_exceeded", ProviderErrorKind.RATE_LIMITED),
        (401, "invalid_api_key", ProviderErrorKind.INVALID_CREDENTIALS),
        (404, "model_not_found", ProviderErrorKind.MODEL_INCOMPATIBLE),
        (503, "server_error", ProviderErrorKind.PROVIDER_UNAVAILABLE),
        (
            429,
            "subscription_sharing_usage_limit_exceeded",
            ProviderErrorKind.USAGE_EXHAUSTED,
        ),
        (
            403,
            "subscription_sharing_user_not_eligible",
            ProviderErrorKind.PERMISSION_DENIED,
        ),
        (
            503,
            "subscription_sharing_usage_unavailable",
            ProviderErrorKind.PROVIDER_UNAVAILABLE,
        ),
    ],
)
def test_responses_errors_are_typed(
    fake: FakeOpenAI, status: int, code: str, kind: ProviderErrorKind
) -> None:
    sign_in(fake)
    fake.response_status = (status, {"error": {"code": code, "message": "no"}})
    provider = OpenAIProvider(
        model="gpt-test", base_url=fake.endpoints.resource, endpoints=fake.endpoints
    )
    with pytest.raises(ProviderError) as caught:
        _turn(provider, Tools())
    assert caught.value.kind is kind


def test_failed_stream_event_is_typed(fake: FakeOpenAI) -> None:
    sign_in(fake)
    fake.responses = [
        [("response.failed", {"response": {"error": {"code": "usage_limit_reached"}}})]
    ]
    provider = OpenAIProvider(
        model="gpt-test", base_url=fake.endpoints.resource, endpoints=fake.endpoints
    )
    with pytest.raises(ProviderError) as caught:
        _turn(provider, Tools())
    assert caught.value.kind is ProviderErrorKind.USAGE_EXHAUSTED


def test_api_key_is_used_only_when_chosen(
    fake: FakeOpenAI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    with pytest.raises(ProviderError) as caught:
        resolve_credential(endpoints=fake.endpoints)
    assert caught.value.kind is ProviderErrorKind.AUTH_REQUIRED
    chosen = resolve_credential("api-key", endpoints=fake.endpoints)
    assert chosen.mode == "api-key" and chosen.billing == "openai-api-usage"
    monkeypatch.delenv("OPENAI_API_KEY")
    with pytest.raises(ProviderError):
        resolve_credential("api-key", endpoints=fake.endpoints)


def test_model_must_be_chosen(fake: FakeOpenAI) -> None:
    sign_in(fake)
    provider = OpenAIProvider(
        base_url=fake.endpoints.resource, endpoints=fake.endpoints
    )
    with pytest.raises(ProviderError) as caught:
        _turn(provider, Tools())
    assert caught.value.kind is ProviderErrorKind.MODEL_INCOMPATIBLE


def test_short_stream_after_partial_output_is_a_failure(fake: FakeOpenAI) -> None:
    sign_in(fake)
    fake.responses = [
        [
            (
                "response.output_item.done",
                {
                    "item": {
                        "type": "function_call",
                        "name": "read_layer",
                        "call_id": "c1",
                        "arguments": "{}",
                    }
                },
            )
        ]
    ]
    tools = Tools()
    provider = OpenAIProvider(
        model="gpt-test", base_url=fake.endpoints.resource, endpoints=fake.endpoints
    )
    with pytest.raises(ProviderError) as caught:
        _turn(provider, tools)
    assert caught.value.kind is ProviderErrorKind.CONNECTION_LOST
    assert tools.calls == []  # nothing from the cut response was applied


def test_request_id_is_kept(fake: FakeOpenAI) -> None:
    from nf_splice.agents.providers.openai import classify

    error = classify(
        429,
        json.dumps({"error": {"code": "subscription_sharing_usage_limit_exceeded"}}),
        {"x-request-id": "req_123"},
    )
    assert error.request_id == "req_123" and "Settings > Usage" in error.guidance
