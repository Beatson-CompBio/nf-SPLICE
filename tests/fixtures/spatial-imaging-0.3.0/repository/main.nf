nextflow.enable.dsl = 2

include { XENIUM_PREPROCESS } from './modules/local/xenium_preprocess'
include { COSMX_PREPROCESS  } from './modules/local/cosmx_preprocess'
include { SEGMENT_CELLS     } from './modules/local/segment_cells'
include { QUANTIFY_CELLS    } from './modules/local/quantify_cells'
include { SPATIAL_REPORT    } from './modules/local/spatial_report'
include { WRITE_INDEX       } from './modules/local/write_index'

workflow {
    runs = Channel.fromPath(params.input)
        .splitCsv(header: true)
        .map { row -> tuple([id: row.sample], file(row.bundle)) }

    // One platform route runs per job.
    if (params.platform == 'xenium') {
        XENIUM_PREPROCESS(runs)
        images = XENIUM_PREPROCESS.out.morphology
    } else {
        COSMX_PREPROCESS(runs)
        images = COSMX_PREPROCESS.out.morphology
    }
    SEGMENT_CELLS(images)
    QUANTIFY_CELLS(SEGMENT_CELLS.out.masks)
    SPATIAL_REPORT(QUANTIFY_CELLS.out.matrix.collect())
    WRITE_INDEX(QUANTIFY_CELLS.out.matrix.collect())
}
