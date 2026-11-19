process SEGMENT_CELLS {
    label 'process_gpu'
    container 'quay.io/example/cellpose:3.0.10'
    publishDir "${params.outdir}/segmentation", mode: 'copy', pattern: '*_masks.ome.tif'

    input:
    tuple val(meta), path(image)

    output:
    tuple val(meta), path("*_masks.ome.tif"), emit: masks

    script:
    "cellpose --image ${image} --pretrained_model ${params.segmentation_model}"
}
