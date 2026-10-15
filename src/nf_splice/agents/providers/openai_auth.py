"""Sign in with ChatGPT for open-source applications (OAuth, PKCE, loopback).

Implements OpenAI's documented open-source flow (checked 15 October 2026,
https://developers.openai.com/siwc/token-sharing-open-source/sign-in):

- first sign-in registers through ``client_id=dynamic_agent_client`` with the
  application name ``nf-splice`` and a stable per-host ``ext_agent_host_id``;
  the callback returns the issued client ID, which is saved and used from
  then on;
- PKCE (S256), fresh ``state`` and ``nonce`` per attempt, and a loopback
  redirect on ``127.0.0.1`` (port 1455 for the first registration);
- the ID token's signature (OpenAI's JWKS), issuer, audience (the issued
  client ID), expiry and nonce are verified before anything is saved;
- ChatGPT plan usage is enabled only when ``chatgpt.tokens.use.direct`` was
  granted; access tokens refresh shortly before expiry, refresh tokens rotate
  and refreshes are serialised; sign-out revokes the refresh token.

No client secret, browser-token scraping or reuse of other applications'
tokens is involved. Credentials are stored owner-only in the user's
configuration folder (see :mod:`nf_splice.credentials`), one record per issued
client ID and verified identity, never in a pipeline repository.
"""

from __future__ import annotations

import base64
import hashlib
import importlib
import secrets
import threading
import time
import uuid
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from nf_splice import credentials
from nf_splice.agents.protocol import ProviderUnavailable
from nf_splice.agents.providers.base import ProviderError, ProviderErrorKind
from nf_splice.agents.providers.http import request_json

APPLICATION_NAME = "nf-splice"
REGISTRATION_CLIENT = "dynamic_agent_client"
PLAN_SCOPE = "chatgpt.tokens.use.direct"
SCOPES = f"openid profile email offline_access resource.invoke {PLAN_SCOPE}"
FIRST_PORT = 1455
_TERMINAL_REFRESH = {
    "invalid_grant",
    "invalid_refresh_token",
    "token_expired",
    "refresh_token_expired",
    "refresh_token_invalidated",
    "refresh_token_reused",
}


@dataclass(frozen=True, slots=True)
class Endpoints:
    """OpenAI's published endpoints (overridable only for offline tests)."""

    issuer: str = "https://auth.openai.com"
    authorize: str = "https://auth.openai.com/api/accounts/authorize"
    token: str = "https://auth.openai.com/api/accounts/oauth/token"
    revoke: str = "https://auth.openai.com/api/accounts/oauth/revoke"
    jwks: str = "https://auth.openai.com/.well-known/jwks.json"
    resource: str = "https://api.openai.com/v1"


ENDPOINTS = Endpoints()


class SignInError(RuntimeError):
    """Sign-in did not complete; nothing was saved."""


def _jwt() -> Any:
    try:
        return importlib.import_module("jwt")
    except ImportError as error:
        raise ProviderUnavailable(
            "Sign in with ChatGPT needs the optional extra: "
            "pip install 'nf-splice[openai]'"
        ) from error


def host_id() -> str:
    """The stable ``ext_agent_host_id`` of this computer (created once)."""
    record = credentials.read_secret("openai/host.json")
    if record and record.get("ext_agent_host_id"):
        return str(record["ext_agent_host_id"])
    value = f"urn:uuid:{uuid.uuid4()}"
    credentials.write_secret("openai/host.json", {"ext_agent_host_id": value})
    return value


def accounts() -> list[dict[str, Any]]:
    """Saved accounts (without exposing tokens to callers that print them)."""
    found = []
    for name in credentials.list_secrets("openai/accounts"):
        record = credentials.read_secret(f"openai/accounts/{name}")
        if record:
            found.append(record)
    return found


def account_label(record: dict[str, Any]) -> str:
    return str(record.get("label") or record.get("email") or record.get("subject"))


def active_account() -> dict[str, Any] | None:
    pointer = credentials.read_secret("openai/active.json") or {}
    client_id = pointer.get("client_id")
    for record in accounts():
        if client_id and record.get("client_id") == client_id:
            return record
    saved = accounts()
    return saved[0] if len(saved) == 1 else None


def select_account(client_id: str) -> None:
    if not any(item.get("client_id") == client_id for item in accounts()):
        raise SignInError(f"no saved ChatGPT account with client ID {client_id}")
    credentials.write_secret("openai/active.json", {"client_id": client_id})


