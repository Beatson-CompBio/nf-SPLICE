process CALL_METHYLATION {
    tag "$meta.id"

    input:
    tuple val(meta), path(bam)
    path genome

    output:
    tuple val(meta), path("${meta.id}_${params.context}.bedGraph"), emit: bedgraph

    script:
    "MethylDackel extract --minDepth ${params.min_depth} ${genome}/genome.fa ${bam} -o ${meta.id}"
}
