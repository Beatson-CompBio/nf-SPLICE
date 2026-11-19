process REPORT {
    publishDir "${params.outdir}/reports"
    output:
    path "report.html", emit: report
}

workflow { REPORT() }
