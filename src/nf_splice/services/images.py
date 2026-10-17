"""Optional, user-invoked delivery of container images to an object store.

The workflow, per distinct runtime image the default profile needs::

    plan (offline) -> approve network -> fetch the native image, or pull and
    convert the OCI image with an installed Apptainer/Singularity -> hash and
    check the image file -> name it as Nextflow's cache would for the source
    it selects -> approve upload -> upload to the configured S3-compatible
    store (never over a different object) -> read it back independently ->
    download it from its public HTTPS location and record the verified
    distribution in components.draft.yaml through the components service.

Nothing here runs as a side effect of init, validation, builds or agent
work: each network step and each upload needs its own explicit approval.
Settings name the store; credentials come from the user's normal provider
(the AWS credential chain or a named profile) and are never written to a
repository, a draft, a log or an agent prompt. Without credentials, network
or an image tool the plan is still produced and nothing is claimed.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

from nf_splice import credentials
from nf_splice.domain.components import ContainerRuntime, ReferenceKind
from nf_splice.inspectors.containers import classify_reference, nextflow_cache_filename
from nf_splice.layers import ChangeContext
from nf_splice.layers.base import read_layer
from nf_splice.services.containers import (
    ContainerServiceError,
    MaterialisedImage,
    detect_format,
    file_sha256,
    materialise_image,
    verify_image_url,
)

SETTINGS_FILE = "image-store.json"
_CHUNK = 1024 * 1024


@dataclass(frozen=True, slots=True)
class StoreSettings:
    """Where images go (no secrets): endpoint, bucket, prefix, public URL."""

    endpoint_url: str
    bucket: str
    prefix: str = ""
    region: str | None = None
    profile: str | None = None
    public_base_url: str | None = None

    def key(self, filename: str) -> str:
        return f"{self.prefix.strip('/')}/{filename}".lstrip("/")

    def public_url(self, filename: str) -> str | None:
        if not self.public_base_url:
            return None
        return f"{self.public_base_url.rstrip('/')}/{self.key(filename)}"

    def to_json(self) -> dict[str, Any]:
        return {
            "endpoint_url": self.endpoint_url,
            "bucket": self.bucket,
            "prefix": self.prefix,
            "region": self.region,
            "profile": self.profile,
            "public_base_url": self.public_base_url,
        }


def _https(value: str, label: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ContainerServiceError(f"{label} must be an https:// URL")
    if parsed.username or parsed.password:
        raise ContainerServiceError(f"{label} must not embed credentials")
    return value.rstrip("/")


def save_settings(settings: StoreSettings) -> Path:
    """Store the (non-secret) image-store settings in the user's config folder."""
    _https(settings.endpoint_url, "the S3 endpoint")
    if settings.public_base_url:
        _https(settings.public_base_url, "the public base URL")
    directory = credentials.config_directory()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / SETTINGS_FILE
    path.write_text(json.dumps(settings.to_json(), indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    return path


def load_settings(environment: Mapping[str, str] | None = None) -> StoreSettings | None:
    """Settings from the environment (``NF_SPLICE_S3_*``) or the config folder."""
    env = os.environ if environment is None else environment
    if env.get("NF_SPLICE_S3_ENDPOINT") and env.get("NF_SPLICE_S3_BUCKET"):
        return StoreSettings(
            endpoint_url=_https(env["NF_SPLICE_S3_ENDPOINT"], "NF_SPLICE_S3_ENDPOINT"),
            bucket=env["NF_SPLICE_S3_BUCKET"],
            prefix=env.get("NF_SPLICE_S3_PREFIX", ""),
            region=env.get("NF_SPLICE_S3_REGION") or None,
            profile=env.get("NF_SPLICE_S3_PROFILE") or None,
            public_base_url=env.get("NF_SPLICE_S3_PUBLIC_URL") or None,
        )
    path = credentials.config_directory(environment) / SETTINGS_FILE
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return StoreSettings(
        endpoint_url=_https(str(data["endpoint_url"]), "endpoint_url"),
        bucket=str(data["bucket"]),
        prefix=str(data.get("prefix") or ""),
        region=data.get("region"),
        profile=data.get("profile"),
        public_base_url=data.get("public_base_url"),
    )


class ObjectClient(Protocol):
    """The S3 operations used (boto3's client satisfies it)."""

    def head_object(self, **kwargs: Any) -> dict[str, Any]: ...

    def put_object(self, **kwargs: Any) -> dict[str, Any]: ...

    def get_object(self, **kwargs: Any) -> dict[str, Any]: ...


def s3_client(settings: StoreSettings) -> ObjectClient:
    """A boto3 client using the user's normal credential chain (optional extra)."""
    try:
        import boto3  # type: ignore[import-not-found]
    except ImportError as error:
        raise ContainerServiceError(
            "S3 uploads need the optional extra: pip install 'nf-splice[s3]'"
        ) from error
    session = boto3.session.Session(profile_name=settings.profile)
    client: ObjectClient = session.client(
        "s3", endpoint_url=settings.endpoint_url, region_name=settings.region
    )
    return client


@dataclass(slots=True)
class S3Uploader:
    """Idempotent upload by content digest, verified by reading back."""

    settings: StoreSettings
    client: ObjectClient

    def stored(self, filename: str) -> dict[str, Any] | None:
        """Size and recorded SHA-256 of an existing object, or None."""
        try:
            head = self.client.head_object(
                Bucket=self.settings.bucket, Key=self.settings.key(filename)
            )
        except Exception as error:  # botocore raises ClientError for 404
            status = getattr(error, "response", {}).get("Error", {}).get("Code")
            if str(status) in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise ContainerServiceError(
                f"could not check {self.settings.key(filename)}: {error}"
            ) from error
        metadata = {
            key.lower(): value for key, value in (head.get("Metadata") or {}).items()
        }
        return {
            "size": int(head.get("ContentLength", 0)),
            "sha256": metadata.get("sha256"),
        }

    def read_back(self, filename: str) -> tuple[str, int]:
        body = self.client.get_object(
            Bucket=self.settings.bucket, Key=self.settings.key(filename)
        )["Body"]
        digest = hashlib.sha256()
        size = 0
        while chunk := body.read(_CHUNK):
            digest.update(chunk)
            size += len(chunk)
        return digest.hexdigest(), size

    def upload(self, path: Path, filename: str, sha256: str) -> str:
        """Upload unless the same content is there; refuse a different object."""
        existing = self.stored(filename)
        size = path.stat().st_size
        if existing is not None:
            if existing["sha256"] == sha256 and existing["size"] == size:
                return "already_stored"
            raise ContainerServiceError(
                f"{self.settings.key(filename)} already exists with different "
                "content; nf-splice never overwrites it"
            )
        with path.open("rb") as handle:
            self.client.put_object(
                Bucket=self.settings.bucket,
                Key=self.settings.key(filename),
                Body=handle,
                ContentLength=size,
                Metadata={"sha256": sha256},
            )
        stored_sha, stored_size = self.read_back(filename)
        if (stored_sha, stored_size) != (sha256, size):
            raise ContainerServiceError(
                f"read-back of {self.settings.key(filename)} does not match the "
                "uploaded image; it is not recorded as verified"
            )
        return "uploaded"


@dataclass(slots=True)
class ImageAction:
    """What one container needs for the default profile's runtime."""

    container: str
    runtime: str
    source: str | None
    kind: str
    status: str
    filename: str | None = None
    note: str = ""
    outcome: str | None = None
    used_by: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "container": self.container,
            "runtime": self.runtime,
            "source": self.source,
            "kind": self.kind,
            "status": self.status,
            "filename": self.filename,
            "note": self.note,
            "outcome": self.outcome,
            "used_by": list(self.used_by),
        }


def _default_engine(root: Path) -> str | None:
    state = read_layer(root, "execution-profiles")
    if state.draft is None or not isinstance(state.draft.data, dict):
        return None
    default = state.draft.data.get("default_profile")
    for item in state.draft.data.get("profiles") or []:
        if isinstance(item, dict) and item.get("id") == default:
            return str(item.get("container_engine") or "") or None
    return None


def plan_images(
    repository_root: str | Path, *, runtime: str | None = None
) -> list[ImageAction]:
    """Offline plan: which image each container needs and how to get it."""
    root = Path(repository_root).resolve()
    engine = runtime or _default_engine(root) or "singularity"
    image_runtime = engine if engine in {"singularity", "apptainer"} else None
    state = read_layer(root, "components")
    if state.draft is None or not isinstance(state.draft.data, dict):
        raise ContainerServiceError("components.draft.yaml is missing or malformed")
    users: dict[str, list[str]] = {}
    for component in state.draft.data.get("components") or []:
        if isinstance(component, dict) and component.get("container_id"):
            users.setdefault(str(component["container_id"]), []).append(
                str(component.get("id"))
            )
    actions = []
    for container in state.draft.data.get("containers") or []:
        if not isinstance(container, dict):
            continue
        identifier = str(container.get("id"))
        sources = container.get("source_images") or {}
        used = users.get(identifier, [])
        if image_runtime is None:
            actions.append(
                ImageAction(
                    identifier,
                    engine,
                    sources.get("docker"),
                    "oci_registry",
                    "pulled_at_run_time",
                    note=f"{engine} pulls OCI images itself",
                    used_by=used,
                )
            )
            continue
        if container.get("distribution"):
            actions.append(
                ImageAction(
                    identifier,
                    image_runtime,
                    None,
                    "distribution",
                    "verified",
                    str((container["distribution"] or {}).get("filename")),
                    used_by=used,
                )
            )
            continue
        source = (
            sources.get(image_runtime)
            or sources.get(ContainerRuntime.SINGULARITY.value)
            or sources.get(ContainerRuntime.APPTAINER.value)
            or sources.get("docker")
        )
        if not source:
            actions.append(
                ImageAction(
                    identifier,
                    image_runtime,
                    None,
                    "none",
                    "unresolved",
                    note="no source image",
                    used_by=used,
                )
            )
            continue
        kind = classify_reference(str(source))
        filename = nextflow_cache_filename(str(source))
        if kind is ReferenceKind.HTTPS_IMAGE:
            status, note = "download", "fetch the native image and verify it"
        elif kind in {ReferenceKind.OCI_REGISTRY, ReferenceKind.DOCKER_URI}:
            status, note = "pull", "pull and convert with Apptainer/Singularity"
        elif kind is ReferenceKind.ORAS:
            status, note = "pull", "pull the ORAS image with Apptainer/Singularity"
        else:
            status, note = "unresolved", f"{kind.value} reference cannot be fetched"
        actions.append(
            ImageAction(
                identifier,
                image_runtime,
                str(source),
                kind.value,
                status,
                filename,
                note,
                used_by=used,
            )
        )
    return actions


def deliver_images(
    repository_root: str | Path,
    context: ChangeContext,
    *,
    approve_network: bool,
    approve_upload: bool,
    uploader: S3Uploader,
    containers: list[str] | None = None,
    scratch: Path | None = None,
    verify: Callable[..., Any] = verify_image_url,
    materialise: Callable[..., MaterialisedImage] = materialise_image,
    record: Callable[..., Any] | None = None,
) -> list[ImageAction]:
    """Run the approved batch; every outcome is reported, nothing is assumed."""
    if not approve_network:
        raise ContainerServiceError(
            "fetching or converting images needs explicit network approval"
        )
    if not approve_upload:
        raise ContainerServiceError("uploading images needs explicit approval")
    from nf_splice.layers.components import verify_distribution

    record = record or verify_distribution
    root = Path(repository_root).resolve()
    actions = [
        item
        for item in plan_images(root)
        if item.status in {"download", "pull"}
        and (not containers or item.container in containers)
    ]
    with tempfile.TemporaryDirectory(prefix="nf-splice-images-", dir=scratch) as work:
        directory = Path(work)
        for action in actions:
            assert action.filename is not None and action.source is not None
            target = directory / action.filename
            try:
                if action.status == "download":
                    verify(action.source, scratch=directory, keep_as=target)
                else:
                    materialise(action.source, target, approve_network=True)
                with target.open("rb") as handle:
                    if detect_format(handle.read(4096)) is None:
                        raise ContainerServiceError(
                            f"{action.filename} is not a SIF or Singularity image"
                        )
                sha = file_sha256(target)
                outcome = uploader.upload(target, action.filename, sha)
                public = uploader.settings.public_url(action.filename)
                if public is None:
                    action.outcome = (
                        f"{outcome}; not recorded: no public_base_url is configured, "
                        "so nobody can download it over HTTPS"
                    )
                    continue
                record(root, action.container, public, context)
                action.outcome = f"{outcome}; verified at {public} and recorded"
            except (ContainerServiceError, OSError, ValueError) as error:
                action.outcome = f"failed: {error}"
            finally:
                target.unlink(missing_ok=True)
    return actions
