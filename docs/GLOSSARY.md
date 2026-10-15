# nf-SPLICE nomenclature

This is the canonical vocabulary for nf-splice code, contracts, CLI/TUI
labels, generated README files, schema references and agent tools. Other
documentation links here rather than redefining these words.

## Platform units

| Word | Precise meaning in 0.3.0 | Must not mean |
| --- | --- | --- |
| **Job** | One submitted workflow invocation/execution, including the collection of its inputs and its job-wide summary/report outputs. `analysis_output.json` is one document per completed job. | A single file-level run or a sample. |
| **Sample** | A biological/experimental sample. Sample-scoped output represents aggregated data for that sample, or its only available output granularity. | One of several distinct file-level runs belonging to that sample. |
| **Run** | A SPLICE platform file-level or acquisition-level unit belonging to a sample; several runs may share one sample. Run-scoped outputs carry an explicit platform `run_id` and the `sample_id` of their parent sample. | A Nextflow (or Snakemake) workflow execution. |
| **Engine execution metadata** | Engine-native session, task, invocation or execution identifiers linked to a job, explicitly qualified by engine (`job_metadata.engine_execution_id`, `job_metadata.nextflow.session_id`, `job_metadata.nextflow.run_name`). | A `run` output scope or a top-level platform run identifier for the whole job. |

Example: one Nextflow execution analysing sample S1 (platform runs S1_R1 and
S1_R2) and sample S2 (one run S2_R1) is **one job**, with **three platform
runs** and **two samples**. A job-level MultiQC report is `scope: job`;
per-sample quantification is `scope: sample`; file-level acquisition QC is
`scope: run`. FASTQ read mates are not automatically distinct runs: only an
evidence-backed platform run identifier or an explicit reviewed binding
permits `scope: run`.

## Bundle vocabulary

| Word | Meaning |
| --- | --- |
| **Bundle** | The static SPLICE integration published below repository-root `splice/`. |
| **Bundle file index** | The `files` map in `bundle.json` naming every final artefact. |
| **Contract family** | One of the five public workflow-bundle JSON contracts, identified by a URI below `https://schemas.splice-data.io/workflow-bundle/`. The bundle index family is `https://schemas.splice-data.io/workflow-bundle/bundle`. |
| **Contract registry** | The packaged mapping from each nf-splice release to the revision of every contract family it emits (`nf-splice schema list`). |
| **Draft** | An editable, authoritative working file below `splice/drafts/`, named `*.draft.*` and carrying a draft marker. |
| **Final artefact** | A validated, draft-marker-free file at its published path below `splice/`. |

## Reserved word: `manifest`

`manifest` is reserved for a different SPLICE platform concept. nf-splice
never uses it for the bundle, the bundle file index, the contract registry,
schema identifiers, emitted keys, UI labels or public API names.

**Upstream syntax exception.** Nextflow itself defines a `manifest { ... }`
scope and keys such as `manifest.name` in `nextflow.config`. The Nextflow
identity inspector must keep recognising that literal token to read pipeline
metadata as evidence. It is an input-parser token only, never an output name
or SPLICE concept.
