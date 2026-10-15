# Automation and CI

The committed drafts under `splice/drafts/` record every review decision, so
a bundle can be checked and rebuilt reproducibly in CI.

## Check a repository in CI

```bash
nf-splice draft validate
nf-splice build all --check --json
nf-splice validate --json
nf-splice schema check --json
```

These commands never write files. Each exits with a non-zero status when
something is wrong, so a CI job fails on any open review, invalid draft or
inconsistent published bundle.

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
nf-splice --actor "ci" build all --non-interactive --replace-existing
```

`--non-interactive` never prompts and fails on any blocker. Set an actor
label so decisions made in CI are attributed. When no label is given, a CI
identity from the environment is used where available.

## Reproducible review

Record review decisions in files and apply them in CI:

```bash
nf-splice configure outputs --decision-file output-decisions.yaml
nf-splice configure inputs --decision-file input-access.json
```

See [Outputs](outputs.md#review-many-candidates-at-once) and
[Inputs](inputs.md#many-parameters-at-once) for the formats.
