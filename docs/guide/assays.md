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

## How nf-splice finds the assays

You do not need to know the vocabulary codes. nf-splice investigates what
your pipeline does and recommends assays, without any AI:

```bash
nf-splice catalogue recommend
```

It reads:

- the **tools** the pipeline runs: module, process, container and conda
  package names (for example STAR, Salmon, RSEM, MACS2, Bismark);
- its **parameters** and their allowed values, and **sample sheet** columns;
- the **outputs** it publishes;
- its **documentation**: README, `docs/` and parameter descriptions.

Packaged evidence rules link this evidence to the vocabulary at the level it
can support. Alignment and gene or transcript quantification establish
*Short-read RNA-seq* under Bulk RNA-seq and Transcriptomics, but not whether
the libraries were poly(A)-selected or total RNA. A rule needs several
independent signals, and some need a specific tool, so a contamination
screen (Kraken2) does not make an RNA-seq pipeline a metagenomics pipeline.

Each recommended assay shows its vocabulary id and label, its level
(`ASSAY_METHOD` or `ASSAY_TYPE`), the evidence with locations, and a status:

| Status | Meaning |
| --- | --- |
| `documented` | The repository names this assay (documentation, a parameter) |
| `supported` | The evidence establishes this level, and nothing finer applies; or a broader classification you may choose |
| `suggested` | Evidence points to it, for example rRNA-removal steps for total RNA-seq, without confirming it |
| `requires_verification` | Plausible, but the evidence cannot tell it apart from its alternatives |
| `rejected` | You rejected it, with a reason |

Where the evidence cannot decide, nf-splice says so and asks the question
that would, for example: *the pipeline processes Short-read RNA-seq data; the
repository does not establish which of poly(A) RNA-seq and Total RNA-seq it
supports.*

## Declare or reject

Recommendations are never capabilities by themselves. Declare each assay the
pipeline supports, with a reason. With no evidence option it is your
statement as a person (`asserted`):

```bash
nf-splice --actor "Ada Lovelace" configure identity --add-assay polya_rnaseq --add-assay total_rnaseq --assay-rationale "The pipeline documents both library types."
```

Cite the documentation or code that shows it:

```bash
nf-splice --actor "Ada Lovelace" configure identity --add-assay atacseq --assay-evidence documented --assay-source docs/usage.md:42 --assay-rationale "The usage guide documents the ATAC-seq route."
```

Reject a recommendation that does not apply, or remove a declared assay:

```bash
nf-splice --actor "Ada Lovelace" configure identity --reject-assay total_rnaseq --assay-rationale "Our protocol uses poly(A) selection only."
nf-splice --actor "Ada Lovelace" configure identity --remove-assay total_rnaseq
```

An assay concept that has no platform registration can be declared by its
vocabulary id, for example `--add-assay entity:255`.

In the wizard, the **Assay capabilities** step opens with the same
assessment: the detected domain, the evidence, the recommendations with
their status and confidence, and the open questions. Declare or reject a
recommendation, or pick any assay from the vocabulary table. Each change is
saved at once.

## Classification is required for ingestion

A pipeline with no declared assay is not ready for SPLICE ingestion. Until
one is declared, the identity draft reports `missing_assay_classification`
(with the recommendations), the bundle is not built, and `nf-splice
validate` reports three separate results:

```text
Structurally valid: yes; scientifically classified: no; ready for ingestion: no.
```

A bundle is *structurally valid* when its files, identity and lock are
correct, *scientifically classified* when it declares verified assays, and
*ready for ingestion* only when both hold.

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

Agents start from the same assessment and investigate further with
nf-splice's read-only tools.

- **AI-assisted:** the agent explains what it found and asks one focused
  question where the evidence cannot decide, for example whether the
  pipeline supports poly(A) libraries, total RNA libraries or both. It turns
  your answer into vocabulary entries, stages them for your approval, and
  you can object or correct it as for any stage.
- **Autonomous:** the agent declares assays the evidence establishes or the
  repository documents. Where alternatives remain, it records a blocker
  naming them and what would decide; the run is reported as partial, never
  complete. Resume the same session in AI-assisted mode to answer it.

An agent cannot assert an assay without evidence, and cannot record your
confirmation outside an approval.

## Earlier drafts

Earlier drafts had a free-text `modality` field. It is not converted: a
free-text value cannot identify an assay. nf-splice reports it until you
declare the assays and remove the field.
