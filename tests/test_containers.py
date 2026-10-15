"""Container sources, distributions, cache naming and safe resolution."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest

from layer_fixtures import ADA, ready_identity
from nf_splice.domain.components import ContainerRuntime, ReferenceKind
from nf_splice.drafts import PatchOp
from nf_splice.inspectors.containers import (
    classify_reference,
    container_sources,
    nextflow_cache_filename,
)
from nf_splice.layers import LayerError
from nf_splice.layers.base import edit_draft
from nf_splice.layers.components import (
    accept_component,
    accept_unambiguous_components,
    container_id,
    discover_components,
    set_image_policy,
    validate_components_draft,
    verify_distribution,
)
from nf_splice.services.containers import (
    ContainerServiceError,
    FetchResponse,
    MaterialisedImage,
    ObjectStoreTarget,
    materialise_image,
    publish_image,
    verify_image_url,
)

SIF = (
    b"#!/usr/bin/env run-singularity\n".ljust(32, b"\n") + b"SIF_MAGIC\x00" + b"x" * 500
)
S3_IMAGE = (
    "https://images.example.net/store/"
    "quay.io-splice-bedtools_coreutils-2.31.1_9.5--cfg-8492f6e28a12.img"
)
CONDITIONAL = """process FASTQC {
    container "${ workflow.containerEngine == 'singularity' &&
        !task.ext.singularity_pull_docker_container ?
        'https://depot.galaxyproject.org/singularity/fastqc:0.12.1--hdfd78af_0' :
        'biocontainers/fastqc:0.12.1--hdfd78af_0' }"

    input:
    path reads
}
"""


def _public(_host: str) -> Sequence[str]:
    return ["93.184.216.34"]


class FakeFetcher:
    def __init__(self, responses: dict[str, FetchResponse]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def __call__(self, url: str, *, timeout: float) -> FetchResponse:
        self.calls.append(url)
        return self.responses[url]


def _ok(
    payload: bytes, content_type: str = "application/octet-stream"
) -> FetchResponse:
    def body() -> Iterator[bytes]:
        yield payload[:100]
        yield payload[100:]

    return FetchResponse(
        200, {"Content-Type": content_type, "Content-Length": str(len(payload))}, body()
    )


def _module(root: Path, relative: str, main: str) -> None:
    path = root / relative
    path.mkdir(parents=True)
    (path / "main.nf").write_text(main, encoding="utf-8")
    (path / "meta.yml").write_text(f"name: {path.name}\n", encoding="utf-8")


def _repository(root: Path) -> None:
    ready_identity(root)
    _module(root, "modules/nf-core/fastqc", CONDITIONAL)
    _module(
        root,
        "modules/local/bedtools",
        "process BEDTOOLS {\n    container 'quay.io/splice/bedtools_coreutils:"
        "2.31.1_9.5--cfg-8492f6e28a12'\n\n    input:\n}\n",
    )
    (root / "modules.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "kind": "module",
                        "path": "modules/nf-core/fastqc",
                        "tool": "fastqc",
                    },
                    {
                        "kind": "module",
                        "path": "modules/local/bedtools",
                        "tool": "bedtools",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )


def test_references_are_classified_without_trusting_suffixes() -> None:
    assert (
        classify_reference("quay.io/biocontainers/fastqc:0.12.1")
        is ReferenceKind.OCI_REGISTRY
    )
    assert classify_reference("docker://quay.io/x/y:1") is ReferenceKind.DOCKER_URI
    assert classify_reference("oras://ghcr.io/x/y:1") is ReferenceKind.ORAS
    assert classify_reference(S3_IMAGE) is ReferenceKind.HTTPS_IMAGE
    assert classify_reference("http://host/x.img") is ReferenceKind.INSECURE_HTTP
    assert classify_reference("${params.image}") is ReferenceKind.UNRESOLVED_EXPRESSION


def test_conditional_docker_and_singularity_sources_stay_distinct(
    tmp_path: Path,
) -> None:
    path = tmp_path / "main.nf"
    path.write_text(CONDITIONAL, encoding="utf-8")
    sources = {item.runtime: item for item in container_sources(path, "main.nf")}
    assert sources[ContainerRuntime.SINGULARITY].raw.startswith("https://depot")
    assert (
        sources[ContainerRuntime.DOCKER].raw
        == "biocontainers/fastqc:0.12.1--hdfd78af_0"
    )
    assert sources[ContainerRuntime.DOCKER].kind is ReferenceKind.OCI_REGISTRY

    path.write_text("process X {\n    container params.image\n\n    input:\n}\n")
    assert container_sources(path, "main.nf") == ()
    path.write_text(
        "process X {\n    container \"${task.ext.image ?: 'a/b:1'}\"\n\n    input:\n}\n"
    )
    assert (
        container_sources(path, "main.nf")[0].kind
        is ReferenceKind.UNRESOLVED_EXPRESSION
    )


def test_nextflow_cache_filename_rule() -> None:
    assert (
        nextflow_cache_filename(
            "quay.io/splice/bedtools_coreutils:2.31.1_9.5--cfg-8492f6e28a12"
        )
        == "quay.io-splice-bedtools_coreutils-2.31.1_9.5--cfg-8492f6e28a12.img"
    )
    assert (
        nextflow_cache_filename(
            "biocontainers/fastqc:0.12.1--hdfd78af_0", registry="quay.io"
        )
        == "quay.io-biocontainers-fastqc-0.12.1--hdfd78af_0.img"
    )
    assert (
        nextflow_cache_filename(
            "https://depot.galaxyproject.org/singularity/fastqc:0.12.1--hdfd78af_0"
        )
        == "depot.galaxyproject.org-singularity-fastqc-0.12.1--hdfd78af_0.img"
    )
    assert nextflow_cache_filename("docker://ubuntu:22.04") == "ubuntu-22.04.img"
    assert nextflow_cache_filename("library://x/y.sif") == "x-y.sif"


def test_https_image_verification_guards_ssrf_and_integrity(tmp_path: Path) -> None:
    good = FakeFetcher({S3_IMAGE: _ok(SIF)})
    verified = verify_image_url(
        S3_IMAGE, fetcher=good, resolver=_public, scratch=tmp_path
    )
    assert verified.sha256 == hashlib.sha256(SIF).hexdigest()
    assert verified.format.value == "sif" and verified.size_bytes == len(SIF)
    assert not list(tmp_path.iterdir())

    redirect = FakeFetcher(
        {S3_IMAGE: FetchResponse(302, {"Location": "https://internal/x"}, iter(()))}
    )

    def internal(host: str) -> Sequence[str]:
        return ["10.0.0.5"] if host == "internal" else ["93.184.216.34"]

    with pytest.raises(ContainerServiceError, match="non-public"):
        verify_image_url(S3_IMAGE, fetcher=redirect, resolver=internal)
    for url, message in (
        ("http://images.example.net/x.img", "only https"),
        ("https://user:pw@images.example.net/x.img", "credentials"),
    ):
        with pytest.raises(ContainerServiceError, match=message):
            verify_image_url(url, fetcher=good, resolver=_public)
    with pytest.raises(ContainerServiceError, match="non-public"):
        verify_image_url(S3_IMAGE, fetcher=good, resolver=lambda _h: ["127.0.0.1"])
    cases = [
        (_ok(b"<html>no</html>", "text/html"), "not an image"),
        (_ok(b"plain bytes that are not an image" * 10), "not a recognised"),
        (_ok(SIF), "quota"),
    ]
    for response, message in cases:
        with pytest.raises(ContainerServiceError, match=message):
            verify_image_url(
                S3_IMAGE,
                fetcher=FakeFetcher({S3_IMAGE: response}),
                resolver=_public,
                scratch=tmp_path,
                max_bytes=100 if message == "quota" else 10**9,
            )
    with pytest.raises(ContainerServiceError, match="checksum mismatch"):
        verify_image_url(
            S3_IMAGE,
            fetcher=FakeFetcher({S3_IMAGE: _ok(SIF)}),
            resolver=_public,
            scratch=tmp_path,
            expected_sha256="0" * 64,
        )
    with pytest.raises(ContainerServiceError, match="HTTP 404"):
        verify_image_url(
            S3_IMAGE,
            fetcher=FakeFetcher({S3_IMAGE: FetchResponse(404, {}, iter(()))}),
            resolver=_public,
        )
    assert not list(tmp_path.iterdir())


def test_components_layer_distinguishes_sources_and_verified_distributions(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    pending = discover_components(tmp_path)
    assert {item.id for item in pending} == {
        "component:modules__nf-core__fastqc",
        "component:modules__local__bedtools",
    }
    assert accept_unambiguous_components(tmp_path, ADA)
    set_image_policy(tmp_path, True, ADA)
    blocked = validate_components_draft(tmp_path)
    assert {item.code for item in blocked.errors} == {"needs_materialisation"}

    bedtools = container_id(
        "quay.io/splice/bedtools_coreutils:2.31.1_9.5--cfg-8492f6e28a12"
    )
    fastqc = container_id("biocontainers/fastqc:0.12.1--hdfd78af_0")
    depot = "https://depot.galaxyproject.org/singularity/fastqc:0.12.1--hdfd78af_0"
    fetcher = FakeFetcher({S3_IMAGE: _ok(SIF), depot: _ok(SIF)})
    verify_distribution(
        tmp_path, bedtools, S3_IMAGE, ADA, fetcher=fetcher, resolver=_public
    )
    verify_distribution(tmp_path, fastqc, depot, ADA, fetcher=fetcher, resolver=_public)
    validation = validate_components_draft(tmp_path)
    assert validation.ready, validation.issues
    document = json.loads(validation.files["components.json"])
    by_id = {item["id"]: item for item in document["containers"]}
    assert by_id[bedtools]["type"] == "singularity"
    assert by_id[bedtools]["uri"] == S3_IMAGE
    assert by_id[bedtools]["source_images"] == {
        "docker": "quay.io/splice/bedtools_coreutils:2.31.1_9.5--cfg-8492f6e28a12"
    }
    assert (
        by_id[bedtools]["distribution"]["cache_filename"] == S3_IMAGE.rsplit("/", 1)[1]
    )
    assert set(by_id[fastqc]["source_images"]) == {"docker", "singularity"}
    assert {item["resolution"]["status"] for item in document["containers"]} == {
        "verified"
    }
    assert {item.code for item in validation.issues} == {"cache_reuse"}

    edit_draft(
        tmp_path,
        "components",
        [
            PatchOp(
                "replace",
                "/containers/0/distribution/sha256",
                "f" * 64,
                expected=hashlib.sha256(SIF).hexdigest(),
            )
        ],
        ADA,
    )
    assert "unverified_distribution" in {
        item.code for item in validate_components_draft(tmp_path).errors
    }


def test_docker_only_deployments_publish_native_sources(tmp_path: Path) -> None:
    _repository(tmp_path)
    discover_components(tmp_path)
    accept_unambiguous_components(tmp_path, ADA)
    set_image_policy(tmp_path, False, ADA)
    document = json.loads(validate_components_draft(tmp_path).files["components.json"])
    oci = next(item for item in document["containers"] if "bedtools" in item["uri"])
    assert oci["type"] == "docker" and "distribution" not in oci
    assert oci["resolution"]["status"] == "resolved"


def test_ambiguous_and_unknown_selections_need_explicit_resolution(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    _module(
        tmp_path,
        "modules/local/multi",
        "process MULTI {\n    container 'quay.io/a/b:1'\n"
        "    container 'quay.io/a/b:2'\n\n    input:\n}\n",
    )
    items = json.loads((tmp_path / "modules.json").read_text(encoding="utf-8"))
    items["items"].append(
        {"kind": "module", "path": "modules/local/multi", "tool": "b"}
    )
    (tmp_path / "modules.json").write_text(json.dumps(items), encoding="utf-8")
    discover_components(tmp_path)
    accepted = accept_unambiguous_components(tmp_path, ADA)
    assert "component:modules__local__multi" not in accepted
    with pytest.raises(LayerError, match="ambiguous"):
        accept_component(tmp_path, "component:modules__local__multi", ADA)
    with pytest.raises(LayerError, match="not present"):
        accept_component(
            tmp_path,
            "component:modules__local__multi",
            ADA,
            sources={"docker": "quay.io/a/b:3"},
            version="1",
        )
    with pytest.raises(LayerError, match="unknown component"):
        accept_component(tmp_path, "component:invented", ADA)


def test_materialisation_and_upload_require_explicit_approval(tmp_path: Path) -> None:
    destination = tmp_path / "image.img"
    with pytest.raises(ContainerServiceError, match="approval"):
        materialise_image("quay.io/a/b:1", destination, approve_network=False)
    with pytest.raises(ContainerServiceError, match="no supported image tool"):
        materialise_image(
            "quay.io/a/b:1", destination, approve_network=True, which=lambda _n: None
        )

    def failing(command: Sequence[str]) -> int:
        Path(command[2]).write_bytes(b"partial")
        return 1

    with pytest.raises(ContainerServiceError, match="exit code 1"):
        materialise_image(
            "quay.io/a/b:1",
            destination,
            approve_network=True,
            which=lambda name: f"/usr/bin/{name}",
            runner=failing,
        )
    assert not any(tmp_path.iterdir())
    commands: list[Sequence[str]] = []

    def pulling(command: Sequence[str]) -> int:
        commands.append(command)
        Path(command[2]).write_bytes(SIF)
        return 0

    image = materialise_image(
        "quay.io/a/b:1",
        destination,
        approve_network=True,
        which=lambda name: f"/usr/bin/{name}",
        runner=pulling,
    )
    assert commands == [
        [
            "apptainer",
            "pull",
            str(tmp_path / ".image.img.partial"),
            "docker://quay.io/a/b:1",
        ]
    ]
    assert image.sha256 == hashlib.sha256(SIF).hexdigest()

    class Store:
        def __init__(self, existing: str | None) -> None:
            self.existing = existing
            self.put_calls: list[str] = []

        def exists(self, url: str) -> str | None:
            return self.existing

        def put(self, path: Path, url: str, sha256: str) -> None:
            self.put_calls.append(url)

    target = ObjectStoreTarget.from_environment(
        {
            "NF_SPLICE_IMAGE_STORE_URL": "https://images.example.net/store",
            "NF_SPLICE_IMAGE_STORE_ALLOWED_HOSTS": "images.example.net",
        }
    )
    assert target is not None
    assert ObjectStoreTarget.from_environment({}) is None
    with pytest.raises(ContainerServiceError, match="approval"):
        publish_image(image, "x.img", target, Store(None), approve_upload=False)
    fresh = Store(None)
    assert publish_image(image, "x.img", target, fresh, approve_upload=True).uploaded
    reused = publish_image(
        image, "x.img", target, Store(image.sha256), approve_upload=True
    )
    assert reused.reused and not reused.uploaded
    with pytest.raises(ContainerServiceError, match="different checksum"):
        publish_image(image, "x.img", target, Store("0" * 64), approve_upload=True)
    other = ObjectStoreTarget(
        "https://other.example.net", frozenset({"images.example.net"})
    )
    with pytest.raises(ContainerServiceError, match="not in"):
        publish_image(image, "x.img", other, Store(None), approve_upload=True)
    assert isinstance(image, MaterialisedImage)


@pytest.mark.nextflow
@pytest.mark.skipif(
    shutil.which("nextflow") is None
    or os.environ.get("NF_SPLICE_NEXTFLOW_TESTS") != "1",
    reason="opt-in: requires a local nextflow and NF_SPLICE_NEXTFLOW_TESTS=1",
)
def test_live_nextflow_reuses_the_predicted_cache_file(tmp_path: Path) -> None:
    """Pre-seed the cache with the predicted name; Nextflow must not pull."""
    image = "quay.io/biocontainers/fastqc:0.12.1--hdfd78af_0"
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / nextflow_cache_filename(image)).write_bytes(SIF)
    (tmp_path / "main.nf").write_text(
        f"process P {{\n container '{image}'\n script:\n 'true'\n}}\n"
        "workflow { P() }\n"
    )
    result = subprocess.run(
        ["nextflow", "run", "main.nf", "-with-apptainer", "-preview"],
        cwd=tmp_path,
        env={**os.environ, "NXF_APPTAINER_CACHEDIR": str(cache)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert "Pulling" not in result.stdout + result.stderr


def test_container_expression_stops_at_the_next_directive(tmp_path: Path) -> None:
    module = tmp_path / "main.nf"
    module.write_text(
        """process FASTQC {
    container 'quay.io/biocontainers/fastqc:0.12.1--hdfd78af_0'
    publishDir "${params.outdir}/fastqc", mode: 'copy'
    label 'process_low'

    input:
    path reads
}
""",
        encoding="utf-8",
    )
    sources = container_sources(module, "main.nf")
    assert [(item.raw, item.kind) for item in sources] == [
        (
            "quay.io/biocontainers/fastqc:0.12.1--hdfd78af_0",
            ReferenceKind.OCI_REGISTRY,
        )
    ]
