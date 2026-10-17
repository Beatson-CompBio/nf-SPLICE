# Troubleshooting

Every problem nf-splice reports names the draft file, the field (as a path
such as `/pipeline/licence`) and a code. Errors block publication; warnings
do not.

```text
error: .splice-local/drafts/bundle.draft.yaml#/pipeline/id [missing_required] pipeline.id is required for an ingestion-ready bundle
```

Run `nf-splice plan` to see everything still open, or
`nf-splice draft inspect <layer>` for one layer.

## Common codes

| Code | Meaning | What to do |
| --- | --- | --- |
| `missing_required` | A required value is empty. | Set it with `nf-splice configure` or in the draft. |
| `conflicting_evidence` | Sources disagree about a value. | Set the value yourself. |
| `placeholder` | A value looks like template text, such as `TODO`. | Replace it with the real value. |
| `invalid_value` | A value has the wrong form, such as a malformed URL or ORCID iD. | Correct it. |
| `recommended` | A recommended value is missing. | Optional; add it for a better listing. |
| `unresolved` | A seeded entry still lacks a required value. | Write it into the draft; `nf-splice draft validate --help`, or the wizard's *Explain errors*. |
| `route_not_covered` (error) | The code always publishes a path no output matches. | Add or correct an output, or list it under `excluded_routes` with a reason (`kind: false_positive` if the analysis is wrong). |
| `conditional_route_not_covered` (warning) | A route published under a condition matches no output. | Add an output for it, or exclude it with a reason; keep alternative routes. |
| `route_unverified` (warning) | Static analysis could not resolve a route. | Check the code; add an output or exclude it if it is published. |
| `container_not_mapped` | A module declares a container but its component names none. | Set `container_id`, or record what stops it under `unresolved`. |
| `adopted_distribution` (warning) | A verified image file was kept from the earlier bundle without downloading it again. | Nothing, or run `nf-splice containers verify` to check it again. |
| `unresolved_component` | A module's container or version needs a decision. | Resolve it in the draft and remove the `unresolved` entry. |
| `module_not_listed` (warning) | A module is not in the inventory. | Add it, or leave it out on purpose. |
| `syntax` | A draft cannot be parsed. | Fix it in your editor; nf-splice never rewrites it. |
| `access_unreviewed` | A parameter you added has no access policy. | Give it `x-splice-access.editable_by` (`[]` for nobody); see [Inputs](inputs.md). |
| `section_policy` | A config's parameter section conflicts with the access policy. | See [Execution profiles](execution-profiles.md#checks). |
| `root_property` (warning) | The RO-Crate lacks a required root property. | See [Provenance](provenance.md). |
| `missing_default` | No default execution profile is chosen. | Set `default_profile`; see [Execution profiles](execution-profiles.md). |
| `identity_not_ready` | Another layer is waiting for the identity. | Finish [Identity](identity.md) first. |
| `identity_mismatch` | A layer repeats an outdated identity. | Run `nf-splice draft sync-identity`. |
| `inputs_not_ready` | Profile parameter overrides need a ready inputs layer. | Finish [Inputs](inputs.md) first. |
| `needs_materialisation` | Images must be downloadable but one is not verified. | See [Components](components.md#deliver-images-to-an-object-store). |

## Common situations

**"was edited after it was published".** A published file in `splice/` was
changed by hand. Copy the change into the draft, or overwrite it
explicitly; see [Publishing](publishing.md#published-files-edited-by-hand).

**"file changed on disk".** The draft changed while
nf-splice was writing it, for example in an editor. Nothing was lost. Run
the command again.

**An edit conflicts with a change in the draft.** nf-splice applies its own
changes only where the draft still holds the value it expects. If you
changed the same field, it stops and names the field instead of
overwriting your edit. Resolve the field in the draft and repeat.

**Publication was interrupted.** Run `nf-splice draft recover` to restore
the previous bundle.

## Agentic AI sessions

**"is stale: files changed after it was proposed".** A draft or a pipeline
source changed after the agent made its proposal, so the proposal was
withdrawn. Run `nf-splice session continue` for a new proposal based on the
current files.

**"is changing this repository's drafts".** Another session is applying
changes. Wait for it to finish, or pause it with `nf-splice session pause`.

**"needs a person's actor label".** Approvals and session starts are
recorded with your name. Pass `--actor "Your Name"` or set
`NF_SPLICE_ACTOR`.

**"sends repository context to a remote model".** Add
`--allow-remote-model` to consent to using a remote AI provider.

**"the Claude provider needs the optional extra".** Install nf-splice with
the `claude` extra; see [Agentic AI](agentic-ai.md#install).

**A session is paused with `usage_exhausted`, `rate_limited` or
`auth_required`.** The provider stopped; nothing was lost. Run
`nf-splice provider doctor --online` to see why, then continue with
`nf-splice session resume`, with another provider (`--provider`), or
manually (`--mode manual`). See [AI providers and accounts](providers.md#when-a-provider-stops).

**"choose a provider with --provider".** No provider was given and none is
saved; run `nf-splice provider list` and `nf-splice provider select`.

**The run ended as partial.** Read `nf-splice session report`. Each blocker
names the decision, the affected file and a suggestion. Resume with
`nf-splice session resume --mode assisted` to resolve them with the agent,
or fix the drafts yourself and run `nf-splice session continue`.

## Getting more detail

```bash
nf-splice status --json
nf-splice inspect
```

`status` reports each layer's state. `inspect` shows the evidence nf-splice
found in the repository. Neither changes any file.
