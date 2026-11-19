process HISAT2_ALIGN {
    container 'quay.io/biocontainers/hisat2:2.2.1--h87f3376_4'

    input:
    tuple val(meta), path(reads)

    output:
    tuple val(meta), path("*.bam"), emit: bam
    tuple val(meta), path("*.hisat2.summary.log"), emit: summary

    script:
    "hisat2 -1 ${reads[0]}"
}
