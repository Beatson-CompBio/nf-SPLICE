"""Release-path acceptance test for a clean realistic pipeline repository."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from nf_splice.cli import app

runner = CliRunner()


def _invoke(root: Path, *arguments: str) -> None:
    result = runner.invoke(app, [*arguments, "--repository", str(root)])
    assert result.exit_code == 0, result.output


def _write_clean_pipeline(root: Path) -> None:
    (root / "main.nf").write_text(
        """process REPORT {
    publishDir "${params.outdir}/reports"
    output:
    path "report.html", emit: report
}

workflow { REPORT() }
""",
        encoding="utf-8",
    )
    (root / "nextflow_schema.json").write_text(
        json.dumps(
            {
                "$defs": {
                    "analysis": {
                        "title": "Analysis",
                        "type": "object",
                        "properties": {
                            "threshold": {
                                "type": "number",
                                "description": "Analysis threshold.",
                                "default": 0.8,
                            }
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    module = root / "modules" / "local" / "tool"
    module.mkdir(parents=True)
    (module / "meta.yml").write_text(
        "name: tool\ntools:\n  - tool:\n      description: Example tool\n",
        encoding="utf-8",
    )
    (module / "main.nf").write_text(
        "process TOOL {\n  container 'quay.io/example/tool:1.0'\n}\n",
        encoding="utf-8",
    )
    (root / "modules.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "kind": "module",
                        "path": "modules/local/tool",
                        "namespace": "local",
                        "tool": "tool",
                        "name": "tool",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (root / "conf").mkdir()
    (root / "conf" / "local.config").write_text(
        "process { executor = 'local' }\nsingularity.enabled = true\n",
        encoding="utf-8",
    )
    (root / "nextflow.config").write_text(
        "profiles { local { includeConfig 'conf/local.config' } }\n",
        encoding="utf-8",
    )
    (root / "ro-crate-metadata.json").write_text(
        json.dumps(
            {
                "@context": "https://w3id.org/ro/crate/1.1/context",
                "@graph": [
                    {
                        "@id": "ro-crate-metadata.json",
                        "@type": "CreativeWork",
                        "about": {"@id": "./"},
                    },
                    {"@id": "./", "@type": "Dataset"},
                ],
            }
        ),
        encoding="utf-8",
    )


def test_cli_completes_clean_pipeline_to_validated_idempotent_bundle(
    tmp_path: Path,
) -> None:
    _write_clean_pipeline(tmp_path)
    inspected = runner.invoke(app, ["inspect", "--repository", str(tmp_path)])

    assert inspected.exit_code == 0
    assert "SPLICE tree: absent" in inspected.output
    assert not (tmp_path / "splice").exists()

    _invoke(
        tmp_path,
        "init",
        "--name",
        "Reference Pipeline",
        "--pipeline-version",
        "1.0.0",
        "--repository-url",
        "https://github.com/org/reference",
    )
    _invoke(tmp_path, "configure", "inputs", "--set", "threshold=user-configurable")
    _invoke(tmp_path, "configure", "components", "--accept-detected")

    unresolved = tmp_path / "unresolved-outputs.json"
    discovered = runner.invoke(
        app,
        [
            "configure",
            "outputs",
            "--repository",
            str(tmp_path),
            "--contract-version",
            "1.0.0",
            "--export-unresolved",
            str(unresolved),
        ],
    )
    assert discovered.exit_code == 2
    candidates = json.loads(unresolved.read_text(encoding="utf-8"))
    assert candidates
    output_arguments = ["configure", "outputs"]
    for index, candidate in enumerate(candidates):
        candidate_id = candidate["id"]
        if index:
            output_arguments.extend(
                [
                    "--set",
                    f"{candidate_id}.action=reject",
                    "--set",
                    f"{candidate_id}.reason=Duplicate discovery evidence",
                ]
            )
            continue
        for field, value in (
            ("key", "report"),
            ("title", "Report"),
            ("description", "Completed run report."),
            ("category", "job_report"),
            ("formats", "html"),
            ("scopes", "job"),
            ("entity_types", "file"),
            ("path_patterns", r"^reports/report\.html$"),
        ):
            output_arguments.extend(["--set", f"{candidate_id}.{field}={value}"])
    _invoke(tmp_path, *output_arguments)

    _invoke(
        tmp_path,
        "configure",
        "execution-profiles",
        "--set",
        "profile:local.type=development",
        "--set",
        "profile:local.description=Supported local execution.",
        "--set",
        "profile:local.executor=local",
        "--set",
        "profile:local.container_engine=singularity",
        "--set",
        "profile:local.config_source=conf/local.config",
    )
    _invoke(
        tmp_path,
        "configure",
        "provenance",
        "--set",
        "provenance.include=true",
    )
    _invoke(tmp_path, "plan", "all", "--json")
    _invoke(tmp_path, "build", "all", "--check", "--non-interactive", "--json")
    _invoke(tmp_path, "build", "all", "--non-interactive")
    first = {
        path.relative_to(tmp_path / "splice").as_posix(): path.read_bytes()
        for path in (tmp_path / "splice").rglob("*")
        if path.is_file()
    }
    _invoke(tmp_path, "validate", "--json")
    _invoke(tmp_path, "build", "all", "--non-interactive")
    second = {
        path.relative_to(tmp_path / "splice").as_posix(): path.read_bytes()
        for path in (tmp_path / "splice").rglob("*")
        if path.is_file()
    }

    assert second == first
    assert (tmp_path / "ro-crate-metadata.json").is_file()
    assert (tmp_path / "conf" / "local.config").is_file()
