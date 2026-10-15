"""Execution profiles: reviewed default, adopted and generated configs."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from layer_fixtures import ADA, ready_identity
from nf_splice.layers import LayerError
from nf_splice.layers.execution import (
    PLATFORM_SECTION,
    USER_SECTION,
    add_generated_profile,
    add_slurm_default_candidate,
    config_draft_path,
    discover_execution,
    groovy_literal,
    pending_profiles,
    reject_profile,
    review_profile,
    set_default_profile,
    validate_execution_draft,
)
from nf_splice.layers.inputs import import_inputs, set_access

FIXTURE = Path(__file__).parent / "fixtures" / "nf-schema" / "nextflow_schema.json"
LOCAL = b"process { executor = 'local' }\r\nsingularity.enabled = true\r\n"


def _repository(root: Path, local: bytes = LOCAL) -> None:
    ready_identity(root)
    (root / "conf").mkdir()
    (root / "conf" / "local.config").write_bytes(local)
    (root / "nextflow.config").write_text(
        "profiles {\n    local { includeConfig 'conf/local.config' }\n"
        "    test { includeConfig 'conf/local.config' }\n}\n",
        encoding="utf-8",
    )
    shutil.copy(FIXTURE, root / "nextflow_schema.json")
    import_inputs(root)
    set_access(root, ["genome", "input", "email"], ["user"], ADA)
    set_access(root, ["outdir", "max_cpus", "igenomes_base"], ["platform"], ADA)
    set_access(
        root,
        ["min_mapped_reads", "skip_qc", "extra_args", "aligners", "thresholds"],
        ["user", "agent"],
        ADA,
    )
    set_access(root, ["trace_report_suffix"], [], ADA)


def _codes(root: Path) -> set[str]:
    return {item.code for item in validate_execution_draft(root).issues}


def test_adopted_and_generated_profiles_with_one_reviewed_default(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    assert {item.id for item in discover_execution(tmp_path)} == {
        "profile:local",
        "profile:test",
    }
    review_profile(
        tmp_path,
        "profile:local",
        ADA,
        profile_type="development",
        description="Local development.",
        executor="local",
        container_engine="singularity",
        config_source="conf/local.config",
    )
    reject_profile(tmp_path, "profile:test", "CI only", ADA)
    add_slurm_default_candidate(tmp_path, ADA)
    assert pending_profiles(tmp_path) == ()
    assert "missing_default" in _codes(tmp_path)

    slurm = "profile-splice_splice_slurm-" + b"splice_splice_slurm".hex()
    set_default_profile(tmp_path, slurm, ADA)
    validation = validate_execution_draft(tmp_path)
    assert validation.ready, validation.issues
    catalogue = json.loads(validation.files["execution-profiles.json"])
    assert catalogue["default_profile"] == slurm
    assert [item["default"] for item in catalogue["profiles"]] == [False, True]
    assert {item["config_strategy"] for item in catalogue["profiles"]} == {
        "adopted",
        "generated",
    }
    local_id = "profile-local-6c6f63616c"
    assert validation.files[f"configs/{local_id}.config"] == LOCAL
    generated = validation.files[f"configs/{slurm}.config"].decode("utf-8")
    assert USER_SECTION in generated and PLATFORM_SECTION in generated
    assert "executor = 'slurm'" in generated
    assert "operator-managed: queue" in generated
    assert "nf-SPLICE draft" not in generated
    assert validate_execution_draft(tmp_path).files == validation.files
    with pytest.raises(LayerError, match="unknown execution profile"):
        set_default_profile(tmp_path, "profile-nope", ADA)


def test_generated_sections_respect_input_policies(tmp_path: Path) -> None:
    _repository(tmp_path)
    discover_execution(tmp_path)
    reject_profile(tmp_path, "profile:local", "x", ADA)
    reject_profile(tmp_path, "profile:test", "x", ADA)
    add_generated_profile(
        tmp_path,
        ADA,
        name="Cluster",
        description="Cluster.",
        profile_type="production",
        executor="slurm",
        container_engine="apptainer",
        generate={
            "user_params": {"genome": "GRCm39", "max_cpus": 4},
            "platform_params": {"max_cpus": 8, "genome": "x", "api_token": "s"},
        },
    )
    identifier = "profile-splice_cluster-" + b"splice_cluster".hex()
    set_default_profile(tmp_path, identifier, ADA)
    issues = validate_execution_draft(tmp_path).issues
    pointers = {item.pointer for item in issues if item.code == "section_policy"}
    assert pointers == {
        "/profiles/0/generated/user_params/max_cpus",
        "/profiles/0/generated/platform_params/genome",
        "/profiles/0/generated/platform_params/api_token",
    }
    assert "secret_literal" in {item.code for item in issues}
    text = (tmp_path / config_draft_path(identifier)).read_text(encoding="utf-8")
    assert "    genome = 'GRCm39'" in text and "    max_cpus = 8" in text


def test_generated_config_drafts_are_editable_and_preserved(tmp_path: Path) -> None:
    _repository(tmp_path)
    discover_execution(tmp_path)
    reject_profile(tmp_path, "profile:local", "x", ADA)
    reject_profile(tmp_path, "profile:test", "x", ADA)
    add_slurm_default_candidate(tmp_path, ADA)
    identifier = "profile-splice_splice_slurm-" + b"splice_splice_slurm".hex()
    set_default_profile(tmp_path, identifier, ADA)
    path = tmp_path / config_draft_path(identifier)
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "process {", "process {\n    // developer note\n    maxRetries = 2"
        ),
        encoding="utf-8",
    )
    final = validate_execution_draft(tmp_path).files[f"configs/{identifier}.config"]
    assert b"maxRetries = 2" in final and b"// developer note" in final
    path.write_text(
        path.read_text(encoding="utf-8").replace(USER_SECTION, ""), encoding="utf-8"
    )
    assert "missing_sections" in _codes(tmp_path)


@pytest.mark.parametrize(
    ("config", "message"),
    [
        (b"process { executor = 'local' }\npassword = 'hunter2'\n", "embedded secret"),
        (b"process { executor = 'local' }\nparams.x = '/Users/ada/data'\n", "personal"),
        (b"process { clusterOptions = '--account=proj123' }\n", "HPC account"),
        (b"process { executor = 'local' }\nparams.genome = 'GRCh38'\n", "genome"),
    ],
)
def test_unsafe_adopted_configs_are_reported(
    tmp_path: Path, config: bytes, message: str
) -> None:
    _repository(tmp_path, config)
    discover_execution(tmp_path)
    reject_profile(tmp_path, "profile:test", "x", ADA)
    review_profile(
        tmp_path,
        "profile:local",
        ADA,
        profile_type="production",
        description="Production.",
        executor="local",
        container_engine="singularity",
        config_source="conf/local.config",
    )
    set_default_profile(tmp_path, "profile-local-6c6f63616c", ADA)
    validation = validate_execution_draft(tmp_path)
    assert not validation.ready
    assert any(message in item.message for item in validation.issues)


def test_review_requires_one_explicit_route_and_detected_values(tmp_path: Path) -> None:
    _repository(tmp_path)
    discover_execution(tmp_path)
    common = {
        "profile_type": "development",
        "description": "x",
        "container_engine": "singularity",
    }
    with pytest.raises(LayerError, match="exactly one config route"):
        review_profile(tmp_path, "profile:local", ADA, executor="local", **common)
    with pytest.raises(LayerError, match="not in detected"):
        review_profile(
            tmp_path,
            "profile:local",
            ADA,
            executor="slurm",
            config_source="conf/local.config",
            **common,
        )
    with pytest.raises(LayerError, match="outside splice"):
        review_profile(
            tmp_path,
            "profile:local",
            ADA,
            executor="local",
            config_source="../x.config",
            **common,
        )
    assert groovy_literal("it's $HOME") == "'it\\'s \\$HOME'"
    assert groovy_literal([1, True, None, {"a": "b"}]) == "[1, true, null, [a: 'b']]"
