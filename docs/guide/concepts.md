# Core concepts

## The bundle

A SPLICE workflow bundle describes a pipeline to the SPLICE platform: what
it is, which inputs it accepts, which outputs it produces, which software it
needs and how to run it. It is the `splice/` directory of your repository.
The platform reads only the published files there.

## Layers

The bundle is reviewed in six parts, called layers. Each has one draft file
and produces one or more published files.

| Layer | Draft | Published | Guide |
| --- | --- | --- | --- |
| `bundle` | `bundle.draft.yaml` | `bundle.json` | [Identity](identity.md) |
| `inputs` | `inputs.draft.yaml` | `inputs.schema.json` | [Inputs](inputs.md) |
| `outputs` | `outputs.draft.yaml` | `outputs.schema.json`, `outputs.yaml` | [Outputs](outputs.md) |
| `components` | `components.draft.yaml` | `components.json` | [Components](components.md) |
| `execution-profiles` | `execution-profiles.draft.yaml` | `execution-profiles.json`, `configs/*.config` | [Execution profiles](execution-profiles.md) |
| `provenance` | `provenance.draft.yaml` | `ro-crate-metadata.json` | [Provenance](provenance.md) |

## Drafts

Drafts are ordinary YAML files under `.splice-local/drafts/` and are the
source of truth while you work; execution profiles also name native
Nextflow config files in `.splice-local/drafts/configs/`. `.splice-local/` is
your private workspace: nf-splice adds it to the repository's `.gitignore`,
and it is never published, committed or archived. Only the finished files in
`splice/` are shared.

- `nf-splice init` fills every draft once from exact, documented metadata
  in the repository. Unknown values are `null`; nothing scientific is
  inferred (no assays, and no outputs unless a published catalogue exists).
  Nothing is invented. Running `init` again never changes a draft or a config.
- Edit them in any editor, in the workspace or with nf-splice commands; all
  count equally. nf-splice's own edits change only what they are asked to,
  keep your comments, and refuse to overwrite an edit made at the same time.
- A saved draft does not have to be valid yet. Validation reads the current
  file, reports exactly what is wrong, and never rewrites it.

History is kept next to the drafts in `.splice-local/reviews/` (who changed
what, discovery hints, verified images) and AI sessions in
`.splice-local/sessions/`. Because the folder is not in Git, back it up, or
keep working in the same copy, until the bundle is finished.

## Evidence

nf-splice reads documented keys in your repository, such as a version in
`nextflow.config`, and uses them to seed the drafts. Other findings, such as
the routes a `publishDir` publishes, are evidence you browse. A seeded value is your value until you change it; it is not
waiting for approval. Where sources disagree, the field is left empty and
the conflict is reported.

Discovery also records *candidates* (a module added since `init`, a profile
in `nextflow.config`). They are hints: the workspace and `nf-splice
configure` can turn one into a draft entry for you, but nothing waits for
them, and a valid draft builds with every candidate untouched. What blocks
publication is the draft's content: a missing required value, an unresolved
container. Routes no output covers block ingestion readiness, not
publication (`output_coverage`).

## Readiness

Four facts are kept apart, and every command and the workspace state them the
same way:

| Fact | Means |
| --- | --- |
| Drafts valid | Every draft passes validation, so the bundle can be published |
| Published | `splice/` holds a bundle built from the drafts, and it is current |
| Scientifically classified | The pipeline's assays are declared from the SPLICE vocabulary |
| Ready for SPLICE ingestion | Every readiness dimension is ready |

The dimensions are valid contracts, classified assays, runtime parameters
someone can supply, deployable software for the default profile (images
for its container engine, no Conda-only module under a container engine),
an RO-Crate with its required properties and a consistent publication. A
dimension nf-splice could not assess is not ready. You may publish a valid
bundle for further review; it is then reported as `Published, but not ready
for SPLICE ingestion` with the reasons until all are ready.

## Draft and published files

Promoting a ready layer writes its published files. Publishing the whole
bundle writes every published file, then the lock file `nf-splice.lock.json`
and `bundle.json`. Publication is all or nothing: if it is interrupted, the
previous bundle stays intact. See [Publishing and updating](publishing.md).

## Job, sample and run

The platform attaches each pipeline output to one of three units:

| Unit | Meaning | Example |
| --- | --- | --- |
| Job | One complete execution of the pipeline | A MultiQC report |
| Sample | One biological sample within a job | Gene counts of sample `S1` |
| Run | One file-level platform run of a sample | QC of sequencing run `S1_L001` |

A Nextflow run is a job, not a run. The [glossary](../GLOSSARY.md) has the
precise definitions.

## Attribution

Review decisions are recorded with an actor label. Set it with `--user` or
the `NF_SPLICE_USER` environment variable:

```bash
nf-splice --user "Ada Lovelace" configure outputs
```

The label is public. Contact details, if any, are kept only in a private
local store outside the repository. Your Git e-mail address is never
published. See [Provenance](provenance.md#attribution-and-privacy).
