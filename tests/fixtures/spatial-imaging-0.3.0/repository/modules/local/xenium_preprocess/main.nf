process XENIUM_PREPROCESS {
    container 'quay.io/example/spatial-tools:1.2.0'
    publishDir "${params.outdir}/preprocess/xenium", mode: 'copy', pattern: '*.ome.tif'

    input:
    tuple val(meta), path(bundle)

    output:
    tuple val(meta), path("*.morphology.ome.tif"), emit: morphology
    tuple val(meta), path("*.transcripts.parquet"), emit: transcripts

    script:
    "spatial-tools xenium ${bundle} --prefix ${meta.id}"
}
