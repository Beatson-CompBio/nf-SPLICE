"""Deterministic output-candidate discovery from repository and job evidence."""

from __future__ import annotations

from pathlib import Path

from nf_splice.domain import OutputScope
from nf_splice.inspectors import discover_output_candidates


def test_static_and_tree_discovery_merge_duplicates_and_generalise_samples(
    tmp_path: Path,
) -> None:
    (tmp_path / "main.nf").write_text(
        """process FASTP {
    publishDir "${params.outdir}/fastp"
    output:
    path "*.html", emit: report, optional: true
    path "*.html", emit: report, optional: true
}
workflow {
    output {
        reports = FASTP.out
    }
}
""",
        encoding="utf-8",
    )
    publish = tmp_path / "publish" / "fastp"
    publish.mkdir(parents=True)
    (publish / "sample_a.fastp.html").write_text("a", encoding="utf-8")
    (publish / "sample_b.fastp.html").write_text("b", encoding="utf-8")

    first = discover_output_candidates(tmp_path, publish_directory=publish.parent)
    second = discover_output_candidates(tmp_path, publish_directory=publish.parent)
    candidates = [item.candidate for item in first]

    assert first == second
    sample = next(
        item
        for item in candidates
        if item.path_pattern == r"^fastp/(?P<sample_id>[^/]+)\.fastp\.html$"
    )
    assert sample.likely_scope is OutputScope.SAMPLE
    reports = [item for item in candidates if item.suggested_key == "report"]
    assert len(reports) == 1
    assert reports[0].processes == ("FASTP",)
    assert reports[0].conditional is True


def test_example_tree_and_existing_output_catalogue_are_discovery_evidence(
    tmp_path: Path,
) -> None:
    tree = tmp_path / "example-tree.txt"
    tree.write_text(
        ".:\nfastp\n\n./fastp:\nsample_a.fastp.html\nsample_b.fastp.html\n",
        encoding="utf-8",
    )
    splice = tmp_path / "splice"
    splice.mkdir()
    (splice / "outputs.yaml").write_text(
        """catalogue_format_version: 0.3.0
schema_version: 1.0.0
pipeline: {}
outputs:
  - key: multiqc_report
    title: MultiQC report
    description: Aggregate quality-control report.
    category: quality_control
    scope: [job]
    entity_type: [file]
    format: [html]
    path_patterns: ['^multiqc/multiqc_report\\.html$']
""",
        encoding="utf-8",
    )
    discovered = discover_output_candidates(tmp_path, example_output_tree=tree)
    by_key = {item.candidate.suggested_key: item for item in discovered}

    assert by_key["fastp_fastp_html"].candidate.path_pattern == (
        r"^fastp/(?P<sample_id>[^/]+)\.fastp\.html$"
    )
    existing = by_key["multiqc_report"].candidate
    assert existing.suggested_description == "Aggregate quality-control report."
    assert existing.likely_scope is OutputScope.JOB
    sources = {
        evidence.provenance.source for item in discovered for evidence in item.evidence
    }
    assert {"example_output_tree", "existing_integration"} <= sources
