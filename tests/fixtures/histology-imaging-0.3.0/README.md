# histology-imaging-0.3.0

A synthetic H&E whole-slide histopathology pipeline: stain normalisation,
nuclear segmentation, per-nucleus morphology features and a slide report.
Inputs are OME-TIFF slides listed in a CSV; outputs are image pyramids,
label masks, Parquet tables and an HTML report. It has no FASTQ, no genes
and no sequencing concepts, so it checks that nf-splice's interfaces work
for imaging without special cases. It is never run; the files are
byte-exact test data written for nf-splice, not taken from a SPLICE tool.
