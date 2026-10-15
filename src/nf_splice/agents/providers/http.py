"""Minimal HTTP and server-sent-event helpers (standard library only).

Errors become typed :class:`ProviderError` values; response bodies are kept
only as redacted diagnostics. Bearer tokens are never logged.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator, Mapping
from typing import Any

from nf_splice.agents.providers.base import (
    ProviderError,
    ProviderErrorKind,
    classify_http,
)

Classifier = Callable[[int, str, Mapping[str, str]], ProviderError]


def _error_from_response(
    error: urllib.error.HTTPError, vendor: str, classifier: Classifier | None
) -> ProviderError:
    body = error.read().decode("utf-8", errors="replace") if error.fp else ""
    headers = {key.lower(): value for key, value in (error.headers or {}).items()}
    if classifier is not None:
        return classifier(error.code, body, headers)
    return classify_http(
        error.code,
        body,
        retry_after=headers.get("retry-after"),
        request_id=headers.get("x-request-id") or headers.get("request-id"),
        vendor=vendor,
    )


def _connection_error(error: Exception, vendor: str) -> ProviderError:
    return ProviderError(
        ProviderErrorKind.CONNECTION_LOST,
        f"could not reach {vendor}: {type(error).__name__}",
        "Check the network connection and try again.",
        diagnostic=str(error),
    )


def request(
    method: str,
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    json_body: Any = None,
    form: Mapping[str, str] | None = None,
    timeout: float = 60.0,
    vendor: str = "provider",
    classifier: Classifier | None = None,
) -> tuple[int, dict[str, str], bytes]:
    """One HTTP request; raises :class:`ProviderError` on failure."""
    data = None
    all_headers = dict(headers or {})
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        all_headers.setdefault("Content-Type", "application/json")
    elif form is not None:
        data = urllib.parse.urlencode(dict(form)).encode("utf-8")
        all_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    call = urllib.request.Request(url, data=data, method=method, headers=all_headers)
    try:
        with urllib.request.urlopen(call, timeout=timeout) as response:
            return (
                response.status,
                {key.lower(): value for key, value in response.headers.items()},
                response.read(),
            )
    except urllib.error.HTTPError as error:
        raise _error_from_response(error, vendor, classifier) from None
    except (TimeoutError, urllib.error.URLError, ConnectionError, OSError) as error:
        raise _connection_error(error, vendor) from None


def request_json(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    _status, _headers, body = request(method, url, **kwargs)
    if not body:
        return {}
    loaded = json.loads(body.decode("utf-8"))
    return loaded if isinstance(loaded, dict) else {"data": loaded}


def stream_events(
    url: str,
    *,
    headers: Mapping[str, str],
    json_body: Any,
    timeout: float = 600.0,
    vendor: str = "provider",
    classifier: Classifier | None = None,
) -> Iterator[tuple[str, dict[str, Any]]]:
    """POST and yield ``(event, data)`` pairs from a server-sent event stream."""
    data = json.dumps(json_body).encode("utf-8")
    call = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers=dict(headers)
        | {"Content-Type": "application/json", "Accept": "text/event-stream"},
    )
    try:
        response = urllib.request.urlopen(call, timeout=timeout)
    except urllib.error.HTTPError as error:
        raise _error_from_response(error, vendor, classifier) from None
    except (TimeoutError, urllib.error.URLError, ConnectionError, OSError) as error:
        raise _connection_error(error, vendor) from None
    event = ""
    lines: list[str] = []
    try:
        with response:
            for raw in response:
                line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                if not line:
                    if lines:
                        text = "\n".join(lines)
                        lines = []
                        if text.strip() == "[DONE]":
                            return
                        try:
                            payload = json.loads(text)
                        except json.JSONDecodeError:
                            payload = {"raw": text}
                        yield event or str(payload.get("type", "")), payload
                    event = ""
                    continue
                if line.startswith(":"):
                    continue
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    lines.append(line[5:].lstrip())
    except (TimeoutError, ConnectionError, OSError) as error:
        raise _connection_error(error, vendor) from None
