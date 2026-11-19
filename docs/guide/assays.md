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

## Declare the assays

nf-splice does not guess which assays a pipeline processes: tools, file
types and prose do not establish a library preparation, and a guess shown
with a confidence still reads as a finding (ADR-0069). You declare them,
from what you know of the pipeline and its code and documentation. A
SPLICE bundle published earlier is not evidence either. Declare each assay
the pipeline supports, with a reason. With no evidence option it is your
statement as a person (`asserted`):

```bash
nf-splice --user "Ada Lovelace" configure identity --add-assay polya_rnaseq --add-assay total_rnaseq --assay-rationale "The pipeline documents both library types."
```

Cite the documentation or code that shows it:

```bash
nf-splice --user "Ada Lovelace" configure identity --add-assay atacseq --assay-evidence documented --assay-source docs/usage.md:42 --assay-rationale "The usage guide documents the ATAC-seq route."
```

Remove a declared assay:

```bash
nf-splice --user "Ada Lovelace" configure identity --remove-assay total_rnaseq
```

An assay concept that has no platform registration can be declared by its
vocabulary id, for example `--add-assay entity:255`.

In the workspace, **Supported assays** shows the vocabulary as a tree, from
modalities to assay methods, with each entry's description and paths.
Tick what the pipeline can process (Space), then **Save selections**; a
tick is recorded as declared by you. **Suggest an addition** prepares a
note for the vocabulary maintainers (copied to the clipboard, sent to
`NF_SPLICE_SUPPORT_CONTACT` when that is set) when an assay is missing; it
is never added automatically.

## Classification is required for ingestion

A pipeline with no declared assay is not ready for SPLICE ingestion. Until
one is declared, the identity draft reports `missing_assay_classification`,
the bundle is not built, and `nf-splice
validate` reports three separate results:

```text
Structurally valid: yes; scientifically classified: no; ready for ingestion: no.
```

A bundle is *structurally valid* when its files, identity and lock are
correct, *scientifically classified* when it declares verified assays, and
*ready for ingestion* only when both hold and every other readiness
dimension (runtime parameters, deployment, provenance, publication) is
ready; see [Core concepts](concepts.md#readiness).

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

Agents read the pipeline with nf-splice's read-only tools and the
vocabulary; nothing is scored for them.

- **AI-assisted:** the agent explains what it found and asks one focused
  question where the evidence cannot decide, for example whether the
  pipeline supports poly(A) libraries, total RNA libraries or both. It turns
  your answer into vocabulary entries, stages them for your approval, and
  you can object or correct it as for any stage.
- **Autonomous:** the agent declares assays the sources it read establish or
  the repository documents, citing them. Where alternatives remain, it
  records a blocker naming them and what would decide; the workspace shows
  it as a human intervention that opens the assay tree. Tick the assays and
  resume the same session; the run is reported as partial until then.

An agent cannot assert an assay without evidence, and cannot record your
confirmation outside an approval.

## Earlier drafts

Earlier drafts had a free-text `modality` field. It is not converted: a
free-text value cannot identify an assay. nf-splice reports it until you
declare the assays and remove the field.
