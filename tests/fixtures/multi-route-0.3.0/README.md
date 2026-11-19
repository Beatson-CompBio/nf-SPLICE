# Multi-route pipeline fixture

A small synthetic DSL2 pipeline with alternative and optional routes:

- `FASTQC` runs unless `params.skip_qc` is set.
- `STAR_ALIGN` or `HISAT2_ALIGN` runs, depending on `params.aligner`.
- `SAMTOOLS_SORT` always runs, but its output is an intermediate: nothing
  publishes it.
- `SALMON_QUANT` runs only when `params.run_salmon` is set.
- `MULTIQC` always runs.

`example-star/` is the results directory of one completed run with the STAR
route, quality control on and Salmon off. It is observational evidence of
one route only. Synthetic content only.
