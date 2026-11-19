process COSMX_PREPROCESS {
    container 'quay.io/example/spatial-tools:1.2.0'
    publishDir "${params.outdir}/preprocess/cosmx", mode: 'copy', pattern: '*.ome.tif'

    input:
    tuple val(meta), path(flatfiles)

    output:
    tuple val(meta), path("*.morphology.ome.tif"), emit: morphology
    tuple val(meta), path("*.transcripts.parquet"), emit: transcripts

    script:
    "spatial-tools cosmx ${flatfiles} --prefix ${meta.id}"
}
