process SAMTOOLS_SORT {
    container 'quay.io/biocontainers/samtools:1.21--h50ea8bc_0'

    input:
    tuple val(meta), path(bam)

    output:
    tuple val(meta), path("*.sorted.bam"), emit: bam

    script:
    "samtools sort ${bam}"
}
