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
| [`nf-splice status`](#nf-splice-status) | Show each layer's draft-derived status (read-only). |
| [`nf-splice init`](#nf-splice-init) | Create absent drafts from evidence; existing drafts are never replaced. |
| [`nf-splice configure`](#nf-splice-configure) | Review one layer by targeted, attributed edits to its draft. |
| [`nf-splice plan`](#nf-splice-plan) | Preview promotion/publication changes and blockers (read-only). |
| [`nf-splice build`](#nf-splice-build) | Promote validated drafts to published files (whole bundle for 'all'). |
| [`nf-splice validate`](#nf-splice-validate) | Validate the published bundle, cross-file identity and lock (read-only). |
| [`nf-splice migrate`](#nf-splice-migrate) | Move drafts and sessions of an earlier layout into .splice-local/. |
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
| [`nf-splice draft recover`](#nf-splice-draft-recover) | Restore the previous release after an interrupted publication. |
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
| [`nf-splice preview outputs`](#nf-splice-preview-outputs) | Print the derived outputs.schema.json/outputs.yaml (never written). |

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

Show each layer's draft-derived status (read-only).

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
| `--strategy` | `<str>` |  | Provenance: include, enriched or generated. |
| `--reimport` |  |  | Inputs: apply a conflict-free nextflow_schema.json re-import. |

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

Validate the published bundle, cross-file identity and lock (read-only).

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
| `--provider` | `<str>` | `claude` | AI provider: claude (needs the claude extra), or scripted (offline, needs --script). |
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

### nf-splice draft recover

Restore the previous release after an interrupted publication.

```text
nf-splice draft recover [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |

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
| `--provider` | `<str>` | `claude` | AI provider: claude (needs the claude extra), or scripted (offline, needs --script). |
| `--script` | `<path>` |  | JSON turn script for the offline scripted provider. |
| `--allow-remote-model` |  |  | Consent to sending repository context to a remote model. |
| `--objective` | `<str>` | `Integrate this Nextflow pipeline with SPLICE.` | What to achieve. |
| `--example-output` | `<path>` |  | Results of one completed run (directory, saved listing or output index) the agent may read as evidence. Repeatable. |
| `--allow` | `<str>` |  | Grant an extra permission: overwrite, external_tools, run_nextflow or network. Repeatable. |
| `--max-tool-calls` | `<int>` | `300` | Tool calls for the whole session. |
| `--max-stage-attempts` | `<int>` | `3` | Attempts per stage. |
| `--max-budget-usd` | `<float>` |  | Provider spending cap. |
| `--turn-timeout` | `<float>` | `600.0` | Seconds per provider turn. |
| `--model` | `<str>` |  | Explicit provider model. |
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

### nf-splice preview outputs

Print the derived outputs.schema.json/outputs.yaml (never written).

```text
nf-splice preview outputs [OPTIONS]
```

| Option | Value | Default | Description |
| --- | --- | --- | --- |
| `--repository`, `-r` | `<directory>` | `.` | Pipeline repository root. |
| `--format` | `<str>` | `json` | json or yaml. |
