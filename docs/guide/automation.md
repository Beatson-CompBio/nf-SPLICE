# Automation and CI

The published bundle in `splice/` is committed, so CI can check it on every
change. Review decisions can also be kept in decision files (see below) and
applied in CI to rebuild the bundle reproducibly; the private drafts in
`.splice-local/` are never committed.

## Check a repository in CI

```bash
nf-splice validate --json
nf-splice schema check --json
```

These commands never write files. Each exits with a non-zero status when
something is wrong, so a CI job fails on an inconsistent published bundle.
Where the drafts are present (for example in a job that first applies
decision files), also run:

```bash
nf-splice draft validate
nf-splice build all --check --json
```

To also check example results from a test run and report route coverage:

```bash
nf-splice assess --example-output test-results --json
```

`assess` exits with a non-zero status when the bundle is invalid or the
example contains files the catalogue does not classify. See
[Output routes and evidence](output-coverage.md).

## Machine-readable output

Most commands accept `--json` and then print stable JSON instead of text.
Use it in scripts rather than parsing the text output.

## Non-interactive publishing

```bash
nf-splice --user "ci" build all --non-interactive --replace-existing
```

`--non-interactive` never prompts and fails on any blocker. Set `--user`
(or `NF_SPLICE_USER`) so decisions made in CI are attributed. When no label is given, a CI
identity from the environment is used where available.

## Reproducible authoring

The drafts are the record: keep `.splice-local/drafts/` with the working
copy (or regenerate it with `init` and apply your edits as files). Files of
complete outputs and of parameter policies can also be applied in one step:

```bash
nf-splice configure outputs --add-output qc-outputs.yaml
nf-splice configure inputs --decision-file input-access.json
```

See [Outputs](outputs.md#author-the-catalogue) and
[Inputs](inputs.md#access-policies) for the formats.
