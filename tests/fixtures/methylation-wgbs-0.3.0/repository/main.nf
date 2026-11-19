nextflow.enable.dsl = 2

include { METHYLATION } from './subworkflows/local/methylation'
include { SUMMARISE   } from './modules/local/summarise/main'

workflow {
    reads = Channel.fromPath(params.input)
        .splitCsv(header: true)
        .map { row -> [[id: row.sample], [file(row.fastq_1), file(row.fastq_2)]] }
    METHYLATION(reads, file(params.genome))
    SUMMARISE(METHYLATION.out.calls.map { meta, bed -> bed }.collect())
}
