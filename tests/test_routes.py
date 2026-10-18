"""Static publication-route analysis across alternative Nextflow routes."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from nf_splice.inspectors.routes import (
    CoverageStatus,
    analyse_routes,
    example_path,
    glob_to_regex,
)

FIXTURE = Path(__file__).parent / "fixtures" / "multi-route-0.3.0"
NF_CORE_DEFAULT_PATH = (
    "${params.outdir}/${task.process.tokenize(':')[-1].tokenize('_')[0].toLowerCase()}"
)


def _repository(tmp_path: Path) -> Path:
    root = tmp_path / "pipeline"
    shutil.copytree(FIXTURE / "repository", root)
    return root


def test_every_route_is_traced_with_its_conditions(tmp_path: Path) -> None:
    analysis = analyse_routes(_repository(tmp_path))
    published = {(item.instance, item.emit): item for item in analysis.published}

    assert set(published) == {
        ("FASTQC", "html"),
        ("FASTQC", "zip"),
        ("STAR_ALIGN", "bam"),
        ("STAR_ALIGN", "log_final"),
        ("HISAT2_ALIGN", "bam"),
        ("SALMON_QUANT", "quant"),
        ("MULTIQC", "report"),
    }
    assert published[("STAR_ALIGN", "bam")].conditions == (
        ("params.aligner == 'star'",),
    )
    assert published[("HISAT2_ALIGN", "bam")].conditions == (
        ("not (params.aligner == 'star')",),
    )
    assert published[("FASTQC", "html")].conditions == (("!params.skip_qc",),)
    assert published[("SALMON_QUANT", "quant")].conditions == (("params.run_salmon",),)
    assert published[("MULTIQC", "report")].conditions == ()
    assert all(
        item.status is CoverageStatus.CONFIRMED_FROM_CODE for item in analysis.published
    )
    # Config withName rules and per-sample directories (meta.id).
    salmon = published[("SALMON_QUANT", "quant")]
    assert salmon.published_glob == "salmon/{sample}/quant.sf"
    assert salmon.publication is not None
    assert salmon.publication.source == "config"
    assert published[("HISAT2_ALIGN", "bam")].published_glob == "hisat2/{sample}.bam"


def test_declared_outputs_are_not_published_outputs(tmp_path: Path) -> None:
    analysis = analyse_routes(_repository(tmp_path))
    unpublished = {(item.instance, item.emit) for item in analysis.unpublished}

    # An intermediate with no publishDir, a pattern-filtered file, a file a
    # selector's pattern excludes and versions.yml dropped by saveAs.
    assert ("SAMTOOLS_SORT", "bam") in unpublished
    assert ("STAR_ALIGN", "junctions") in unpublished
    assert ("HISAT2_ALIGN", "summary") in unpublished
    assert ("SALMON_QUANT", "versions") in unpublished
    assert all(
        item.status is CoverageStatus.NOT_PUBLISHED for item in analysis.unpublished
    )


def test_nf_core_default_rule_and_selector_filters(tmp_path: Path) -> None:
    (tmp_path / "modules").mkdir()
    (tmp_path / "main.nf").write_text(
        """include { FASTQC } from './modules/fastqc'
