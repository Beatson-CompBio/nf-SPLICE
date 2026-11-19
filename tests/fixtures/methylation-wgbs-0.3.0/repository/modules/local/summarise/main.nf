process SUMMARISE {
    input:
    path calls

    output:
    path "methylation_summary.html", emit: html
    path "methylation_summary.tsv", emit: tsv

    script:
    "summarise-methylation ${calls}"
}
