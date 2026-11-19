process STAR_ALIGN {
    container 'quay.io/biocontainers/star:2.7.11b--h43eeafb_0'
    publishDir "${params.outdir}/star", mode: 'copy', pattern: '*.{bam,out}'

    input:
    tuple val(meta), path(reads)

    output:
    tuple val(meta), path("*.Aligned.sortedByCoord.out.bam"), emit: bam
    tuple val(meta), path("*.Log.final.out"), emit: log_final
    tuple val(meta), path("*.SJ.out.tab"), emit: junctions, optional: true
    path "versions.yml", emit: versions

    script:
    "STAR --readFilesIn ${reads}"
}
