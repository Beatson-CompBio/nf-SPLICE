# Publishing and updating

Publishing turns reviewed drafts into the files the platform reads. It is
safe to repeat: nothing is written unless it is valid, and an interrupted
publication leaves the previous bundle intact.

## Check before publishing

```bash
nf-splice draft validate
nf-splice plan
```

`draft validate` checks every draft. `plan` lists what would be written and
everything still blocking, with the draft field each item refers to:

```text
blocked: outputs/outputs/0/description: output 'tiles': description is not known yet; describe what the output contains scientifically
blocked: outputs/contract/schema_version: the analysis-output schema version (X.Y.Z) must be reviewed
```

## Publish the bundle

```bash
nf-splice build all --check
nf-splice build all
nf-splice validate
```

`build all` publishes only when every draft validates. It writes all files
first, then the lock file and `bundle.json`, so a partial bundle can never
look complete.

Publishing is not the same as being ready for SPLICE ingestion. After a
build, `build`, `status`, `validate`, `export` and the workspace all say where
the bundle stands, with the reason for each gap:

```text
Built 11 file(s).
Published, but not ready for SPLICE ingestion.
  - runtime parameters: input (required by the input contract) has no default, nobody may supply it (editable_by: []) and the default profile's config does not set it
```

The dimensions are contracts, scientific classification, runtime
parameters, deployment, provenance and publication. `validate` exits with
status 2 until every one is ready. nf-splice never widens an access policy
or invents a value to make a bundle ready: you decide, for example, whether
`input` is `editable_by: [user]` or set by the default profile's config.

## Publish one layer

A ready layer can be published while others are still drafts:

```bash
nf-splice draft diff outputs
nf-splice draft promote outputs
```

`draft diff` shows exactly what promotion would change.

## Update a published bundle

To release a new pipeline version, update the identity, bring the other
drafts in line and publish again:

```bash
nf-splice configure identity --set version=1.3.0
nf-splice draft sync-identity
nf-splice configure provenance --strategy regenerate
nf-splice draft diff
nf-splice build all --replace-existing
```

The provenance shortcut brings the RO-Crate graph to the new version (or
edit the graph's `version` yourself; with an adopted root crate, update your
root `ro-crate-metadata.json` and use `--strategy correct`).

nf-splice never replaces a published file silently: after reviewing the
difference, pass `--replace-existing`.

## Published files edited by hand

Make changes in the drafts, not in published files. If a published file was
edited by hand, nf-splice keeps the edit and blocks publication with
`edited after it was published`. Either copy the change into the draft, or
confirm that the edited file may be overwritten:

```bash
nf-splice build all --replace-existing --overwrite-edited splice/components.json
```

## After an interruption

If publication was interrupted, for example by a full disk or a closed
terminal, restore the previous bundle:

```bash
nf-splice draft recover
```

## Precise edits (advanced)

Scripts can change any draft field with a JSON-pointer patch. Each operation
states the value it expects to replace, so a patch never overwrites a
change it did not know about:

```json
[{"op": "replace", "path": "/pipeline/title", "expected": null, "value": "RNA quantification"}]
```

```bash
nf-splice draft edit bundle --patch title.json
nf-splice draft edit bundle --patch title.json --apply
```

Without `--apply`, the command only shows the result.