include { TRIMGALORE as TRIM } from './modules/trim'
include { CUSTOM_DUMP } from './modules/dump'
workflow PIPELINE {
    main:
    FASTQC(reads)
    if (params.trim) TRIM(reads)
    CUSTOM_DUMP(versions)
}
workflow { PIPELINE() }
""",
        encoding="utf-8",
    )
    (tmp_path / "modules" / "fastqc.nf").write_text(
        """process FASTQC {
    output:
    tuple val(meta), path("*.html"), emit: html
    tuple val(meta), path("*.zip") , emit: zip
    path "versions.yml"            , emit: versions
    when:
    task.ext.when == null || task.ext.when
}
""",
        encoding="utf-8",
    )
    (tmp_path / "modules" / "trim.nf").write_text(
        """process TRIMGALORE {
    output:
    tuple val(meta), path("*.fq.gz"), emit: reads
    tuple val(meta), path("*report.txt"), emit: log
}
""",
        encoding="utf-8",
    )
    (tmp_path / "modules" / "dump.nf").write_text(
        """process CUSTOM_DUMP {
    output:
    path "software_versions.yml", emit: yml
}
""",
        encoding="utf-8",
    )
    (tmp_path / "nextflow.config").write_text(
        """process {
    publishDir = [
        path: { "DEFAULT_PATH" },
        mode: params.publish_dir_mode,
        saveAs: { filename -> filename.equals('versions.yml') ? null : filename }
    ]
    withName: '.*:TRIM' {
        publishDir = [
            [
                path: { "${params.outdir}/trimgalore" },
                pattern: "*.fq.gz",
                enabled: params.save_trimmed
            ],
            [ path: { "${params.outdir}/trimgalore/logs" }, pattern: "*.txt" ]
        ]
    }
    withName: CUSTOM_DUMP {
        publishDir = [
            path: { "${params.outdir}/pipeline_info" },
            pattern: '*.yml',
            saveAs: { name -> "renamed_${name}" }
        ]
    }
}
""".replace("DEFAULT_PATH", NF_CORE_DEFAULT_PATH),
        encoding="utf-8",
    )
    analysis = analyse_routes(tmp_path)
    published = {(item.instance, item.emit): item for item in analysis.published}

    html = published[("FASTQC", "html")]
    assert html.published_glob == "fastqc/{sample}.html"
    assert html.status is CoverageStatus.INFERRED_UNVERIFIED
    assert any("default publishDir" in note for note in html.notes)
    assert ("FASTQC", "versions") not in published
    reads = published[("TRIM", "reads")]
    assert reads.published_glob == "trimgalore/{sample}.fq.gz"
    assert reads.conditions == (
        ("params.trim", "publishDir enabled: params.save_trimmed"),
    )
    assert (
        published[("TRIM", "log")].published_glob
        == "trimgalore/logs/{sample}report.txt"
    )
    dump = published[("CUSTOM_DUMP", "yml")]
    assert dump.status is CoverageStatus.INFERRED_UNVERIFIED
    assert any("saveAs" in note for note in dump.notes)


def test_unreached_and_dynamic_routes_are_not_claimed(tmp_path: Path) -> None:
    (tmp_path / "main.nf").write_text(
        """process USED {
    publishDir params.custom_dir
    output:
    path "a.txt", emit: a
}
process UNUSED {
    publishDir "${params.outdir}/unused"
    output:
    path "b.txt", emit: b
}
process DYNAMIC {
    publishDir "${params.outdir}/${params.run_name}/reports"
    output:
    path "c.txt", emit: c
}
workflow {
    USED()
    DYNAMIC()
}
""",
        encoding="utf-8",
    )
    published = {item.instance: item for item in analyse_routes(tmp_path).published}

    assert published["USED"].status is CoverageStatus.UNRESOLVED
    assert published["UNUSED"].status is CoverageStatus.NOT_REACHABLE
    assert published["UNUSED"].reachable is False
    assert published["DYNAMIC"].status is CoverageStatus.INFERRED_UNVERIFIED
    assert published["DYNAMIC"].published_glob == "*/reports/c.txt"


def test_comments_and_strings_do_not_create_routes(tmp_path: Path) -> None:
    (tmp_path / "main.nf").write_text(
        """// process FAKE { publishDir "x" }
/* workflow { FAKE() } */
process REAL {
    publishDir "${params.outdir}/real" // http://example.org/not-a-comment-end
    output:
    path "r.txt", emit: r
}
workflow {
    println "REAL() is mentioned in a string"
    REAL()
}
""",
        encoding="utf-8",
    )
    analysis = analyse_routes(tmp_path)
    assert [item.instance for item in analysis.published] == ["REAL"]
    assert analysis.published[0].invocations == ("main.nf:10",)


def test_glob_helpers_round_trip() -> None:
    pattern = glob_to_regex("star/{sample}.Aligned.*.{bam,cram}")
    assert pattern == r"^star/(?P<sample_id>[^/]+)\.Aligned\.[^/]+\.(?:bam|cram)$"
    assert re.match(pattern, example_path("star/{sample}.Aligned.*.{bam,cram}"))
