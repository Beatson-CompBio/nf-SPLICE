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

Drafts are ordinary YAML files under `.splice-local/drafts/` and are the source of
truth while you work. `.splice-local/` is your private workspace: nf-splice
adds it to the repository's `.gitignore`, and it is never published,
committed or archived. Only the finished files in `splice/` are shared.

- Edit them with nf-splice commands, the wizard or any text editor.
  nf-splice changes only the fields it is asked to change, keeps your
  comments, and reports a conflict instead of overwriting an edit you made
  at the same time.
- Unknown values are written as `null`. Nothing is guessed.
- Status is always worked out from the current file contents, so an edit in
  your editor is picked up immediately.

Review history (evidence, candidates and decisions) is kept next to the
drafts in `.splice-local/reviews/`, and AI sessions in
`.splice-local/sessions/`. Because the folder is not in Git, back it up, or
keep working in the same copy, until the bundle is finished; session
checkpoints let you undo changes while you work.

## Evidence and review

nf-splice finds information in your repository, such as a version in
`nextflow.config` or an output path in a `publishDir`. What it finds is a
suggestion until a person accepts or changes it:

- **Detected values** fill draft fields but stay unconfirmed. Confirm them
  with `nf-splice draft confirm`, edit them, or use `--accept-detected` where
  the sources agree.
- **Candidates** are discovered items, such as an output or a profile, that
  need an explicit decision: accept, reject, merge or split.

A layer is `ready` only when nothing is left unreviewed.

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

Review decisions are recorded with an actor label. Set it with `--actor` or
the `NF_SPLICE_ACTOR` environment variable:

```bash
nf-splice --actor "Ada Lovelace" configure outputs
```

The label is public. Contact details, if any, are kept only in a private
local store outside the repository. Your Git e-mail address is never
published. See [Provenance](provenance.md#attribution-and-privacy).
