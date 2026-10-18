"""Execution profiles: reviewed default, adopted and generated configs."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

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


def _profiles(root: Path, profiles: list[dict[str, Any]], default: str | None) -> None:
    from layer_fixtures import edit_draft_file

    def change(data: dict[str, Any]) -> None:
        data["profiles"] = profiles
        data["default_profile"] = default

    edit_draft_file(root, "execution-profiles", change)


def _profile(identifier: str, **values: Any) -> dict[str, Any]:
    return {
        "id": identifier,
        "name": identifier.title(),
        "description": f"{identifier} profile.",
        "type": "development",
        "engine": "nextflow",
        "executor": "local",
        "container_engine": "singularity",
        "config": {"draft": f"{identifier}.draft.config"},
    } | values


def test_init_seeds_a_usable_default_profile_and_native_config(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    assert {item.id for item in discover_execution(tmp_path)} == {
        "profile:local",
        "profile:test",
    }
    config = tmp_path / config_draft_path("default")
    text = config.read_text(encoding="utf-8")
    assert USER_SECTION in text and PLATFORM_SECTION in text
    assert "singularity {" in text and "executor = 'local'" in text
    codes = _codes(tmp_path)
    # Detected repository profiles are evidence; nothing waits for them.
    assert "pending_candidate" not in codes
    assert {"missing_required"} <= codes  # description and type are unknown
    # Re-running never touches the YAML or the config.
    draft = tmp_path / ".splice-local/drafts/execution-profiles.draft.yaml"
    before = (draft.read_bytes(), config.read_bytes())
    discover_execution(tmp_path)
    assert (draft.read_bytes(), config.read_bytes()) == before


def test_manually_authored_profiles_and_configs_publish_without_reviews(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    discover_execution(tmp_path)
    configs = tmp_path / ".splice-local/drafts/configs"
    (configs / "default.draft.config").unlink()
    (configs / "archer2.draft.config").write_text(
        "// Archer2 profile written by hand\n"
        "process {\n    executor = 'slurm'\n    withLabel: 'process_high' {\n"
        "        cpus = 16\n    }\n}\n"
        f"{USER_SECTION}\nparams {{\n    genome = 'GRCm39'\n}}\n"
        f"{PLATFORM_SECTION}\nparams {{\n    max_cpus = 128\n}}\n",
        encoding="utf-8",
    )
    (configs / "laptop.draft.config").write_text(
        "process.executor = 'local'\n", encoding="utf-8"
    )
    _profiles(
        tmp_path,
        [
            _profile("archer2", type="production", executor="slurm"),
            _profile("laptop"),
            _profile("repository", config={"adopt": "conf/local.config"}),
        ],
        "archer2",
    )
    validation = validate_execution_draft(tmp_path)
    assert validation.ready, validation.issues
    catalogue = json.loads(validation.files["execution-profiles.json"])
    assert catalogue["default_profile"] == "archer2"
    assert {item["id"]: item["config_strategy"] for item in catalogue["profiles"]} == {
        "archer2": "authored",
        "laptop": "authored",
        "repository": "adopted",
    }
    archer2 = validation.files["configs/archer2.config"].decode("utf-8")
    assert "withLabel: 'process_high'" in archer2 and "cpus = 16" in archer2
    assert "nf-SPLICE draft" not in archer2
    assert validation.files["configs/repository.config"] == LOCAL
    # The laptop config has no parameter sections: a warning, not a blocker.
    assert "missing_sections" in _codes(tmp_path)
    # A later edit in an editor is what validation reads next.
    (configs / "archer2.draft.config").write_text(
        archer2.replace("cpus = 16", "cpus = 32"), encoding="utf-8"
    )
    final = validate_execution_draft(tmp_path).files["configs/archer2.config"]
    assert b"cpus = 32" in final


def test_a_profile_may_declare_no_container_engine(tmp_path: Path) -> None:
    # ADR-0070: nf-splice authors bundles; the runtime is the site's decision.
    _repository(tmp_path)
    discover_execution(tmp_path)
    configs = tmp_path / ".splice-local/drafts/configs"
    (configs / "default.draft.config").write_text(
        "process {\n    executor = 'local'\n}\n"
        f"{USER_SECTION}\nparams {{\n    genome = 'GRCm39'\n}}\n"
        f"{PLATFORM_SECTION}\nparams {{\n}}\n",
        encoding="utf-8",
    )
    _profiles(tmp_path, [_profile("default", container_engine=None)], "default")
    validation = validate_execution_draft(tmp_path)
    assert validation.ready, validation.issues
    catalogue = json.loads(validation.files["execution-profiles.json"])
    assert catalogue["profiles"][0]["container_engine"] is None


def test_a_supplied_engine_is_still_checked(tmp_path: Path) -> None:
    _repository(tmp_path)
    discover_execution(tmp_path)
    _profiles(tmp_path, [_profile("default", container_engine="kubernetes")], "default")
    assert "vocabulary" in _codes(tmp_path)


def test_an_engine_the_profile_config_does_not_enable_warns(tmp_path: Path) -> None:
    # conf/local.config enables singularity; naming docker is a real conflict.
    _repository(tmp_path)
    discover_execution(tmp_path)
    _profiles(
        tmp_path,
        [_profile("repository", config={"adopt": "conf/local.config"},
                  container_engine="docker")],
        "repository",
    )
    issues = validate_execution_draft(tmp_path).issues
    conflict = [item for item in issues if item.code == "engine_conflict"]
    assert conflict and conflict[0].severity.value == "warning"
    assert "singularity" in conflict[0].message


def test_review_profile_can_leave_the_engine_unset(tmp_path: Path) -> None:
    import yaml

    _repository(tmp_path)
    discover_execution(tmp_path)
    review_profile(
        tmp_path,
        "profile:local",
        ADA,
        profile_type="development",
        description="Local work.",
        executor="local",
    )
    draft = tmp_path / ".splice-local/drafts/execution-profiles.draft.yaml"
    data = yaml.safe_load(draft.read_text(encoding="utf-8"))
    added = [item for item in data["profiles"] if item["id"] == "local"]
    assert added and added[0]["container_engine"] is None


def test_parameter_sections_are_checked_against_input_policies(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    discover_execution(tmp_path)
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
    text = (tmp_path / config_draft_path("cluster")).read_text(encoding="utf-8")
    assert "    genome = 'GRCm39'" in text and "    max_cpus = 8" in text
    _profiles(tmp_path, [_profile("cluster", type="production")], "cluster")
    issues = validate_execution_draft(tmp_path).issues
    flagged = {
        item.message.split("'")[1]
        for item in issues
        if item.code == "section_policy" and item.severity.value == "error"
    }
    assert flagged == {"max_cpus", "genome"}
    assert "secret_literal" in {item.code for item in issues}


def test_config_files_are_written_safely_and_conflicts_are_refused(
    tmp_path: Path,
) -> None:
    from nf_splice.drafts import DraftConflictError
    from nf_splice.layers.execution import read_config_draft, write_config_draft

    _repository(tmp_path)
    discover_execution(tmp_path)
    current = read_config_draft(tmp_path, "default")
    assert current["exists"] and USER_SECTION in current["text"]
    edited = current["text"].replace("process {", "process {\n    maxRetries = 2")
    result = write_config_draft(
        tmp_path, "default", edited, ADA, expected_sha256=current["sha256"]
    )
    assert result.wrote and "+    maxRetries = 2" in result.diff
    with pytest.raises(DraftConflictError, match="changed on disk"):
        write_config_draft(
            tmp_path, "default", edited, ADA, expected_sha256=current["sha256"]
        )
    with pytest.raises(LayerError, match="secret"):
        write_config_draft(
            tmp_path,
            "extra",
            "params { api_token = 'abc' }\npassword = 'hunter2'\n",
            ADA,
            expected_sha256=None,
        )
    assert not (tmp_path / config_draft_path("extra")).exists()
    with pytest.raises(LayerError, match="config name"):
        write_config_draft(tmp_path, "../escape", "x", ADA, expected_sha256=None)


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
    _profiles(
        tmp_path,
        [_profile("local", type="production", config={"adopt": "conf/local.config"})],
        "local",
    )
    validation = validate_execution_draft(tmp_path)
    assert not validation.ready
    assert any(message in item.message for item in validation.issues)


def test_parameter_and_environment_accounts_are_not_literals(tmp_path: Path) -> None:
    config = (
        b'process { clusterOptions = { "--account=${params.budget}" } }\n'
        b"params { budget = params.budget ?: null }\n"
    )
    _repository(tmp_path, config)
    discover_execution(tmp_path)
    _profiles(
        tmp_path,
        [_profile("local", config={"adopt": "conf/local.config"})],
        "local",
    )
    assert not any(
        "HPC account" in item.message
        for item in validate_execution_draft(tmp_path).issues
    )


def test_optional_review_conveniences_check_detected_values(tmp_path: Path) -> None:
    _repository(tmp_path)
    discover_execution(tmp_path)
    common: dict[str, Any] = {
        "profile_type": "development",
        "description": "x",
        "container_engine": "singularity",
    }
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
    review_profile(
        tmp_path,
        "profile:local",
        ADA,
        executor="local",
        config_source="conf/local.config",
        **common,
    )
    reject_profile(tmp_path, "profile:test", "CI only", ADA)
    assert pending_profiles(tmp_path) == ()
    add_slurm_default_candidate(tmp_path, ADA)
    set_default_profile(tmp_path, "splice-slurm", ADA)
    text = (tmp_path / config_draft_path("splice-slurm")).read_text(encoding="utf-8")
    assert "executor = 'slurm'" in text and "deployment-managed: queue" in text
    with pytest.raises(LayerError, match="unknown execution profile"):
        set_default_profile(tmp_path, "profile-nope", ADA)
    assert groovy_literal("it's $HOME") == "'it\\'s \\$HOME'"
    assert groovy_literal([1, True, None, {"a": "b"}]) == "[1, true, null, [a: 'b']]"
