nextflow.enable.dsl = 2

params.slides    = null
params.outdir    = 'results'
params.tile_size = 512

process TILE_SLIDE {
    container 'quay.io/example/openslide-tiler:2.1.0'
    publishDir "${params.outdir}/tiles", mode: 'copy'

    input:
    path slide

    output:
    path "${slide.baseName}.tiles.zarr", emit: tiles

    script:
    "tile-slide ${slide} --size ${params.tile_size} --out ${slide.baseName}.tiles.zarr"
}

workflow {
    TILE_SLIDE(Channel.fromPath(params.slides))
}
