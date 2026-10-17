"""Opt-in verification and materialisation of container images.

Uploading to an object store is :mod:`nf_splice.services.images`. Nothing
here runs implicitly. Network access and image builds each need an
explicit call, and every external URL is treated as untrusted:
HTTPS only, no embedded credentials, no private/loopback/link-local targets
(re-checked for every redirect hop), bounded streaming with a size quota,
temporary files and atomic placement. No credentials, accounts or
organisation-specific endpoints are built in.
"""

from __future__ import annotations

import hashlib
import ipaddress
import os
import shutil
import socket
import subprocess
import tempfile
import urllib.request
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol
from urllib.parse import urljoin, urlparse

from nf_splice.domain.components import ImageFormat

DEFAULT_MAX_BYTES = 20 * 1024**3
MAX_REDIRECTS = 5
_CHUNK = 1024 * 1024
_SIF_MAGIC = b"SIF_MAGIC"
_SQUASHFS_MAGIC = b"hsqs"


class ContainerServiceError(ValueError):
    """Raised when a container operation is unsafe or fails verification."""


@dataclass(frozen=True, slots=True)
class FetchResponse:
    """One HTTP response hop: status, headers and a body stream."""

    status: int
    headers: Mapping[str, str]
    body: Iterator[bytes]


class Fetcher(Protocol):
    """Single-hop HTTPS GET without automatic redirects."""

    def __call__(self, url: str, *, timeout: float) -> FetchResponse: ...


Resolver = Callable[[str], Sequence[str]]


def _system_resolver(host: str) -> Sequence[str]:
    return sorted({str(item[4][0]) for item in socket.getaddrinfo(host, 443)})


def check_url(url: str, *, resolver: Resolver = _system_resolver) -> None:
    """Reject non-HTTPS, credential-bearing or internal-network URLs."""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ContainerServiceError(f"only https:// image URLs are accepted: {url}")
    if parsed.username or parsed.password:
        raise ContainerServiceError("image URLs must not embed credentials")
    if not parsed.hostname:
        raise ContainerServiceError(f"image URL has no host: {url}")
    try:
        addresses = resolver(parsed.hostname)
    except OSError as error:
        raise ContainerServiceError(
            f"cannot resolve {parsed.hostname}: {error}"
        ) from error
    if not addresses:
        raise ContainerServiceError(f"{parsed.hostname} does not resolve")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise ContainerServiceError(
                f"{parsed.hostname} resolves to a non-public address {address}"
            )


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


def urllib_fetcher(url: str, *, timeout: float) -> FetchResponse:
    """Default TLS-verifying single-hop fetcher (redirects are not followed)."""
    opener = urllib.request.build_opener(_NoRedirect())
    request = urllib.request.Request(url, headers={"User-Agent": "nf-splice"})
    try:
        response = opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as error:
        return FetchResponse(error.code, dict(error.headers.items()), iter(()))

    def chunks() -> Iterator[bytes]:
        with response:
            while chunk := response.read(_CHUNK):
                yield chunk

    return FetchResponse(response.status, dict(response.headers.items()), chunks())


@dataclass(frozen=True, slots=True)
class VerifiedImage:
    """Integrity facts established by downloading an image completely."""

    url: str
    final_url: str
    sha256: str
    size_bytes: int
    format: ImageFormat
    filename: str


def detect_format(head: bytes) -> ImageFormat | None:
    """Recognise SIF or legacy squashfs-based Singularity images by signature."""
    if head[32:41] == _SIF_MAGIC or head.startswith(_SIF_MAGIC):
        return ImageFormat.SIF
    if head.startswith(_SQUASHFS_MAGIC):
        return ImageFormat.IMG
    if head.startswith(b"#!") and _SQUASHFS_MAGIC in head[:4096]:
        return ImageFormat.IMG
    return None


