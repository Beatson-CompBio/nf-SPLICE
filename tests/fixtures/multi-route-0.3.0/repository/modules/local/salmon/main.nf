process SALMON_QUANT {
    container 'quay.io/biocontainers/salmon:1.10.3--h6dccd9a_2'

    input:
    tuple val(meta), path(reads)

    output:
    tuple val(meta), path("quant.sf"), emit: quant
    path "versions.yml", emit: versions

    script:
    "salmon quant -1 ${reads[0]}"
}
