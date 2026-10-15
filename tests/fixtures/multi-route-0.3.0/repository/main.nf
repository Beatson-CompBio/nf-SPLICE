nextflow.enable.dsl = 2

include { FASTQC        } from './modules/local/fastqc'
include { STAR_ALIGN    } from './modules/local/star'
include { HISAT2_ALIGN  } from './modules/local/hisat2'
include { SAMTOOLS_SORT } from './modules/local/samtools_sort'
include { SALMON_QUANT  } from './modules/local/salmon'
include { MULTIQC       } from './modules/local/multiqc'

workflow {
    reads = Channel.fromFilePairs(params.input)

    // Quality control is optional.
    if (!params.skip_qc) {
        FASTQC(reads)
    }

    // Exactly one aligner runs.
    if (params.aligner == 'star') {
        STAR_ALIGN(reads)
        aligned = STAR_ALIGN.out.bam
    } else {
        HISAT2_ALIGN(reads)
        aligned = HISAT2_ALIGN.out.bam
    }
    SAMTOOLS_SORT(aligned)

    if (params.run_salmon) {
        SALMON_QUANT(reads)
    }

    MULTIQC(Channel.empty().collect())
}
