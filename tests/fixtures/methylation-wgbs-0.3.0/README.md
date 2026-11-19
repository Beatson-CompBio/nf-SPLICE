# methylation-wgbs-0.3.0

A synthetic whole-genome bisulfite sequencing (DNA methylation) pipeline,
structured unlike the other fixtures: a local subworkflow, containers set
by `withName` in a config rather than in the modules, a flat parameter
schema without groups, a conditional deduplication step and a `saveAs`
rename. It checks that the same interfaces handle a non-transcriptomic
workflow without special cases. It is never run; the files are byte-exact
test data written for nf-splice.