def _save(record: dict[str, Any]) -> None:
    credentials.write_secret(f"openai/accounts/{record['client_id']}.json", record)


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class _Callback(BaseHTTPRequestHandler):
    result: dict[str, str] | None = None

    def log_message(self, *_args: Any) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/auth/callback":
            self.send_response(404)
            self.end_headers()
            return
        type(self).result = {
            key: values[0] for key, values in parse_qs(parsed.query).items()
        }
        body = (
            b"<html><body><h1>nf-splice</h1><p>You can close this window and "
            b"return to the terminal.</p></body></html>"
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _verify_id_token(
    id_token: str, client_id: str, nonce: str, endpoints: Endpoints
) -> dict[str, Any]:
    jwt = _jwt()
    try:
        key = jwt.PyJWKClient(endpoints.jwks).get_signing_key_from_jwt(id_token)
        claims: dict[str, Any] = jwt.decode(
            id_token,
            key.key,
            algorithms=["RS256", "ES256", "PS256"],
            audience=client_id,
            issuer=endpoints.issuer,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
    except jwt.PyJWTError as error:
        raise SignInError(f"the ID token could not be verified: {error}") from error
    if claims.get("nonce") != nonce:
        raise SignInError("the ID token's nonce does not match this sign-in")
    return claims


def sign_in(
    *,
    client_id: str | None = None,
    open_browser: Callable[[str], Any] = webbrowser.open,
    announce: Callable[[str], None] = print,
    timeout: float = 300.0,
    endpoints: Endpoints = ENDPOINTS,
    port: int | None = None,
) -> dict[str, Any]:
    """Run the browser sign-in and save the verified account record."""
    existing = None
    if client_id:
        existing = next(
            (item for item in accounts() if item.get("client_id") == client_id), None
        )
        if existing is None:
            raise SignInError(f"no saved ChatGPT account with client ID {client_id}")
    registering = existing is None
    host = host_id()
    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(64)
    _Callback.result = None
    server = HTTPServer(
        ("127.0.0.1", port if port is not None else (FIRST_PORT if registering else 0)),
        _Callback,
    )
    redirect_uri = f"http://127.0.0.1:{server.server_address[1]}/auth/callback"
    parameters = {
        "response_type": "code",
        "client_id": REGISTRATION_CLIENT if registering else existing["client_id"],  # type: ignore[index]
        "redirect_uri": redirect_uri,
        "scope": SCOPES,
        "resource": endpoints.resource,
        "state": state,
        "nonce": nonce,
        "code_challenge": _challenge(verifier),
        "code_challenge_method": "S256",
        "ext_agent_host_id": host,
    }
    if registering:
        parameters["agent_name_hint"] = APPLICATION_NAME
    else:
        assert existing is not None
        if existing.get("id_token"):
            parameters["id_token_hint"] = str(existing["id_token"])
        if existing.get("email"):
            parameters["login_hint"] = str(existing["email"])
    url = f"{endpoints.authorize}?{urlencode(parameters)}"
    thread = threading.Thread(target=server.handle_request, daemon=True)
    server.timeout = timeout
    thread.start()
    announce(
        "Opening your browser to sign in with ChatGPT. "
        f"If it does not open, visit:\n{url}"
    )
    try:
        open_browser(url)
    except Exception:
        pass
    thread.join(timeout)
    server.server_close()
    result = _Callback.result
    if result is None:
        raise SignInError("sign-in timed out before the browser returned")
    if result.get("state") != state:
        raise SignInError("the sign-in response did not match this attempt (state)")
    if result.get("error"):
        if result["error"] == "access_denied":
            raise SignInError("sign-in was cancelled or access was denied")
        raise SignInError(f"sign-in failed: {result['error']}")
    issued = result.get("client_id")
    if registering:
        if not issued or issued == REGISTRATION_CLIENT:
            raise SignInError("OpenAI did not issue a client ID for nf-splice")
        client = issued
    else:
        assert existing is not None
        client = str(existing["client_id"])
        if issued and issued != client:
            raise SignInError("the sign-in returned a different client ID; rejected")
    if not result.get("code"):
        raise SignInError("the sign-in response carried no authorisation code")
    pending = {"client_id": client, "ext_agent_host_id": host, "pending": True}
    if registering:
        _save(pending)
    try:
        tokens = request_json(
            "POST",
            endpoints.token,
            form={
                "grant_type": "authorization_code",
                "client_id": client,
                "code": result["code"],
                "code_verifier": verifier,
                "redirect_uri": redirect_uri,
                "resource": endpoints.resource,
            },
            vendor="OpenAI sign-in",
        )
    except ProviderError as error:
        raise SignInError(f"the code exchange failed: {error.message}") from error
    claims = _verify_id_token(str(tokens.get("id_token", "")), client, nonce, endpoints)
    if existing is not None and existing.get("subject") not in {None, claims["sub"]}:
        raise SignInError("a different ChatGPT account signed in; nothing replaced")
    scopes = str(tokens.get("scope") or result.get("scope") or "").split()
    record = {
        "label": claims.get("email") or claims["sub"],
        "email": claims.get("email"),
        "issuer": claims.get("iss"),
        "subject": claims["sub"],
        "client_id": client,
        "ext_agent_host_id": host,
        "id_token": tokens.get("id_token"),
        "access_token": tokens.get("access_token"),
        "refresh_token": tokens.get("refresh_token"),
        "token_type": tokens.get("token_type", "Bearer"),
        "expires_at": time.time() + float(tokens.get("expires_in") or 3600),
        "scopes": scopes,
        "plan_usage": PLAN_SCOPE in scopes,
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _save(record)
    credentials.write_secret("openai/active.json", {"client_id": client})
    return record


def refresh(
    record: dict[str, Any], *, endpoints: Endpoints = ENDPOINTS
) -> dict[str, Any]:
    """Rotate tokens; serialised per account so two processes never race."""
    client = str(record["client_id"])
    with credentials.exclusive(f"openai/refresh-{client}"):
        current = credentials.read_secret(f"openai/accounts/{client}.json") or record
        if current.get("expires_at", 0) - time.time() > 300 and current.get(
            "access_token"
        ) != record.get("access_token"):
            return current  # another process refreshed meanwhile
        if not current.get("refresh_token"):
            raise ProviderError(
                ProviderErrorKind.AUTH_REQUIRED,
                "this ChatGPT account has no refresh token",
                "Run `nf-splice provider auth openai --sign-in` again.",
            )
        try:
            tokens = request_json(
                "POST",
                endpoints.token,
                form={
                    "grant_type": "refresh_token",
                    "client_id": client,
                    "refresh_token": str(current["refresh_token"]),
                    "resource": endpoints.resource,
                },
                vendor="OpenAI sign-in",
            )
        except ProviderError as error:
            code = _error_code(error.diagnostic)
            if code in _TERMINAL_REFRESH:
                for key in ("access_token", "refresh_token"):
                    current.pop(key, None)
                _save(current)
                raise ProviderError(
                    ProviderErrorKind.AUTH_REQUIRED,
                    "the ChatGPT sign-in has expired or was revoked",
                    "Run `nf-splice provider auth openai --sign-in` to sign in again.",
                    diagnostic=error.diagnostic,
                ) from None
            if code == "invalid_client":
                raise ProviderError(
                    ProviderErrorKind.INVALID_CREDENTIALS,
                    "OpenAI no longer accepts this nf-splice client registration",
                    "Remove the account with "
                    "`nf-splice provider auth openai --sign-out` and sign in again.",
                    diagnostic=error.diagnostic,
                ) from None
            raise
        current.update(
            {
                "access_token": tokens.get("access_token"),
                "refresh_token": tokens.get("refresh_token")
                or current.get("refresh_token"),
                "expires_at": time.time() + float(tokens.get("expires_in") or 3600),
                "scopes": str(
                    tokens.get("scope") or " ".join(current.get("scopes", []))
                ).split(),
            }
        )
        current["plan_usage"] = PLAN_SCOPE in current["scopes"]
        _save(current)
        return current


def _error_code(diagnostic: str) -> str | None:
    import json

    try:
        body = json.loads(diagnostic)
    except (json.JSONDecodeError, TypeError):
        return None
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            return str(error.get("code") or error.get("type") or "") or None
        if isinstance(error, str):
            return error
        return str(body.get("code") or "") or None
    return None


def access_token(
    record: dict[str, Any] | None = None,
    *,
    endpoints: Endpoints = ENDPOINTS,
    min_seconds: float = 300.0,
) -> tuple[str, dict[str, Any]]:
    """A valid access token for plan usage, refreshing when needed."""
    current = record or active_account()
    if current is None or current.get("pending"):
        raise ProviderError(
            ProviderErrorKind.AUTH_REQUIRED,
            "no ChatGPT account is signed in",
            "Run `nf-splice provider auth openai --sign-in`.",
        )
    if not current.get("plan_usage"):
        raise ProviderError(
            ProviderErrorKind.CONSENT_REQUIRED,
            "ChatGPT plan usage (chatgpt.tokens.use.direct) was not granted",
            "Sign in again and allow nf-splice to use your plan, or choose another "
            "provider or an API key. Nothing is charged to a card.",
        )
    if (
        not current.get("access_token")
        or current.get("expires_at", 0) - time.time() < min_seconds
    ):
        current = refresh(current, endpoints=endpoints)
    return str(current["access_token"]), current


def sign_out(record: dict[str, Any], *, endpoints: Endpoints = ENDPOINTS) -> bool:
    """Revoke the refresh token, then forget the tokens (keep the registration)."""
    revoked = False
    if record.get("refresh_token"):
        try:
            request_json(
                "POST",
                endpoints.revoke,
                form={
                    "token": str(record["refresh_token"]),
                    "token_type_hint": "refresh_token",
                    "client_id": str(record["client_id"]),
                },
                vendor="OpenAI sign-in",
            )
            revoked = True
        except ProviderError:
            revoked = False
    for key in ("access_token", "refresh_token", "id_token"):
        record.pop(key, None)
    record["plan_usage"] = False
    _save(record)
    return revoked