def verify_image_url(
    url: str,
    *,
    fetcher: Fetcher = urllib_fetcher,
    resolver: Resolver = _system_resolver,
    max_bytes: int = DEFAULT_MAX_BYTES,
    timeout: float = 60.0,
    scratch: Path | None = None,
    expected_sha256: str | None = None,
    keep_as: Path | None = None,
) -> VerifiedImage:
    """Download and verify an image without trusting its URL suffix.

    Every redirect target is validated. The body is streamed to a temporary
    file with a size limit; its SHA-256 and format signature are computed.
    """
    current = url
    response: FetchResponse | None = None
    for _hop in range(MAX_REDIRECTS + 1):
        check_url(current, resolver=resolver)
        response = fetcher(current, timeout=timeout)
        if response.status in {301, 302, 303, 307, 308}:
            location = {
                key.lower(): value for key, value in response.headers.items()
            }.get("location")
            if not location:
                raise ContainerServiceError(f"redirect from {current} has no target")
            current = urljoin(current, location)
            continue
        break
    else:
        raise ContainerServiceError(f"too many redirects for {url}")
    assert response is not None
    if response.status != 200:
        raise ContainerServiceError(f"{current} returned HTTP {response.status}")
    headers = {key.lower(): value for key, value in response.headers.items()}
    declared = headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > max_bytes:
        raise ContainerServiceError(f"image is larger than the {max_bytes}-byte quota")
    content_type = headers.get("content-type", "")
    if content_type.startswith(("text/html", "application/json")):
        raise ContainerServiceError(f"{current} is not an image ({content_type})")
    directory = scratch or Path(tempfile.gettempdir())
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".nf-splice-image-", dir=directory
    )
    temporary = Path(temporary_name)
    digest = hashlib.sha256()
    size = 0
    head = b""
    try:
        with os.fdopen(descriptor, "wb") as handle:
            for chunk in response.body:
                size += len(chunk)
                if size > max_bytes:
                    raise ContainerServiceError(
                        f"image exceeds the {max_bytes}-byte quota; download aborted"
                    )
                if len(head) < 4096:
                    head += chunk[: 4096 - len(head)]
                digest.update(chunk)
                handle.write(chunk)
        if size == 0:
            raise ContainerServiceError(f"{current} returned an empty body")
        image_format = detect_format(head)
        if image_format is None:
            raise ContainerServiceError(
                f"{current} is not a recognised SIF or Singularity image file"
            )
        sha = digest.hexdigest()
        if expected_sha256 is not None and sha != expected_sha256:
            raise ContainerServiceError(
                f"checksum mismatch: expected {expected_sha256}, downloaded {sha}"
            )
        if keep_as is not None:
            os.replace(temporary, keep_as)
    finally:
        temporary.unlink(missing_ok=True)
    return VerifiedImage(
        url=url,
        final_url=current,
        sha256=sha,
        size_bytes=size,
        format=image_format,
        filename=PurePosixPath(urlparse(url).path).name,
    )


def file_sha256(path: Path) -> str:
    """Hash a local file in bounded chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


Runner = Callable[[Sequence[str]], int]


def _subprocess_runner(command: Sequence[str]) -> int:
    return subprocess.run(list(command), check=False).returncode


@dataclass(frozen=True, slots=True)
class MaterialisedImage:
    """A locally built or pulled image and its checksum."""

    path: Path
    sha256: str
    size_bytes: int
    tool: str


def materialise_image(
    docker_reference: str,
    destination: Path,
    *,
    approve_network: bool,
    tool: str | None = None,
    runner: Runner = _subprocess_runner,
    which: Callable[[str], str | None] = shutil.which,
) -> MaterialisedImage:
    """Pull/convert an OCI image with an installed Apptainer/Singularity.

    Requires explicit approval: it may need network, CPU, storage and local
    permissions. It never uses sudo or Docker. On failure no partial image is
    left at the destination.
    """
    if not approve_network:
        raise ContainerServiceError(
            "materialising an image needs explicit approval (network, CPU, storage)"
        )
    candidates = [tool] if tool else ["apptainer", "singularity"]
    selected = next((item for item in candidates if item and which(item)), None)
    if selected is None:
        tried = ", ".join(item for item in candidates if item)
        raise ContainerServiceError(
            f"no supported image tool found on PATH (tried {tried})"
        )
    if destination.exists():
        raise ContainerServiceError(f"refusing to overwrite existing {destination}")
    partial = destination.with_name(f".{destination.name}.partial")
    partial.unlink(missing_ok=True)
    source = (
        docker_reference
        if "://" in docker_reference
        else f"docker://{docker_reference}"
    )
    code = runner([selected, "pull", str(partial), source])
    if code != 0 or not partial.is_file():
        partial.unlink(missing_ok=True)
        raise ContainerServiceError(f"{selected} pull failed with exit code {code}")
    os.replace(partial, destination)
    return MaterialisedImage(
        destination, file_sha256(destination), destination.stat().st_size, selected
    )
