process SLIDE_REPORT {
    container 'ghcr.io/example-org/histotools:1.2.0'
    publishDir "${params.outdir}/report", mode: 'copy'

    input:
    path tables

    output:
    path "slide_report.html", emit: html

    script:
    "slide-report ${tables} --out slide_report.html"
}
