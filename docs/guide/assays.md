# Assay capabilities

A bundle says which **assays** your pipeline can process, each classified by
the SPLICE modality vocabulary. This lets the platform find the right
pipelines for a dataset and group them under the right modalities.

Declare every assay the pipeline supports across its routes, not only the one
your example run used: if it handles both poly(A)-selected and total RNA
libraries, declare both.

## Modality, subtype, assay type, assay method

The vocabulary has four levels below a root, from broad to specific:

| Entity type | Example |
| --- | --- |
| `MODALITY` | Transcriptomics |
| `MODALITY_SUBTYPE` | Bulk RNA-seq |
| `ASSAY_TYPE` | Short-read RNA-seq |
| `ASSAY_METHOD` | poly(A) RNA-seq |

A capability names an assay: an `ASSAY_METHOD`, or an `ASSAY_TYPE` when no
finer method exists (ATAC-seq). Levels the vocabulary does not have are never
filled in.

The vocabulary is a graph: an assay can belong to several modalities. Xenium
RNA belongs to both Imaging and Transcriptomics, and nf-splice keeps both.

The platform registers some assays under a short code, such as
`polya_rnaseq`. The platform's table for these is called "modalities", but
each registration is an assay. poly(A) RNA-seq is an assay method under
Transcriptomics, never a modality. A registration's *current* flag says what
one deployment ingests today; it does not limit what you may declare.

## Browse the vocabulary

nf-splice carries a snapshot of the vocabulary, so this works offline:

```bash
nf-splice catalogue info
nf-splice catalogue modalities
nf-splice catalogue assays --modality Transcriptomics
nf-splice catalogue assays --all-vocabulary
nf-splice catalogue show polya_rnaseq
nf-splice catalogue search "spatial"
```

`show` prints every path from the assay to its modalities, with each
entity's type.

## Declare capabilities

See which assays your repository names, with locations:

```bash
nf-splice catalogue candidates
```

A candidate is only a mention. Accepting FASTQ files, or running an aligner,
does not establish a library preparation, so nf-splice never proposes an assay
from those.

Declare each supported assay with a reason. With no evidence option it is
your statement as a person (`asserted`):

```bash
nf-splice --actor "Ada Lovelace" configure identity --add-assay polya_rnaseq --add-assay total_rnaseq --assay-rationale "The pipeline documents both library types."
```

Cite the documentation or code that shows it:

```bash
nf-splice --actor "Ada Lovelace" configure identity --add-assay atacseq --assay-evidence documented --assay-source docs/usage.md:42 --assay-rationale "The usage guide documents the ATAC-seq route."
```

Remove one:

```bash
nf-splice --actor "Ada Lovelace" configure identity --remove-assay total_rnaseq
```

An assay concept that has no platform registration can be declared by its
vocabulary id, for example `--add-assay entity:138`.

In the wizard, the **Assay capabilities** step shows the vocabulary with
entity-type badges and every modality path; highlight an assay, give a reason
and declare it. Each change is saved at once.

## What is published

The draft keeps only your reviewed codes, evidence, reasons and sources. On
build, nf-splice resolves each one and publishes in `bundle.json`:

- `pipeline.assay_capabilities`: for each assay its registered code (if
  any), the assay with its exact type, the assay types, modality subtypes and
  modalities above it, and every path;
- `assay_vocabulary`: the vocabulary snapshot it was classified with.

Labels, types and paths always come from the vocabulary; `nf-splice
validate` resolves them again and rejects anything else. See the
[bundle reference](../schemas/bundle/README.md).

## With agentic AI

In an AI-assisted session, the agent proposes capabilities at the identity
stage with the evidence it found; you approve, object or ask, as for any
stage. An agent can only declare an assay it can cite evidence for. In an
autonomous run, an assay the agent cannot establish becomes a blocker; resume
in assisted mode to decide it.

## Earlier drafts

Earlier drafts had a free-text `modality` field. It is not converted: a
free-text value cannot identify an assay. nf-splice reports it until you
declare the assays and remove the field.
