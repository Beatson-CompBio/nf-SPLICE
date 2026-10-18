include { ALIGN_BISULFITE  } from '../../modules/local/align_bisulfite/main'
include { DEDUPLICATE      } from '../../modules/local/deduplicate/main'
include { CALL_METHYLATION } from '../../modules/local/call_methylation/main'

workflow METHYLATION {
    take:
    reads
    genome

    main:
    ALIGN_BISULFITE(reads, genome)
    bam = ALIGN_BISULFITE.out.bam
    if (!params.skip_dedup) {
        DEDUPLICATE(bam)
        bam = DEDUPLICATE.out.bam
    }
    CALL_METHYLATION(bam, genome)

    emit:
    calls = CALL_METHYLATION.out.bedgraph
}
