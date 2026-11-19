process DEDUPLICATE {
    tag "$meta.id"

    input:
    tuple val(meta), path(bam)

    output:
    tuple val(meta), path("${meta.id}.deduplicated.bam"), emit: bam

    script:
    "deduplicate_bismark --bam ${bam} --output_dir . -o ${meta.id}"
}
