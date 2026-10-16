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

Assay classification is required: a pipeline without a declared assay is not
ready for SPLICE ingestion. Investigate it in every session, even when the
repository never names an assay.

1. Run `assess_assays`. It reads the pipeline's tools, parameters, sample
   sheet columns, outputs and documentation, applies nf-splice's evidence
   rules, and returns the scientific domains, candidate assays (each with
   vocabulary ids, classification level, status, confidence, evidence and
   alternatives) and the questions the evidence cannot answer.
2. Check the evidence yourself with `read_source` and `search_source`: does
   a route, parameter or document distinguish the alternatives (for example a
   library-type parameter, rRNA-depletion steps, a protocol section)?
3. Decide, with `show_assay` for exact classifications:
   - a `documented` or `supported` candidate whose evidence you have checked:
     declare it with `add_assay_capability` (evidence documented or detected,
     the locations as sources, a one-sentence rationale);
   - alternatives the evidence cannot tell apart (for example poly(A) versus
     total RNA-seq for a generic RNA-seq pipeline): never choose one by
     default. **AI-assisted:** ask the person one focused question that names
     the alternatives and the evidence (`record_blocker` in a plan turn, so
     the session waits for their reply). When they answer, resolve their
     words against the vocabulary with `show_assay` or
     `search_assay_catalogue`, declare each with evidence `confirmed`, the
     conversation as the source and their answer in the rationale, then
     submit the stage for approval. **Autonomous:** call `record_blocker`
     with the alternatives, the evidence for each and the information that
     would decide it; the stage stays open until it is resolved;
   - a candidate that does not apply: `reject_assay_candidate` with the
     reason.
4. Check the identity draft with `inspect_draft` for the bundle layer: it is
   ready only with at least one valid assay capability.

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
  establish a library preparation. It does establish a broader domain; use
  `assess_assays` to find the candidates, then ask (AI-assisted) or record a
  blocker (autonomous) naming them.
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
