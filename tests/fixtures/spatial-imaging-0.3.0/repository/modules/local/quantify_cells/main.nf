process QUANTIFY_CELLS {
    container 'quay.io/example/spatial-tools:1.2.0'
    publishDir "${params.outdir}/quantification", mode: 'copy'

    input:
    tuple val(meta), path(masks)

    output:
    path "*.cell_by_gene.csv", emit: matrix

    script:
    "spatial-tools quantify ${masks} --out ${meta.id}.cell_by_gene.csv"
}
