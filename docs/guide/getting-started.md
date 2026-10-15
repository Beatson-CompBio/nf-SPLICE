# Getting started

This page takes you from installation to your first published SPLICE bundle,
reviewing it yourself. Allow about thirty minutes for a typical Nextflow
pipeline. To let an agent do the work with you or for you instead, see
[Agentic AI](agentic-ai.md).

## Requirements

- Python 3.10 to 3.14
- Git, and read access to the nf-SPLICE GitHub repository
- A Nextflow pipeline repository, ideally with a `nextflow_schema.json`

You do not need Nextflow, Docker or an AI account. After installation, nf-splice
works offline unless you choose to use agentic AI.

## Install

nf-splice is installed from GitHub; it is not published on PyPI. Use a
virtual environment so it does not affect other Python tools:

```bash
python -m venv ~/.venvs/nf-splice
. ~/.venvs/nf-splice/bin/activate
python -m pip install "git+https://github.com/Beatson-CompBio/nf-SPLICE.git"
nf-splice --version
```

To try a branch before it is merged, add `@<branch>` to the address, for
example `"git+https://github.com/Beatson-CompBio/nf-SPLICE.git@wip/nf-splice-v0.3.0"`. If Git asks for credentials, sign in
with your GitHub account; the repository is private.

## 1. Create the drafts

From the root of your pipeline repository:

```bash
nf-splice init --accept-detected
```

`init` reads your repository (Nextflow configuration, `nextflow_schema.json`,
modules, Git, `CITATION.cff`, `README.md`) and writes one draft file per part
of the bundle under `splice/drafts/`. Nothing outside `splice/` is changed,
and running it again never replaces a draft you already have.

`--accept-detected` accepts the identity values that all sources agree on.
Anything ambiguous is left empty for you to decide.

## 2. See what is left to do

```bash
nf-splice status
```

```text
Layers:
  bundle: incomplete; errors=4; warnings=1; finals: bundle.json=absent
  inputs: incomplete; errors=3; warnings=0; finals: inputs.schema.json=absent
  outputs: incomplete; errors=5; warnings=0; ...
Bundle ready to publish: no
```

Each part of the bundle (a *layer*) is `missing`, `malformed`, `incomplete`
or `ready`. `nf-splice plan` lists every open item with the draft field it
refers to.

## 3. Review each layer

The quickest route is the guided wizard. It walks through every layer in
order and shows what is still needed:

```bash
nf-splice tui
```

If you prefer commands or scripts, review each layer with
`nf-splice configure`, or edit the draft files in your editor. All three
routes write the same files and can be mixed freely. The layer guides
describe each step:

1. [Identity](identity.md): name, version, description, authors. When it
   is ready, run `nf-splice draft sync-identity`.
2. [Inputs](inputs.md): who may change each parameter
3. [Outputs](outputs.md): what the pipeline produces
4. [Components](components.md): modules and container images
5. [Execution profiles](execution-profiles.md): how the pipeline runs
6. [Provenance](provenance.md): the RO-Crate

## 4. Publish

When `nf-splice status` reports every layer as `ready`:

```bash
nf-splice build all --check
nf-splice build all
nf-splice validate
```

`--check` shows what would be written without writing it. The published
bundle is in `splice/`. Commit `splice/`, including `splice/drafts/`, to
your repository: the drafts record the reviewed decisions for next time.

## Next steps

- [Agentic AI](agentic-ai.md) shows how an agent can do this work with you,
  or for you.
- [Output routes and evidence](output-coverage.md) explains how to check
  outputs across alternative routes with `nf-splice assess`.
- [Publishing and updating](publishing.md) explains releasing a new version.
- [Job outputs](job-outputs.md) explains what happens after each job runs.
- [Core concepts](concepts.md) explains drafts, layers and review in more
  depth.
