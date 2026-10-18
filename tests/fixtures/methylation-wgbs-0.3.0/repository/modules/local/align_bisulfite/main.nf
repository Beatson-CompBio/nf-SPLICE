process ALIGN_BISULFITE {
    tag "$meta.id"

    input:
    tuple val(meta), path(reads)
    path genome

    output:
    tuple val(meta), path("${meta.id}.bismark.bam"), emit: bam
    tuple val(meta), path("${meta.id}.bismark_report.txt"), emit: report

    script:
    "bismark --genome ${genome} -1 ${reads[0]} -2 ${reads[1]} --basename ${meta.id}.bismark"
}
