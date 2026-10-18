process EXTRACT_FEATURES {
    tag "$meta.id"
    container 'ghcr.io/example-org/histotools:1.2.0'
    publishDir "${params.outdir}/features", mode: 'copy'

    input:
    tuple val(meta), path(masks), path(image)

    output:
    tuple val(meta), path("${meta.id}.nuclei.parquet"), emit: features

    script:
    "nuclear-features --min-area ${params.min_area_px} ${masks} ${image} ${meta.id}.nuclei.parquet"
}
