process MULTIQC {
    publishDir "${params.outdir}/multiqc"
    output:
    path "multiqc_report.html", emit: report
}

workflow { MULTIQC() }
