"""S01: a new pipeline authored end to end through the non-interactive CLI."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from layer_fixtures import write_pipeline
from nf_splice.cli import app

runner = CliRunner()


def _ok(root: Path, *arguments: str) -> str:
    result = runner.invoke(
        app, ["--user", "Ada", *arguments, "--repository", str(root)]
    )
    assert result.exit_code == 0, result.output
    return result.output


def author_with_cli(root: Path) -> None:
    """Author every layer with explicit, reproducible CLI decisions."""
    write_pipeline(root)
    (root / "nextflow.config").write_text(
        "manifest {\n    name = 'reference'\n    version = '1.0.0'\n"
        "    homePage = 'https://github.com/org/reference'\n"
        "    description = 'Reference pipeline.'\n}\n"
        "profiles { local { includeConfig 'conf/local.config' } }\n",
        encoding="utf-8",
    )
    _ok(root, "init", "--accept-detected", "--contract-version", "1.0.0")
    _ok(
        root,
        "configure",
        "identity",
        "--add-assay",
        "polya_rnaseq",
        "--assay-rationale",
        "The reference pipeline quantifies poly(A)-selected RNA-seq libraries.",
    )
    _ok(
        root,
        "configure",
        "inputs",
        "--set",
        "threshold=user,agent",
        "--set",
        "outdir=platform",
    )
    # The catalogue starts empty (ADR-0068): describe the output, then refine it.
    output = root / ".splice-local" / "report-output.yaml"
    output.parent.mkdir(exist_ok=True)
    output.write_text(
        "key: report\ntitle: Report\ndescription: Draft.\ncategory: report\n"
        "formats: [html]\nscopes: [job]\nentity_types: [file]\n"
        "path_patterns: ['^reports/report\\.html$']\n",
        encoding="utf-8",
    )
    _ok(root, "configure", "outputs", "--add-output", str(output))
    _ok(
        root,
        "configure",
        "outputs",
        "--set",
        "report.description=Job report.",
        "--set",
        "report.category=job_report",
    )
    _ok(root, "configure", "components", "--require-downloadable", "false")
    _ok(
        root,
        "configure",
        "execution-profiles",
        "--set",
        "default.type=development",
        "--set",
        "default.description=Local development.",
        "--set",
        "default.config_adopt=conf/local.config",
        "--default",
        "default",
    )
    _ok(
        root,
        "configure",
        "identity",
        "--set",
        "licence=MIT",
        "--set",
        "released_at=2026-10-15T10:00:00Z",
    )
    _ok(root, "configure", "provenance", "--strategy", "generated")


def test_cli_completes_a_new_pipeline_to_a_validated_idempotent_bundle(
    tmp_path: Path,
) -> None:
    inspected = runner.invoke(app, ["inspect", "--repository", str(tmp_path)])
    assert "SPLICE tree: absent" in inspected.output
    author_with_cli(tmp_path)

    plan = json.loads(_ok(tmp_path, "plan", "--json"))
    assert plan["ready"] and plan["blockers"] == []
    built = _ok(tmp_path, "build", "all")
    assert "Built" in built
    assert "Valid SPLICE bundle" in _ok(tmp_path, "validate")
    assert "byte-identical" in _ok(tmp_path, "build", "all")

    splice = tmp_path / "splice"
    assert not (splice / "nf-splice.yaml").exists()
    assert not (splice / "outputs.json").exists()
    bundle = json.loads((splice / "bundle.json").read_text(encoding="utf-8"))
    assert bundle["pipeline"]["name"] == "reference"
    assert bundle["pipeline"]["description"] == "Reference pipeline."

    publish = tmp_path / "results"
    (publish / "reports").mkdir(parents=True)
    (publish / "reports" / "report.html").write_text("<html/>\n", encoding="utf-8")
    job = tmp_path / "job.json"
    job.write_text(json.dumps({"job_id_short": "A001"}), encoding="utf-8")
    _ok(
        tmp_path,
        "analysis-output",
        "generate",
        "--publish-directory",
        str(publish),
        "--job-metadata",
        str(job),
        "--output-directory",
        str(publish),
    )
    report = runner.invoke(
        app,
        [
            "analysis-output",
            "validate",
            str(publish / "analysis_output.json"),
            "--repository",
            str(tmp_path),
        ],
    )
    assert report.exit_code == 0, report.output
    document = json.loads((publish / "analysis_output.json").read_text())
    assert [item["scope"] for item in document["files"]] == ["job"]
