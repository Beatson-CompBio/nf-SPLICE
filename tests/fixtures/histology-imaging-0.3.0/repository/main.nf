nextflow.enable.dsl = 2

include { STAIN_NORMALISE  } from './modules/local/stain_normalise/main'
include { SEGMENT_NUCLEI   } from './modules/local/segment_nuclei/main'
include { EXTRACT_FEATURES } from './modules/local/extract_features/main'
include { SLIDE_REPORT     } from './modules/local/slide_report/main'

workflow {
    slides = Channel.fromPath(params.input)
        .splitCsv(header: true)
        .map { row -> [[id: row.slide_id], file(row.image)] }
    STAIN_NORMALISE(slides)
    SEGMENT_NUCLEI(STAIN_NORMALISE.out.image)
    EXTRACT_FEATURES(SEGMENT_NUCLEI.out.masks.join(STAIN_NORMALISE.out.image))
    SLIDE_REPORT(EXTRACT_FEATURES.out.features.map { meta, table -> table }.collect())
}
