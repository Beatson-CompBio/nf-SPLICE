# Getting started

This page takes you from installation to your first published SPLICE bundle,
authoring it yourself. Allow about thirty minutes for a typical Nextflow
pipeline. To let an agent do the work with you or for you instead, see
[Agentic AI](agentic-ai.md).

## Requirements

- Python 3.10 to 3.14
- Git, and read access to the nf-SPLICE GitHub repository
- A Nextflow pipeline repository, ideally with a `nextflow_schema.json`

You do not need Nextflow, Docker or an AI account. After installation, nf-splice
works offline unless you choose to use agentic AI.

## Install

nf-splice is installed from GitHub; it is not published on PyPI. Install it
in its own environment so it does not affect other Python tools. With a
virtual environment:

```bash
python -m venv ~/.venvs/nf-splice
. ~/.venvs/nf-splice/bin/activate
python -m pip install "git+https://github.com/Beatson-CompBio/nf-SPLICE.git"
nf-splice --version
```

Or with Conda (or Mamba), for example alongside nf-core tools:

```bash
conda create -n nf-splice python=3.12 git
conda activate nf-splice
python -m pip install "git+https://github.com/Beatson-CompBio/nf-SPLICE.git"
nf-splice --version
```

To try a branch before it is merged, add `@<branch>` to the address, for
example `"git+https://github.com/Beatson-CompBio/nf-SPLICE.git@wip/nf-splice-v0.3.0"`. If Git asks for credentials, sign in
with your GitHub account; the repository is private.

`nf-splice --help` shows where to start and the everyday commands;
`nf-splice --help-all` lists every command.

## 1. Make a safe working copy

nf-splice works on a copy, so your original pipeline is never changed. From
the folder that contains your pipeline:

```bash
nf-splice source prepare ./my-pipeline
```

This creates `my-pipeline-splice-integration` next to the original, on the
local Git branch `nf-splice/integration-my-pipeline`, and, in a terminal,
opens the workspace on the copy at its Welcome screen. Welcome shows the
pipeline, the working copy and its branch, your progress, and whether AI
assistance is set up:

| AI assistance | Welcome offers |
| --- | --- |
| Not configured, incomplete or not yet verified | **Start manual integration**, **Set up AI assistance**, **Exit** |
| Verified (its connection test passed) | **Manual integration**, **Assisted integration**, **Autonomous integration**, **AI provider settings**, **Exit** |

Press the number beside an option, or Enter on it. To work from the command
line instead, add `--no-open` and change into the copy:

```bash
nf-splice source prepare ./my-pipeline --no-open
cd my-pipeline-splice-integration
```

See [Working copy and Git](working-copy.md) for Git URLs and other options.
To carry on later, run `nf-splice` in the copy: it opens the same workspace
and offers to resume. Run anywhere else, it lists the working copies you
have made.

## 2. Create the drafts

Choose **Start manual integration** on Welcome, or from the root of the
working copy run:

```bash
nf-splice init
```

`init` reads your repository and writes six draft files, filled in from
exact, documented metadata (nothing scientific is guessed):

| Draft (in `.splice-local/drafts/`) | Seeded from |
| --- | --- |
| `bundle.draft.yaml` | documented keys in `nextflow.config`, `CITATION.cff` and a root RO-Crate; the upstream remote; a Git release tag |
| `inputs.draft.yaml` | every parameter in `nextflow_schema.json`, nobody allowed to change it yet |
| `outputs.draft.yaml` | an earlier `splice/outputs.yaml`, otherwise empty: you describe the outputs |
| `components.draft.yaml` | every module in `modules.json` with its container per runtime |
| `execution-profiles.draft.yaml` and `configs/default.draft.config` | a default profile and a native Nextflow config, or an earlier bundle's profiles |
| `provenance.draft.yaml` | a copy of your root `ro-crate-metadata.json`, or one built from the identity |

Seeded values are a starting point, not a verdict: unknown values are empty
and first guesses are marked as such. Nothing outside `.splice-local/` is
changed, and running `init` again never touches a draft you already have.

`init` refuses to create drafts in a folder that is not a working copy, so
an original pipeline is never changed by accident. To author in a pipeline
folder itself (for example a disposable CI checkout), authorise it with
`nf-splice init --in-place`; the consent is recorded in
`.splice-local/integration.json`.

## 3. Edit the files

The drafts are yours. Open them in any editor, for example VS Code:

```bash
code .splice-local/drafts/
```

Edit anything, add what discovery missed, delete what is wrong. The
profile's actual Nextflow configuration is the native file
`.splice-local/drafts/configs/default.draft.config`; edit it like any other
Nextflow config. Check a layer at any time:

```bash
nf-splice draft validate outputs
nf-splice draft validate execution-profiles
```

Validation reads the file on disk and never changes it. Errors give the file,
the field (a JSON pointer such as `/outputs/3/scopes`) and what to do; a file
that does not parse is reported and left as it is. You never have to accept
or reject discovery candidates: a valid draft builds as it is.

If you prefer forms, the workspace shows the same files as guided pages, with
Ask AI and Assist on every page (see [The workspace](workspace.md)):

```bash
nf-splice tui
```

`nf-splice configure <layer>` makes targeted edits from the command line. All
routes write the same files and can be mixed freely. The layer guides
describe each one:

1. [Identity](identity.md) and [assay capabilities](assays.md)
2. [Inputs](inputs.md): who may change each parameter
3. [Outputs](outputs.md): what the pipeline publishes
4. [Components](components.md): modules and container images
5. [Execution profiles](execution-profiles.md): how the pipeline runs
6. [Provenance](provenance.md): the RO-Crate

## 4. See what is left to do

```bash
nf-splice status
nf-splice plan
```

`status` shows each layer as `missing`, `malformed`, `incomplete` or
`ready`; `plan` lists every blocker with the draft field it refers to.

## 5. Publish

When `nf-splice plan` reports no blockers:

```bash
nf-splice build all
nf-splice validate
```

`build` publishes the bundle and then says where it stands, for example
`Published, but not ready for SPLICE ingestion.` with each reason. A
successful build is not ingestion readiness: `validate` reports whether the
bundle is structurally valid, scientifically classified and ready for
ingestion, with each readiness dimension separately (contracts,
classification, runtime parameters, deployment, provenance, publication),
and exits with status 2 until all are ready. The published bundle is in `splice/`. Commit `splice/` and the
updated `.gitignore`; your drafts stay in the private `.splice-local/` folder.

```bash
nf-splice git commit
nf-splice export --archive-scope pipeline
```

`export` writes a verified ZIP; the pipeline archive is a standard Workflow
RO-Crate (see [Export a ZIP archive](export.md)).

## Next steps

- [Agentic AI](agentic-ai.md): an agent investigates the pipeline and
  improves the drafts with you, or for you.
- [Output routes and evidence](output-coverage.md): outputs across
  alternative routes with `nf-splice assess`.
- [Publishing and updating](publishing.md): releasing a new version.
- [Job outputs](job-outputs.md): what happens after each job runs.
- [Core concepts](concepts.md): drafts, layers, evidence and readiness.
