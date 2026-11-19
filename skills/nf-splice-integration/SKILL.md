---
name: nf-splice-integration
description: Build the SPLICE integration for a Nextflow pipeline with nf-splice, as an external coding agent (Codex, Claude Code, OpenCode). Investigate the repository, author the YAML drafts and native configs directly, then validate and publish with the nf-splice CLI. Use when asked to integrate a pipeline with SPLICE or to fix its splice/ bundle.
---

# Build a SPLICE integration with nf-splice

## When to use

Use this skill when the person asks you to build, complete or repair the
SPLICE integration of a Nextflow pipeline ("Use nf-SPLICE to build the SPLICE
integration for this pipeline"). You are the agent: you investigate, author
and iterate with your own tools. nf-splice gives you the drafts' schemas,
deterministic validation and publication. Never start
`nf-splice session start`, `nf-splice ask` or the workspace (`nf-splice tui`):
they launch nf-splice's own embedded agents, and you do not need them.

## Prerequisites

- The `nf-splice` command (`nf-splice --version`). If it is missing, ask the
  person to install it; do not install software yourself.
- A safe integration copy. Check with `cat .splice-local/integration.json`:
  it exists in a copy made by `nf-splice source prepare` (or a folder the
  person authorised with `--in-place`); a folder that already has drafts in
  `.splice-local/drafts/` was authorised earlier. Otherwise you are
  probably in the original pipeline: stop and suggest
  `nf-splice source prepare <this folder> --no-open`, then work in the copy
  it prints. Never modify an original pipeline silently.

## Workflow

1. **Initialise.** Run `nf-splice init` once. It seeds six drafts in
   `.splice-local/drafts/` from documented metadata only and never replaces
   an existing draft, so re-running it is safe. Read its notes.
2. **Investigate the whole repository**: `main.nf`, workflows and
   subworkflows, `modules/` and `modules.json`, `nextflow.config` and
   `conf/`, `nextflow_schema.json`, `README.md`, `docs/` (especially output
   documentation), `CITATION.cff`, licences, and every `publishDir` route.
   Helpers: `nf-splice draft parameters` (where code reads `params.*`),
   `nf-splice draft routes` (published routes against the output catalogue),
   `nf-splice draft contract <layer>` (every authorable field),
   `nf-splice catalogue assays` (assay codes).
3. **Author the drafts directly** with your normal file-editing tools. You
   have full authority to create, edit, rewrite or replace these files
   without asking for each change:
   - `bundle.draft.yaml`: identity, licence, authors, assay capabilities.
   - `inputs.draft.yaml`: the runtime input contract and who may set each
     parameter.
   - `outputs.draft.yaml`: the output catalogue, the union of everything any
     route may publish. It starts empty; you write it.
   - `components.draft.yaml`: modules, tools and container images.
   - `execution-profiles.draft.yaml` with the native Nextflow configs in
     `.splice-local/drafts/configs/*.draft.config`.
   - `provenance.draft.yaml`: the Workflow RO-Crate graph.
   Seeded content is a scaffold to challenge, not an authority. Keep each
   file's `x-splice-draft` marker block. Treat the person's instructions in
   this conversation as authoritative alongside the repository's evidence.
4. **Validate and revise.** After each pass run
   `nf-splice draft validate` (or `nf-splice draft validate <layer>`), fix
   the reported paths, and repeat. Fix identity (`bundle`) first: other
   layers report `identity_not_ready` until it validates. Use `--json` when
   you want to parse results. `nf-splice status` summarises every layer;
   `nf-splice plan` lists what still blocks publication.
5. **Publish.** When the plan shows no blockers, run
   `nf-splice build all --non-interactive`, then `nf-splice validate`. Use
   `--replace-existing` only when the person agrees to replace an earlier
   published bundle that differs.
6. **Iterate** until the integration is as complete as the evidence allows,
   rebuilding after every draft change.

For detail on one layer, read the matching specialised skill with
`nf-splice skills show <name>`: `nf-splice-assay-capabilities`,
`nf-splice-input-access`, `nf-splice-output-discovery`,
`nf-splice-components-images`, `nf-splice-execution-config`,
`nf-splice-provenance` and `nf-splice-validation`. They also describe the
embedded agents' tools; you do not need those tools, because you edit the
files and run the CLI.

## Verification gates

- `nf-splice draft validate` reports no errors for any layer.
- `nf-splice plan` reports no blockers, and `nf-splice build all` succeeds.
- `nf-splice validate` decides whether the published bundle is valid and
  whether it is ready for SPLICE ingestion. A successful build is not
  readiness; report the readiness dimensions exactly as it states them.

## Failure handling

- YAML that cannot be parsed is reported as a syntax error; fix the file.
- `unresolved` or `missing_required` issues: supply the value from evidence,
  or leave it null and tell the person what is missing and why.
- Incomplete route coverage blocks ingestion readiness, not publication:
  describe the route as an output, or list it under the outputs draft's
  excluded routes with a reason.
- An interrupted build: `nf-splice draft recover`.
- A command refuses to change a file someone else edited: re-read the file
  and work from its current content.

## Evidence reporting

When you finish, report: the bundle's location (`splice/`), the result of
`nf-splice validate` (valid, classified, ingestion ready, with each
dimension that is not ready), what you authored and from which files, and
every remaining blocker or question for the person.

## Safety boundaries

- Never edit anything in `splice/` by hand; it is generated by
  `nf-splice build`. Edit only the drafts and draft configs, never the
  pipeline's own code.
- Ask the person about genuinely unresolved scientific or policy decisions
  (which assays the pipeline supports, who may set a parameter, licences,
  whether to publish people's names or contact details, image registries)
  instead of inventing them. Ordinary draft edits need no approval.
- Never invent identifiers, versions, checksums, URLs, people or licences,
  and never use placeholder values.
- Do not run the pipeline, install software, upload data, push, or read
  credentials. Do not commit `.splice-local/` or the installed agent skill
  folders.
