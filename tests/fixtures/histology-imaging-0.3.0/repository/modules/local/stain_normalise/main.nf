process STAIN_NORMALISE {
    tag "$meta.id"
    container 'ghcr.io/example-org/histotools:1.2.0'
    publishDir "${params.outdir}/normalised", mode: 'copy'

    input:
    tuple val(meta), path(image)

    output:
    tuple val(meta), path("${meta.id}.normalised.ome.tiff"), emit: image

    script:
    "stain-normalise --method ${params.normalisation} ${image} ${meta.id}.normalised.ome.tiff"
}
