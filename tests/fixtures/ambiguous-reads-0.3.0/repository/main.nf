nextflow.enable.dsl = 2

process ALIGN {
    tag "$meta.id"
    container 'quay.io/example/minimap2:2.28'
    publishDir "${params.outdir}/aligned", mode: 'copy'

    input:
    tuple val(meta), path(reads)
    path reference

    output:
    tuple val(meta), path("${meta.id}.bam"), emit: bam

    script:
    "minimap2 -a ${reference} ${reads} | samtools sort -o ${meta.id}.bam"
}

process COUNT_FEATURES {
    container 'quay.io/example/featurecounter:3.1'
    publishDir "${params.outdir}/counts", mode: 'copy'

    input:
    path bams
    path annotation

    output:
    path "feature_counts.tsv", emit: counts

    script:
    "count-features -a ${annotation} -o feature_counts.tsv ${bams}"
}

workflow {
    reads = Channel.fromPath(params.input)
        .splitCsv(header: true)
        .map { row -> [[id: row.sample], file(row.fastq)] }
    ALIGN(reads, file(params.reference))
    COUNT_FEATURES(ALIGN.out.bam.map { meta, bam -> bam }.collect(), file(params.annotation))
}
