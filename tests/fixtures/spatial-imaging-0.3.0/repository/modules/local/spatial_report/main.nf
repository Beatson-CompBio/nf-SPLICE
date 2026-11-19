process SPATIAL_REPORT {
    container 'quay.io/example/spatial-report:0.3.1'
    publishDir "${params.outdir}/report", mode: 'copy'

    input:
    path matrices

    output:
    path "spatial_report.html", emit: report

    script:
    "spatial-report ${matrices} --out spatial_report.html"
}
