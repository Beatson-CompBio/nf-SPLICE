# Command reference

Every `nf-splice` command and option. This page is generated from the
command definitions by `scripts/generate_cli_docs.py`; run any command
with `--help` for the same information in the terminal. For
step-by-step use, start with the [user guide](../USAGE.md).

## Global options

Global options go before the command name, for example
`nf-splice --actor "Ada Lovelace" configure outputs`.

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--version` |  |  | Show the nf-splice version and exit. |
| `--actor` | `<str>` |  | Public actor label recorded with review events (never an e-mail). |

## Commands

| Command | Purpose |
| --- | --- |
| [`nf-splice inspect`](#nf-splice-inspect) | Inspect pipeline evidence and the splice/ tree (read-only). |
| [`nf-splice status`](#nf-splice-status) | Show each layer's draft status and where the bundle stands (read-only). |
| [`nf-splice init`](#nf-splice-init) | Create absent drafts from evidence; existing drafts are never replaced. |
| [`nf-splice configure`](#nf-splice-configure) | Review one layer by targeted, attributed edits to its draft. |
| [`nf-splice plan`](#nf-splice-plan) | Preview promotion/publication changes and blockers (read-only). |
| [`nf-splice build`](#nf-splice-build) | Promote validated drafts to published files (whole bundle for 'all'). |
| [`nf-splice validate`](#nf-splice-validate) | Validate the published bundle and assess ingestion readiness (read-only). |
| [`nf-splice migrate`](#nf-splice-migrate) | Move drafts and sessions of an earlier layout into .splice-local/. |
| [`nf-splice export`](#nf-splice-export) | Create and verify a ZIP of the validated bundle or pipeline copy. |
| [`nf-splice assess`](#nf-splice-assess) | Report contract validity, observed outputs and route coverage separately. |
| [`nf-splice ask`](#nf-splice-ask) | Ask AI about your pipeline or drafts; read-only, it never changes anything. |
| [`nf-splice tui`](#nf-splice-tui) | Open the terminal wizard: manual, AI-assisted or autonomous. |
| [`nf-splice analysis-output generate`](#nf-splice-analysis-output-generate) | Generate and schema-validate analysis_output.json for one completed job. |
| [`nf-splice analysis-output validate`](#nf-splice-analysis-output-validate) | Validate an existing analysis_output.json against the static contract. |
| [`nf-splice schema list`](#nf-splice-schema-list) | List the contract families and revisions emitted by this release. |
| [`nf-splice schema show`](#nf-splice-schema-show) | Print the packaged formal definition of one family revision. |
| [`nf-splice schema validate`](#nf-splice-schema-validate) | Validate one document offline against its packaged contract definition. |
| [`nf-splice schema check`](#nf-splice-schema-check) | Check every published contract file in splice/, or compare revisions. |
| [`nf-splice audit identity`](#nf-splice-audit-identity) | Show the actor label that would be recorded and the Git suggestion. |
| [`nf-splice audit show`](#nf-splice-audit-show) | Export this repository's private audit records, redacted by default. |
| [`nf-splice draft list`](#nf-splice-draft-list) | List every draft with its derived state (read-only). |
| [`nf-splice draft inspect`](#nf-splice-draft-inspect) | Show per-field issues for one draft (read-only). |
| [`nf-splice draft validate`](#nf-splice-draft-validate) | Validate one or all drafts (read-only). |
| [`nf-splice draft diff`](#nf-splice-draft-diff) | Show the final-file diff promotion would produce (read-only). |
| [`nf-splice draft confirm`](#nf-splice-draft-confirm) | Record deliberate confirmation of current (detected) draft values. |
| [`nf-splice draft edit`](#nf-splice-draft-edit) | Plan (default) or apply a JSON-pointer patch to one draft. |
| [`nf-splice draft sync-identity`](#nf-splice-draft-sync-identity) | Update the inputs draft's identity envelope from bundle.draft.yaml. |
| [`nf-splice draft promote`](#nf-splice-draft-promote) | Promote one ready layer, or publish the whole ready bundle. |
| [`nf-splice draft contract`](#nf-splice-draft-contract) | Show every authorable field of a layer's draft (read-only). |
| [`nf-splice draft parameters`](#nf-splice-draft-parameters) | Where workflow code reads params.*, against the input contract (read-only). |
| [`nf-splice draft resources`](#nf-splice-draft-resources) | Resource selectors, task.memory uses and one config's memory settings. |
| [`nf-splice draft check-config`](#nf-splice-draft-check-config) | Ask Nextflow for the effective configuration of one profile (opt-in). |
| [`nf-splice draft check-crate`](#nf-splice-draft-check-crate) | Assess the RO-Crate and check the draft graph (standards check opt-in). |
| [`nf-splice draft recover`](#nf-splice-draft-recover) | Restore the previous release after an interrupted publication. |
| [`nf-splice containers plan`](#nf-splice-containers-plan) | Which image each container needs and how it would be obtained (offline). |
| [`nf-splice containers store`](#nf-splice-containers-store) | Configure the image store (no secrets; kept in your config folder). |
| [`nf-splice containers deliver`](#nf-splice-containers-deliver) | Fetch or convert, upload, verify and record images (explicitly approved). |
| [`nf-splice containers classify`](#nf-splice-containers-classify) | Classify a container reference without network access. |
| [`nf-splice containers cache-name`](#nf-splice-containers-cache-name) | Print the Nextflow Singularity/Apptainer cache file name. |
| [`nf-splice containers verify`](#nf-splice-containers-verify) | Download and verify an image, then record its distribution (network). |
| [`nf-splice session start`](#nf-splice-session-start) | Start an AI-assisted or autonomous integration session. |
| [`nf-splice session status`](#nf-splice-session-status) | Show a session's stages, conversation and pending proposal (read-only). |
| [`nf-splice session list`](#nf-splice-session-list) | List this repository's sessions, most recent first. |
| [`nf-splice session approve`](#nf-splice-session-approve) | Approve the pending proposal; it is applied and validated. |
| [`nf-splice session object`](#nf-splice-session-object) | Object to the pending proposal; the agent investigates and responds. |
| [`nf-splice session reply`](#nf-splice-session-reply) | Answer the agent when it asks how to proceed. |
| [`nf-splice session ask`](#nf-splice-session-ask) | Ask the session's agent a question; nothing changes. |
| [`nf-splice session continue`](#nf-splice-session-continue) | Continue after editing drafts yourself; files are checked again first. |
| [`nf-splice session pause`](#nf-splice-session-pause) | Pause a session; resume it later in any mode. |
| [`nf-splice session cancel`](#nf-splice-session-cancel) | Cancel a session; drafts and published files are kept as they are. |
| [`nf-splice session resume`](#nf-splice-session-resume) | Resume a session, optionally in another mode; work so far is kept. |
| [`nf-splice session report`](#nf-splice-session-report) | Show the session's report: artefacts, results, blockers and audit. |
| [`nf-splice session rollback`](#nf-splice-session-rollback) | Restore splice/ to a session checkpoint. |
| [`nf-splice session tools`](#nf-splice-session-tools) | Print the structured tool schemas agents can use (offline). |
| [`nf-splice skills list`](#nf-splice-skills-list) | List the packaged skills. |
| [`nf-splice skills show`](#nf-splice-skills-show) | Print one skill's SKILL.md. |
| [`nf-splice skills export`](#nf-splice-skills-export) | Copy the skills where an external coding agent discovers them. |
| [`nf-splice workspace check`](#nf-splice-workspace-check) | Report problems with the private workspace and published folder (read-only). |
| [`nf-splice workspace untrack`](#nf-splice-workspace-untrack) | Stop Git tracking .splice-local/ (files kept; history not rewritten). |
| [`nf-splice source prepare`](#nf-splice-source-prepare) | Create the isolated working copy that nf-splice will change. |
| [`nf-splice source info`](#nf-splice-source-info) | Show where this integration copy came from (read-only). |
| [`nf-splice git status`](#nf-splice-git-status) | Changes to the bundle and other files (read-only). |
| [`nf-splice git diff`](#nf-splice-git-diff) | Diff of splice/ and .gitignore against the last commit (read-only). |
| [`nf-splice git commit`](#nf-splice-git-commit) | Commit the validated splice/ and .gitignore with your Git identity. |
| [`nf-splice git push`](#nf-splice-git-push) | Push the integration branch to a remote you choose (never automatic). |
| [`nf-splice preview outputs`](#nf-splice-preview-outputs) | Print the derived outputs.schema.json/outputs.yaml (never written). |
| [`nf-splice catalogue recommend`](#nf-splice-catalogue-recommend) | Investigate the pipeline and recommend assay capabilities (read-only, no AI). |
| [`nf-splice catalogue info`](#nf-splice-catalogue-info) | Which vocabulary snapshot this nf-splice carries, and its provenance. |
| [`nf-splice catalogue modalities`](#nf-splice-catalogue-modalities) | List the top-level modalities and their subtypes. |
| [`nf-splice catalogue assays`](#nf-splice-catalogue-assays) | List assays a pipeline can declare, with type, modalities and paths. |
| [`nf-splice catalogue show`](#nf-splice-catalogue-show) | Show one entity: type, description, registrations and every path. |
| [`nf-splice catalogue search`](#nf-splice-catalogue-search) | Search labels, aliases, registered codes and ids. |
| [`nf-splice catalogue candidates`](#nf-splice-catalogue-candidates) | Assays the repository names explicitly, with locations (read-only). |
| [`nf-splice catalogue compare`](#nf-splice-catalogue-compare) | Compare a live platform vocabulary with this nf-splice's pinned snapshot. |
| [`nf-splice provider list`](#nf-splice-provider-list) | List the providers, how each signs in, where it runs and who pays. |
| [`nf-splice provider doctor`](#nf-splice-provider-doctor) | Diagnose providers: installed parts, sign-in, routing and billing. |
| [`nf-splice provider models`](#nf-splice-provider-models) | List the models the signed-in account or configuration offers. |
| [`nf-splice provider select`](#nf-splice-provider-select) | Save the provider (and model) used when --provider is not given. |
| [`nf-splice provider auth`](#nf-splice-provider-auth) | Sign in, save a key or choose how a provider authenticates. |
| [`nf-splice provider test`](#nf-splice-provider-test) | Run one small real turn and check that the model calls an nf-splice tool. |

### nf-splice inspect

Inspect pipeline evidence and the splice/ tree (read-only).

```text
nf-splice inspect [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--json` |  |  | Emit stable JSON. |

### nf-splice status

Show each layer's draft status and where the bundle stands (read-only).

```text
nf-splice status [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--json` |  |  | Emit stable JSON. |

### nf-splice init

Create absent drafts from evidence; existing drafts are never replaced.

```text
nf-splice init [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--name` | `<str>` |  | Reviewed pipeline name. |
| `--pipeline-version` | `<str>` |  | Reviewed pipeline version. |
| `--repository-url` | `<str>` |  | Reviewed repository URL. |
| `--release-url` | `<str>` |  | Optional release URL. |
| `--description` | `<str>` |  | Concise description. |
| `--title` | `<str>` |  | Display title. |
| `--licence` | `<str>` |  | Licence identifier. |
| `--example-output-tree` | `<path>` |  | Outputs: example results directory, or a saved 'ls -R'/'tree' listing of one, to discover output candidates from. |
| `--contract-version` | `<str>` |  | Reviewed analysis-output schema version (X.Y.Z). |
| `--accept-detected` |  |  | Explicitly confirm every unanimous detected identity value. |
| `--json` |  |  | Emit stable JSON. |

### nf-splice configure

Review one layer by targeted, attributed edits to its draft.

```text
nf-splice configure [OPTIONS] LAYER
```

| Argument | Required | Description |
| --- | --- | --- |
| `LAYER` | yes | Layer: bundle, inputs, outputs, components, execution-profiles, provenance. |

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--set` | `<str>` |  | Repeatable explicit review value KEY=VALUE. |
| `--visibility` | `<str>` |  | Inputs: NAME=standard\|advanced\|hidden. |
| `--decision-file` | `<path>` |  | Batch review file: a YAML 'actions' list for outputs, or a JSON array of parameter policies for inputs. |
| `--example-output-tree` | `<path>` |  | Outputs: example results directory, or a saved 'ls -R'/'tree' listing of one, to discover output candidates from. |
| `--publish-directory` | `<path>` |  | Outputs: publish directory of a completed job to discover output candidates from. |
| `--contract-version` | `<str>` |  | Outputs: reviewed analysis-output schema version X.Y.Z. |
| `--export-unresolved` | `<path>` |  | Write pending candidates as JSON ('-' for stdout). |
| `--accept-detected` |  |  | Identity/components: explicitly accept unambiguous evidence. |
| `--approve-maintainer-publication` |  |  | Identity: approve publishing maintainer contacts. |
| `--require-downloadable` | `<str>` |  | Components: true/false whether images must be downloadable. |
| `--default` | `<str>` |  | Execution profiles: the reviewed default profile ID. |
| `--slurm-default` |  |  | Execution profiles: add the generated SPLICE Slurm candidate. |
| `--strategy` | `<str>` |  | Provenance shortcut: adopt (the repository's own crate), correct (a copy, from the reviewed identity) or regenerate (from the identity). Editing the YAML does the same. |
| `--with-nf-core` |  |  | Provenance: replace the crate with nf-core's generator output, run on an isolated copy (needs nf-core installed; never touches the pipeline). |
| `--reimport` |  |  | Inputs: apply a conflict-free nextflow_schema.json re-import. |
| `--add-assay` | `<str>` |  | Identity: declare an assay the pipeline can process, by registered code (polya_rnaseq) or entity:<id>. Repeatable. |
| `--remove-assay` | `<str>` |  | Identity: remove a declared assay. Repeatable. |
| `--assay-evidence` | `<str>` | `asserted` | Identity: why the assays are declared: asserted (your statement), documented or detected (cite --assay-source). |
| `--assay-rationale` | `<str>` |  | Identity: the reason the pipeline supports the added assays. |
| `--assay-source` | `<str>` |  | Identity: evidence location path:line. Repeatable. |
| `--reject-assay` | `<str>` |  | Identity: reject a recommended assay that does not apply (give the reason with --assay-rationale). Repeatable. |

### nf-splice plan

Preview promotion/publication changes and blockers (read-only).

```text
nf-splice plan [OPTIONS] [TARGET]
```

| Argument | Required | Description |
| --- | --- | --- |
| `TARGET` | no | 'all' or a layer name. |

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--json` |  |  | Emit stable JSON. |

### nf-splice build

Promote validated drafts to published files (whole bundle for 'all').

```text
nf-splice build [OPTIONS] TARGET
```

| Argument | Required | Description |
| --- | --- | --- |
| `TARGET` | yes | 'all', 'bundle' or a layer name. |

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--check` |  |  | Show changes without writing. |
| `--replace-existing` |  |  | Replace differing published files after review. |
| `--overwrite-edited` | `<str>` |  | Published path whose external edit may be overwritten. |
| `--non-interactive` |  |  | Never prompt; fail on blockers. |
| `--json` |  |  | Emit stable JSON. |

### nf-splice validate

Validate the published bundle and assess ingestion readiness (read-only).

```text
nf-splice validate [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--json` |  |  | Emit stable JSON. |

### nf-splice migrate

Move drafts and sessions of an earlier layout into .splice-local/.

```text
nf-splice migrate [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--check` |  |  | Show what would move. |
| `--apply` |  |  | Back up, move and verify. |
| `--rollback` |  |  | Restore the most recent migration's originals. |
| `--json` |  |  | Emit stable JSON. |

### nf-splice export

Create and verify a ZIP of the validated bundle or pipeline copy.

```text
nf-splice export [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--archive-scope` | `<str>` | `bundle` | bundle (splice/ only) or pipeline. |
| `--archive-output` | `<path>` |  | ZIP file to write (default .splice-local/exports/<name>-<version>-splice-<scope>.zip). |
| `--overwrite` |  |  | Replace an existing archive. |
| `--json` |  |  | Emit stable JSON. |

### nf-splice assess

Report contract validity, observed outputs and route coverage separately.

```text
nf-splice assess [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--example-output` | `<path>` |  | Results of one completed run: a directory, a saved 'ls -R'/'tree' listing or an output index. Repeatable; read-only evidence. |
| `--allow` | `<str>` |  | Permit an optional check's side effects: external_tools, run_nextflow or network. Repeatable. |
| `--write-analysis-output` | `<directory>` |  | Directory for the analysis_output.json generated from each example. |
| `--json` |  |  | Emit stable JSON. |

### nf-splice ask

Ask AI about your pipeline or drafts; read-only, it never changes anything.

```text
nf-splice ask [OPTIONS] QUESTION
```

| Argument | Required | Description |
| --- | --- | --- |
| `QUESTION` | yes | What you want to know. |

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--provider` | `<str>` |  | AI provider: claude, openai, codex, opencode, or scripted (offline, needs --script). Defaults to the one saved with `nf-splice provider select`. |
| `--script` | `<path>` |  | JSON turn script for the offline scripted provider. |
| `--allow-remote-model` |  |  | Consent to sending repository context to a remote model. |
| `--layer` | `<str>` |  | The layer you are looking at. |
| `--pointer` | `<str>` |  | JSON pointer of the field. |
| `--error` | `<str>` |  | An error message to explain. |
| `--candidate` | `<str>` |  | A candidate ID to explain. |
| `--example-output` | `<path>` |  | Results of one completed run (directory, saved listing or output index) the agent may read as evidence. Repeatable. |
| `--model` | `<str>` |  | Explicit provider model. |
| `--json` |  |  | Emit stable JSON. |

### nf-splice tui

Open the terminal wizard: manual, AI-assisted or autonomous.

```text
nf-splice tui [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--no-session` |  |  | Do not read or write wizard sessions. |
| `--provider` | `<str>` |  | Enable agentic AI in the wizard: claude, or scripted with --script. |
| `--script` | `<path>` |  | JSON turn script for the offline scripted provider. |
| `--allow-remote-model` |  |  | Consent to sending repository context to a remote model. |

### nf-splice analysis-output generate

Generate and schema-validate analysis_output.json for one completed job.

```text
nf-splice analysis-output generate [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--publish-directory` | `<path>` |  | Publish directory of the completed job (walked on disk). |
| `--native-output-index` | `<path>` |  | Output index written by the pipeline (.json, .yaml, .csv or .tsv), instead of walking a directory. |
| `--output-tree` | `<path>` |  | Saved 'ls -R' or 'tree' listing of the publish directory. Supply exactly one of the three sources. |
| `--job-metadata` | `<path>` |  | JSON job identity and job-wide metadata (job_id_short/job_id_long, config_profile, execution_timestamp, job_metadata.*). |
| `--sample-metadata` | `<path>` |  | CSV of known samples; optional run_id column maps runs to samples. |
| `--output-directory` | `<directory>` | `.` | Directory in which to write analysis_output.json. |
| `--checksum` | `<str>` |  | Optional hashlib algorithm for completed published files. |
| `--allow-unclassified` |  |  | Omit produced paths outside the reviewed contract instead of failing. |

### nf-splice analysis-output validate

Validate an existing analysis_output.json against the static contract.

```text
nf-splice analysis-output validate [OPTIONS] ANALYSIS_OUTPUT
```

| Argument | Required | Description |
| --- | --- | --- |
| `ANALYSIS_OUTPUT` | yes | Existing analysis_output.json to validate. |

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |

### nf-splice schema list

List the contract families and revisions emitted by this release.

```text
nf-splice schema list [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--json` |  |  | Emit the stable machine-readable registry view. |

### nf-splice schema show

Print the packaged formal definition of one family revision.

```text
nf-splice schema show [OPTIONS] CONTRACT
```

| Argument | Required | Description |
| --- | --- | --- |
| `CONTRACT` | yes | Family URI, key or final file name. |

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--revision` | `<str>` |  | Contract revision to show. |

### nf-splice schema validate

Validate one document offline against its packaged contract definition.

```text
nf-splice schema validate [OPTIONS] DOCUMENT
```

| Argument | Required | Description |
| --- | --- | --- |
| `DOCUMENT` | yes | JSON document. |

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--family` | `<str>` |  | Family URI, key or file name; detected from the document by default. |
| `--json` |  |  | Emit a JSON report. |

### nf-splice schema check

Check every published contract file in splice/, or compare revisions.

```text
nf-splice schema check [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--against` | `<file>` |  | Earlier formal definition to compare with --family for breaks. |
| `--family` | `<str>` |  | Family to compare. |
| `--json` |  |  | Emit a JSON report. |

### nf-splice audit identity

Show the actor label that would be recorded and the Git suggestion.

```text
nf-splice audit identity [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--actor` | `<str>` |  | Explicit public actor label. |
| `--json` |  |  | Emit JSON. |

### nf-splice audit show

Export this repository's private audit records, redacted by default.

```text
nf-splice audit show [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--no-redact` |  |  | Include private contact details (local only). |

### nf-splice draft list

List every draft with its derived state (read-only).

```text
nf-splice draft list [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--json` |  |  | Emit stable JSON. |

### nf-splice draft inspect

Show per-field issues for one draft (read-only).

```text
nf-splice draft inspect [OPTIONS] LAYER
```

| Argument | Required | Description |
| --- | --- | --- |
| `LAYER` | yes | Layer: bundle, inputs, outputs, components, execution-profiles, provenance. |

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--json` |  |  | Emit stable JSON. |

### nf-splice draft validate

Validate one or all drafts (read-only).

```text
nf-splice draft validate [OPTIONS] [LAYER]
```

| Argument | Required | Description |
| --- | --- | --- |
| `LAYER` | no | Layer; all when omitted. |

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--json` |  |  | Emit stable JSON. |

### nf-splice draft diff

Show the final-file diff promotion would produce (read-only).

```text
nf-splice draft diff [OPTIONS] [LAYER]
```

| Argument | Required | Description |
| --- | --- | --- |
| `LAYER` | no | Layer; whole bundle when omitted. |

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--json` |  |  | Emit stable JSON. |

### nf-splice draft confirm

Record deliberate confirmation of current (detected) draft values.

```text
nf-splice draft confirm [OPTIONS] LAYER POINTERS
```

| Argument | Required | Description |
| --- | --- | --- |
| `LAYER` | yes | Layer: bundle, inputs, outputs, components, execution-profiles, provenance. |
| `POINTERS` | yes | JSON pointers to confirm. |

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |

### nf-splice draft edit

Plan (default) or apply a JSON-pointer patch to one draft.

```text
nf-splice draft edit [OPTIONS] LAYER
```

| Argument | Required | Description |
| --- | --- | --- |
| `LAYER` | yes | Layer: bundle, inputs, outputs, components, execution-profiles, provenance. |

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--patch` | `<file>` |  | JSON list of patch operations with expected values. |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--apply` |  |  | Write the approved edit. |

### nf-splice draft sync-identity

Update the inputs draft's identity envelope from bundle.draft.yaml.

```text
nf-splice draft sync-identity [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |

### nf-splice draft promote

Promote one ready layer, or publish the whole ready bundle.

```text
nf-splice draft promote [OPTIONS] [LAYER]
```

| Argument | Required | Description |
| --- | --- | --- |
| `LAYER` | no | Layer; whole bundle when omitted. |

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--replace-existing` |  |  | Replace differing published files after review. |
| `--overwrite-edited` | `<str>` |  | Published path whose external edit may be overwritten. |
| `--json` |  |  | Emit stable JSON. |

### nf-splice draft contract

Show every authorable field of a layer's draft (read-only).

```text
nf-splice draft contract LAYER
```

| Argument | Required | Description |
| --- | --- | --- |
| `LAYER` | yes | Layer: bundle, inputs, outputs, components, execution-profiles, provenance. |

### nf-splice draft parameters

Where workflow code reads params.*, against the input contract (read-only).

```text
nf-splice draft parameters [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--json` |  |  | Emit stable JSON. |

### nf-splice draft resources

Resource selectors, task.memory uses and one config's memory settings.

```text
nf-splice draft resources [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--config` | `<str>` |  | An execution profile's config name (default, cirrus, ...). |
| `--json` |  |  | Emit stable JSON. |

### nf-splice draft check-config

Ask Nextflow for the effective configuration of one profile (opt-in).

```text
nf-splice draft check-config [OPTIONS] PROFILE
```

| Argument | Required | Description |
| --- | --- | --- |
| `PROFILE` | yes | Execution profile ID. |

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--allow` | `<str>` |  | run_nextflow: let `nextflow config` evaluate the configuration. |
| `--json` |  |  | Emit stable JSON. |

### nf-splice draft check-crate

Assess the RO-Crate and check the draft graph (standards check opt-in).

```text
nf-splice draft check-crate [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--allow` | `<str>` |  | external_tools: run rocrate-validator; network: let it fetch profile contexts (otherwise it runs offline). |
| `--json` |  |  | Emit stable JSON. |

### nf-splice draft recover

Restore the previous release after an interrupted publication.

```text
nf-splice draft recover [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |

### nf-splice containers plan

Which image each container needs and how it would be obtained (offline).

```text
nf-splice containers plan [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--runtime` | `<str>` |  | singularity or apptainer (default: the default profile's). |
| `--json` |  |  | Emit stable JSON. |

### nf-splice containers store

Configure the image store (no secrets; kept in your config folder).

```text
nf-splice containers store [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--endpoint` | `<str>` |  | https:// S3-compatible endpoint. |
| `--bucket` | `<str>` |  | Bucket for images. |
| `--prefix` | `<str>` |  | Key prefix, e.g. images/. |
| `--region` | `<str>` |  | Region, if the store needs one. |
| `--profile` | `<str>` |  | AWS credential profile to use (credentials are never stored). |
| `--public-base-url` | `<str>` |  | https:// URL that serves the bucket's objects for download. |

### nf-splice containers deliver

Fetch or convert, upload, verify and record images (explicitly approved).

```text
nf-splice containers deliver [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--container` | `<str>` |  | Only these container IDs. Repeatable. |
| `--approve-network` |  |  | Approve fetching or converting the planned images. |
| `--approve-upload` |  |  | Approve uploading them to the configured store. |
| `--json` |  |  | Emit stable JSON. |

### nf-splice containers classify

Classify a container reference without network access.

```text
nf-splice containers classify REFERENCE
```

| Argument | Required | Description |
| --- | --- | --- |
| `REFERENCE` | yes |  |

### nf-splice containers cache-name

Print the Nextflow Singularity/Apptainer cache file name.

```text
nf-splice containers cache-name [OPTIONS] REFERENCE
```

| Argument | Required | Description |
| --- | --- | --- |
| `REFERENCE` | yes |  |

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--registry` | `<str>` |  | Configured registry. |

### nf-splice containers verify

Download and verify an image, then record its distribution (network).

```text
nf-splice containers verify [OPTIONS] CONTAINER URL
```

| Argument | Required | Description |
| --- | --- | --- |
| `CONTAINER` | yes | Container ID from the components draft. |
| `URL` | yes | HTTPS URL of the static image. |

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--registry` | `<str>` |  | Configured Nextflow registry. |

### nf-splice session start

Start an AI-assisted or autonomous integration session.

```text
nf-splice session start [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--mode` | `<str>` | `assisted` | assisted (you approve each stage) or autonomous. |
| `--provider` | `<str>` |  | AI provider: claude, openai, codex, opencode, or scripted (offline, needs --script). Defaults to the one saved with `nf-splice provider select`. |
| `--script` | `<path>` |  | JSON turn script for the offline scripted provider. |
| `--allow-remote-model` |  |  | Consent to sending repository context to a remote model. |
| `--objective` | `<str>` | `Integrate this Nextflow pipeline with SPLICE.` | What to achieve. |
| `--example-output` | `<path>` |  | Results of one completed run (directory, saved listing or output index) the agent may read as evidence. Repeatable. |
| `--allow` | `<str>` |  | Grant an extra permission: overwrite, external_tools, run_nextflow or network. Repeatable. |
| `--max-tool-calls` | `<int>` | `1500` | Tool calls for the whole session. |
| `--max-stage-attempts` | `<int>` | `3` | Attempts per stage. |
| `--max-budget-usd` | `<float>` |  | Provider spending cap. |
| `--turn-timeout` | `<float>` | `1800.0` | Seconds per provider turn. |
| `--model` | `<str>` |  | Explicit provider model. |
| `--reasoning-effort` | `<str>` | `high` | Reasoning effort: low, medium, high, xhigh, max, or default (the provider's own). Each provider applies its real control or says it cannot. |
| `--review` | `<str>` | `always` | always: every layer gets an AI review, even when it validates; reuse-unchanged: reuse a completed review while the draft and sources are unchanged. |
| `--interactive` |  |  | Converse in this terminal (default when it is a terminal). |
| `--json` |  |  | Emit stable JSON. |

### nf-splice session status

Show a session's stages, conversation and pending proposal (read-only).

```text
nf-splice session status [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--session` | `<str>` |  | Session ID; the most recent when omitted. |
| `--diff` |  | `True` | Show the proposal diff. |
| `--json` |  |  | Emit stable JSON. |

### nf-splice session list

List this repository's sessions, most recent first.

```text
nf-splice session list [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--json` |  |  | Emit stable JSON. |

### nf-splice session approve

Approve the pending proposal; it is applied and validated.

```text
nf-splice session approve [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--session` | `<str>` |  | Session ID; the most recent when omitted. |
| `--json` |  |  | Emit stable JSON. |

### nf-splice session object

Object to the pending proposal; the agent investigates and responds.

```text
nf-splice session object [OPTIONS] MESSAGE
```

| Argument | Required | Description |
| --- | --- | --- |
| `MESSAGE` | yes | What is wrong with the proposal. |

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--session` | `<str>` |  | Session ID; the most recent when omitted. |
| `--json` |  |  | Emit stable JSON. |

### nf-splice session reply

Answer the agent when it asks how to proceed.

```text
nf-splice session reply [OPTIONS] MESSAGE
```

| Argument | Required | Description |
| --- | --- | --- |
| `MESSAGE` | yes | Your answer to the agent. |

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--session` | `<str>` |  | Session ID; the most recent when omitted. |
| `--json` |  |  | Emit stable JSON. |

### nf-splice session ask

Ask the session's agent a question; nothing changes.

```text
nf-splice session ask [OPTIONS] QUESTION
```

| Argument | Required | Description |
| --- | --- | --- |
| `QUESTION` | yes | Your question. |

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--session` | `<str>` |  | Session ID; the most recent when omitted. |

### nf-splice session continue

Continue after editing drafts yourself; files are checked again first.

```text
nf-splice session continue [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--session` | `<str>` |  | Session ID; the most recent when omitted. |
| `--json` |  |  | Emit stable JSON. |

### nf-splice session pause

Pause a session; resume it later in any mode.

```text
nf-splice session pause [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--session` | `<str>` |  | Session ID; the most recent when omitted. |

### nf-splice session cancel

Cancel a session; drafts and published files are kept as they are.

```text
nf-splice session cancel [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--session` | `<str>` |  | Session ID; the most recent when omitted. |

### nf-splice session resume

Resume a session, optionally in another mode; work so far is kept.

```text
nf-splice session resume [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--session` | `<str>` |  | Session ID; the most recent when omitted. |
| `--mode` | `<str>` |  | Switch to assisted, autonomous or manual before continuing. |
| `--allow` | `<str>` |  | Grant an extra permission: overwrite, external_tools, run_nextflow or network. Repeatable. |
| `--provider` | `<str>` |  | Continue with another provider (the session's record carries the context; nothing is switched automatically). |
| `--model` | `<str>` |  | Continue with another model. |
| `--allow-remote-model` |  |  | Consent to sending repository context to a remote model. |
| `--interactive` |  |  | Converse in this terminal (default when it is a terminal). |
| `--json` |  |  | Emit stable JSON. |

### nf-splice session report

Show the session's report: artefacts, results, blockers and audit.

```text
nf-splice session report [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--session` | `<str>` |  | Session ID; the most recent when omitted. |
| `--json` |  |  | Emit stable JSON. |

### nf-splice session rollback

Restore splice/ to a session checkpoint.

```text
nf-splice session rollback [OPTIONS] CHECKPOINT
```

| Argument | Required | Description |
| --- | --- | --- |
| `CHECKPOINT` | yes | Checkpoint ID, e.g. checkpoint-2. |

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--session` | `<str>` |  | Session ID; the most recent when omitted. |

### nf-splice session tools

Print the structured tool schemas agents can use (offline).

```text
nf-splice session tools [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--stage` | `<str>` |  | Only the tools of one stage. |

### nf-splice skills list

List the packaged skills.

```text
nf-splice skills list
```

### nf-splice skills show

Print one skill's SKILL.md.

```text
nf-splice skills show NAME
```

| Argument | Required | Description |
| --- | --- | --- |
| `NAME` | yes | Skill name. |

### nf-splice skills export

Copy the skills where an external coding agent discovers them.

```text
nf-splice skills export [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--dest` | `<directory>` |  | Directory to write <skill>/SKILL.md into, for example .claude/skills for Claude Code. |

### nf-splice workspace check

Report problems with the private workspace and published folder (read-only).

```text
nf-splice workspace check [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--json` |  |  | Emit stable JSON. |

### nf-splice workspace untrack

Stop Git tracking .splice-local/ (files kept; history not rewritten).

```text
nf-splice workspace untrack [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--yes` |  |  | Confirm: stop tracking .splice-local/. |

### nf-splice source prepare

Create the isolated working copy that nf-splice will change.

```text
nf-splice source prepare [OPTIONS] SOURCE
```

| Argument | Required | Description |
| --- | --- | --- |
| `SOURCE` | yes | Pipeline folder, local Git repository or Git URL. |

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--into` | `<path>` |  | New directory for the integration copy (default: <name>-splice-integration next to the source). |
| `--ref` | `<str>` |  | Branch, tag or commit to start from. |
| `--branch` | `<str>` |  | Local branch for the work (default nf-splice/integration-<name>). |
| `--include-uncommitted` |  |  | Also copy the source repository's uncommitted changes. |
| `--git-name` | `<str>` |  | Git author name for this copy. |
| `--git-email` | `<str>` |  | Git author e-mail for this copy. |
| `--no-git` |  |  | Plain folder copy without a local Git repository. |
| `--in-place` |  |  | Work on the original instead of a copy (risky). |
| `--yes` |  |  | Confirm working in place. |
| `--json` |  |  | Emit stable JSON. |

### nf-splice source info

Show where this integration copy came from (read-only).

```text
nf-splice source info [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--json` |  |  | Emit stable JSON. |

### nf-splice git status

Changes to the bundle and other files (read-only).

```text
nf-splice git status [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--json` |  |  | Emit stable JSON. |

### nf-splice git diff

Diff of splice/ and .gitignore against the last commit (read-only).

```text
nf-splice git diff [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |

### nf-splice git commit

Commit the validated splice/ and .gitignore with your Git identity.

```text
nf-splice git commit [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--message`, `-m` | `<str>` | `Publish the SPLICE workflow bundle` | Commit message. |
| `--include` | `<str>` |  | Also commit this pipeline path (repeatable). |

### nf-splice git push

Push the integration branch to a remote you choose (never automatic).

```text
nf-splice git push [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--remote` | `<str>` |  | Remote to push to, for example origin. |
| `--branch` | `<str>` |  | Remote branch (default: current). |
| `--yes` |  |  | Confirm pushing to the remote. |

### nf-splice preview outputs

Print the derived outputs.schema.json/outputs.yaml (never written).

```text
nf-splice preview outputs [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--format` | `<str>` | `json` | json or yaml. |

### nf-splice catalogue recommend

Investigate the pipeline and recommend assay capabilities (read-only, no AI).

```text
nf-splice catalogue recommend [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--json` |  |  | Emit stable JSON. |

### nf-splice catalogue info

Which vocabulary snapshot this nf-splice carries, and its provenance.

```text
nf-splice catalogue info [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--json` |  |  | Emit stable JSON. |

### nf-splice catalogue modalities

List the top-level modalities and their subtypes.

```text
nf-splice catalogue modalities [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--json` |  |  | Emit stable JSON. |

### nf-splice catalogue assays

List assays a pipeline can declare, with type, modalities and paths.

```text
nf-splice catalogue assays [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--modality` | `<str>` |  | Only assays under this modality (label or entity id). |
| `--all-vocabulary` |  |  | Include assay concepts that have no platform registration. |
| `--json` |  |  | Emit stable JSON. |

### nf-splice catalogue show

Show one entity: type, description, registrations and every path.

```text
nf-splice catalogue show [OPTIONS] REFERENCE
```

| Argument | Required | Description |
| --- | --- | --- |
| `REFERENCE` | yes | Registered code, entity:<id>, or an exact name. |

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--json` |  |  | Emit stable JSON. |

### nf-splice catalogue search

Search labels, aliases, registered codes and ids.

```text
nf-splice catalogue search [OPTIONS] TEXT
```

| Argument | Required | Description |
| --- | --- | --- |
| `TEXT` | yes | Label, alias, code or entity id. |

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--json` |  |  | Emit stable JSON. |

### nf-splice catalogue candidates

Assays the repository names explicitly, with locations (read-only).

```text
nf-splice catalogue candidates [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--json` |  |  | Emit stable JSON. |

### nf-splice catalogue compare

Compare a live platform vocabulary with this nf-splice's pinned snapshot.

```text
nf-splice catalogue compare [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--api` | `<str>` |  | Base URL of a SPLICE platform API. |
| `--json` |  |  | Emit stable JSON. |

### nf-splice provider list

List the providers, how each signs in, where it runs and who pays.

```text
nf-splice provider list [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--json` |  |  | Emit stable JSON. |

### nf-splice provider doctor

Diagnose providers: installed parts, sign-in, routing and billing.

```text
nf-splice provider doctor [OPTIONS] [NAME]
```

| Argument | Required | Description |
| --- | --- | --- |
| `NAME` | no | One provider; all when omitted. |

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--online` |  |  | Contact the provider to verify the credential. |
| `--json` |  |  | Emit stable JSON. |

### nf-splice provider models

List the models the signed-in account or configuration offers.

```text
nf-splice provider models [OPTIONS] NAME
```

| Argument | Required | Description |
| --- | --- | --- |
| `NAME` | yes | Provider name. |

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--json` |  |  | Emit stable JSON. |

### nf-splice provider select

Save the provider (and model) used when --provider is not given.

```text
nf-splice provider select [OPTIONS] NAME
```

| Argument | Required | Description |
| --- | --- | --- |
| `NAME` | yes | Provider name. |

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--model` | `<str>` |  | The model to use with it. |

### nf-splice provider auth

Sign in, save a key or choose how a provider authenticates.

```text
nf-splice provider auth [OPTIONS] NAME
```

| Argument | Required | Description |
| --- | --- | --- |
| `NAME` | yes | claude, openai, codex or opencode. |

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--sign-in` |  |  | OpenAI: sign in with ChatGPT in your browser. |
| `--sign-out` |  |  | OpenAI: revoke and forget the active sign-in. |
| `--account` | `<str>` |  | OpenAI: the saved account (client ID) to use. |
| `--api-key` |  |  | Save an API key, typed at a hidden prompt. |
| `--forget-key` |  |  | Remove a saved key. |
| `--use` | `<str>` |  | OpenAI: chatgpt (plan usage) or api-key (metered API billing). |
| `--yes` |  |  | Confirm switching to metered API billing. |

### nf-splice provider test

Run one small real turn and check that the model calls an nf-splice tool.

```text
nf-splice provider test [OPTIONS] NAME
```

| Argument | Required | Description |
| --- | --- | --- |
| `NAME` | yes | Provider name. |

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--model` | `<str>` |  | Model to test. |
| `--allow-remote-model` |  |  | Consent to sending repository context to a remote model. |
| `--json` |  |  | Emit stable JSON. |
