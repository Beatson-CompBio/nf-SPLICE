"""Acceptance tests for reviewed execution profiles and safe configs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nf_splice.domain import DecisionStatus
from nf_splice.services import (
    ApplicationService,
    ExecutionProfileError,
    StaticChangeKind,
    load_repository_document,
    unresolved_execution_profiles,
)


def _repository(root: Path, local_config: str | None = None) -> ApplicationService:
    service = ApplicationService()
    service.initialise(
        root,
        name="pipeline",
        version="1.0.0",
        repository_url="https://github.com/org/pipeline",
    )
    (root / "conf").mkdir()
    (root / "conf" / "local.config").write_text(
        local_config or "process { executor = 'local' }\nsingularity.enabled = true\n",
        encoding="utf-8",
    )
    (root / "conf" / "slurm.config").write_text(
        "process { executor = 'slurm' }\nsingularity.enabled = true\n",
        encoding="utf-8",
    )
    (root / "nextflow.config").write_text(
        "profiles {\n"
        "  local { includeConfig 'conf/local.config' }\n"
        "  cluster { includeConfig 'conf/slurm.config' }\n"
        "}\n",
        encoding="utf-8",
    )
    return service


def test_detected_profiles_require_selection_and_render_byte_identically(
    tmp_path: Path,
) -> None:
    service = _repository(tmp_path)
    document = service.discover_execution_profiles(tmp_path)

    assert not (tmp_path / "splice" / "execution-profiles.json").exists()
    assert [item.id for item in unresolved_execution_profiles(document)] == [
        "profile:cluster",
        "profile:local",
    ]
    assert all(
        item.status is DecisionStatus.CANDIDATE
        for item in document.decisions
        if item.id.startswith("profile:")
    )

    service.review_execution_profile(
        tmp_path,
        "profile:local",
        profile_type="development",
        description="Supported local execution.",
        executor="local",
        container_engine="singularity",
        config_source="conf/local.config",
    )
    service.reject_execution_profile(
        tmp_path, "profile:cluster", "Cluster environment is not supported."
    )
    preview = service.plan_execution_profiles(tmp_path)
    assert [item.path.name for item in preview.changes] == [
        "execution-profiles.json",
        "profile-local-6c6f63616c.config",
    ]
    assert all(item.kind is StaticChangeKind.CREATE for item in preview.changes)

    built = service.build_execution_profiles(tmp_path)
    repeated = service.plan_execution_profiles(tmp_path)
    profiles = json.loads((tmp_path / "splice" / "execution-profiles.json").read_text())

    assert built.wrote
    assert all(item.kind is StaticChangeKind.UNCHANGED for item in repeated.changes)
    assert profiles["profiles"] == [
        {
            "id": "profile-local-6c6f63616c",
            "name": "Local",
            "description": "Supported local execution.",
            "type": "development",
            "engine": "nextflow",
            "executor": "local",
            "container_engine": "singularity",
            "config": "configs/profile-local-6c6f63616c.config",
        }
    ]
    assert (
        tmp_path / "splice" / "configs" / "profile-local-6c6f63616c.config"
    ).read_bytes() == (tmp_path / "conf" / "local.config").read_bytes()


def test_source_config_must_be_selected_explicitly(tmp_path: Path) -> None:
    service = _repository(tmp_path)
    service.discover_execution_profiles(tmp_path)

    with pytest.raises(ExecutionProfileError, match="explicitly selected"):
        service.review_execution_profile(
            tmp_path,
            "profile:local",
            profile_type="development",
            description="Supported local execution.",
            executor="local",
            container_engine="singularity",
        )


def test_multiple_profiles_may_share_type_and_executor_with_unique_generated_ids(
    tmp_path: Path,
) -> None:
    service = _repository(tmp_path)
    (tmp_path / "conf" / "slurm.config").write_text(
        "process { executor = 'local' }\nsingularity.enabled = true\n",
        encoding="utf-8",
    )
    service.discover_execution_profiles(tmp_path)
    service.review_execution_profile(
        tmp_path,
        "profile:local",
        profile_type="production",
        description="Production profile for interactive workloads.",
        executor="local",
        container_engine="singularity",
        config_source="conf/local.config",
    )
    service.review_execution_profile(
        tmp_path,
        "profile:cluster",
        profile_type="production",
        description="Production profile for scheduled workloads.",
        executor="local",
        container_engine="singularity",
        config_source="conf/slurm.config",
    )

    service.build_execution_profiles(tmp_path)
    profiles = json.loads(
        (tmp_path / "splice" / "execution-profiles.json").read_text()
    )["profiles"]

    assert len(profiles) == 2
    assert {item["type"] for item in profiles} == {"production"}
    assert {item["executor"] for item in profiles} == {"local"}
    assert {item["id"] for item in profiles} == {
        "profile-cluster-636c7573746572",
        "profile-local-6c6f63616c",
    }


def test_incomplete_and_conflicting_profiles_require_explicit_resolution(
    tmp_path: Path,
) -> None:
    service = _repository(tmp_path)
    (tmp_path / "conf" / "local.config").write_text(
        "process { executor = 'local'; executor = 'slurm' }\n"
        "docker.enabled = true\n"
        "singularity.enabled = true\n",
        encoding="utf-8",
    )
    document = service.discover_execution_profiles(tmp_path)
    decisions = {item.id: item for item in document.decisions}

    assert decisions["profile:local"].status is DecisionStatus.CONFLICT
    with pytest.raises(ExecutionProfileError, match="explicitly selected executor"):
        service.review_execution_profile(
            tmp_path,
            "profile:local",
            profile_type="test",
            description="Resolved test environment.",
            config_source="conf/local.config",
        )
    service.review_execution_profile(
        tmp_path,
        "profile:local",
        profile_type="test",
        description="Resolved test environment.",
        executor="local",
        container_engine="docker",
        config_source="conf/local.config",
    )


@pytest.mark.parametrize(
    "unsafe",
    [
        "password = 'embedded'\n",
        "params.cache = '/Users/alice/cache'\n",
        "process.clusterOptions = '--account=private-project'\n",
        "params.dataset = 'demo_testdata.csv'\n",
    ],
)
def test_unsafe_production_config_values_block_all_writes(
    tmp_path: Path, unsafe: str
) -> None:
    service = _repository(
        tmp_path,
        "process { executor = 'local' }\nsingularity.enabled = true\n" + unsafe,
    )
    service.discover_execution_profiles(tmp_path)
    service.review_execution_profile(
        tmp_path,
        "profile:local",
        profile_type="production",
        description="Production environment.",
        executor="local",
        container_engine="singularity",
        config_source="conf/local.config",
    )
    service.reject_execution_profile(tmp_path, "profile:cluster", "Not supported.")

    with pytest.raises(ExecutionProfileError, match="unsafe execution config"):
        service.plan_execution_profiles(tmp_path)
    assert not (tmp_path / "splice" / "execution-profiles.json").exists()
    assert not (tmp_path / "splice" / "configs").exists()


def test_unknown_config_siblings_are_preserved_and_recognized_targets_need_review(
    tmp_path: Path,
) -> None:
    service = _repository(tmp_path)
    service.discover_execution_profiles(tmp_path)
    service.review_execution_profile(
        tmp_path,
        "profile:local",
        profile_type="development",
        description="Local environment.",
        executor="local",
        container_engine="singularity",
        config_source="conf/local.config",
    )
    service.reject_execution_profile(tmp_path, "profile:cluster", "Not supported.")
    configs = tmp_path / "splice" / "configs"
    configs.mkdir()
    unknown = configs / "notes.txt"
    unknown.write_text("preserve me\n", encoding="utf-8")
    target = configs / "profile-local-6c6f63616c.config"
    target.write_text("process { executor = 'other' }\n", encoding="utf-8")

    with pytest.raises(ExecutionProfileError, match="replace-existing"):
        service.build_execution_profiles(tmp_path)
    result = service.build_execution_profiles(tmp_path, replace_existing=True)

    assert result.wrote
    assert unknown.read_text(encoding="utf-8") == "preserve me\n"
    assert target.read_bytes() == (tmp_path / "conf" / "local.config").read_bytes()
    assert unresolved_execution_profiles(load_repository_document(tmp_path)) == ()


def test_reviewed_scientific_parameter_overrides_are_not_copied(
    tmp_path: Path,
) -> None:
    service = _repository(
        tmp_path,
        "process { executor = 'local' }\n"
        "singularity.enabled = true\n"
        "params.threshold = 0.5\n",
    )
    (tmp_path / "nextflow_schema.json").write_text(
        json.dumps(
            {
                "$defs": {
                    "analysis": {
                        "title": "Analysis",
                        "properties": {
                            "threshold": {
                                "type": "number",
                                "description": "Scientific threshold.",
                            }
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    service.discover_inputs(tmp_path)
    service.review_input(tmp_path, "input:threshold", "user-configurable")
    service.discover_execution_profiles(tmp_path)
    service.review_execution_profile(
        tmp_path,
        "profile:local",
        profile_type="development",
        description="Local environment.",
        executor="local",
        container_engine="singularity",
        config_source="conf/local.config",
    )
    service.reject_execution_profile(tmp_path, "profile:cluster", "Not supported.")

    with pytest.raises(ExecutionProfileError, match="scientific parameter override"):
        service.plan_execution_profiles(tmp_path)
