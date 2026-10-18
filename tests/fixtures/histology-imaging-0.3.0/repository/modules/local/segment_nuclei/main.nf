process SEGMENT_NUCLEI {
    tag "$meta.id"
    container 'ghcr.io/example-org/stardist:0.9.1'
    publishDir "${params.outdir}/masks", mode: 'copy', enabled: params.save_masks

    input:
    tuple val(meta), path(image)

    output:
    tuple val(meta), path("${meta.id}.nuclei.ome.tiff"), emit: masks

    script:
    "segment-nuclei --tile ${params.tile_size} ${image} ${meta.id}.nuclei.ome.tiff"
}
