---
name: nf-splice-assay-capabilities
description: Declare which assays a Nextflow pipeline can process, classified by the SPLICE modality vocabulary (modality, subtype, assay type, assay method), with evidence. Use at the identity stage, when a person asks about assays or modalities, or when capability evidence is ambiguous.
---

# Assay capabilities

## When to use

Use this skill when a pipeline's assay capabilities are being declared or
reviewed (identity stage), when a person asks what assays or modalities a
pipeline supports, or when you must explain the difference between a
modality and an assay.

## Prerequisites

- The identity draft exists (`initialise_drafts` has run).
- The vocabulary is nf-splice's packaged snapshot of the SPLICE modality
  vocabulary; every tool below uses the same resolver. Nothing needs a
  network.

## The vocabulary in one minute

- Entity types, from broad to specific: MODALITY (Transcriptomics),
  MODALITY_SUBTYPE (Bulk RNA-seq), ASSAY_TYPE (Short-read RNA-seq) and
  ASSAY_METHOD (poly(A) RNA-seq). A root entity, "Data modality", sits above
  the modalities and is never a capability or a modality.
- It is a graph, not a tree: Xenium RNA belongs to both Imaging and
  Transcriptomics. Keep every path; never pick one.
- Some assays stop at ASSAY_TYPE (ATAC-seq has no method). Never add a level
  the vocabulary does not have.
- A **registered assay** is a platform registration with a code, for example
  polya_rnaseq or total_rnaseq. The platform calls these rows "modalities",
  but each one names an assay, not a top-level modality. Never call poly(A)
  RNA-seq a modality.
- The registration flag "current" says what one deployment ingests today. It
  never limits what a pipeline may declare.

## Workflow

1. Read what is declared and what the repository names:
   `list_assay_candidates`. A candidate is a mention in documentation, the
   parameter schema or configuration, with locations. It is not proof.
2. Read the evidence behind each candidate with `read_source` or
   `search_source`: does the pipeline actually support that assay (a library
   type parameter, documented protocols, route-specific processing)?
3. Look up exact classifications with `show_assay` or
   `search_assay_catalogue`. Use registered codes where they exist; use
   `entity:<id>` only for an assay concept that has no registration.
4. Declare each supported assay with `add_assay_capability`, citing
   `evidence` (documented or detected), the `sources` (path:line) and a
   one-sentence rationale. Remove a wrong one with
   `remove_assay_capability`.
5. Check the identity draft with `inspect_draft` for the bundle layer.

Declare the union of assays the pipeline supports across its routes: a
poly(A) example run does not mean total RNA-seq is unsupported.

## Verification gates

- `inspect_draft` reports no capability issue: every entry resolves, has
  evidence and a rationale, and none is duplicated.
- The published `bundle.json` capabilities are re-resolved by `validate_bundle`;
  a label, type, path or modality that differs from the vocabulary fails.

## Failure handling

- Unknown code, wrong type (a modality or subtype is not an assay), duplicate,
  or mismatched label: the tool says which; correct the reference.
- Evidence is a generic file type or tool (FASTQ, an aligner): that does not
  establish a library preparation. Do not declare; in an assisted session ask
  the person, in an autonomous run call `record_blocker` naming the assays
  that need a person's decision.
- An assay the person knows is supported without repository evidence: only
  the person can assert it (`nf-splice configure bundle --add-assay`); you
  cannot use asserted evidence.

## Evidence reporting

For each capability, report the registered code or entity id, the exact
label and type from `show_assay`, every modality it belongs to, the evidence
kind, and the cited locations. Say which candidates you did not declare and
why.

## Safety boundaries

- Never invent a code, label, entity id or platform accession identifier;
  accession identifiers come only from the SPLICE platform and are refused.
- Never write capabilities with `patch_draft` or `set_identity`; only the two
  capability tools change them, and they check every value.
- Never treat a deployment's "current" flag as a reason to add or remove a
  capability.
