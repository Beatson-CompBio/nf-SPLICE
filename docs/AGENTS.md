# Agent contract

Developer reference for nf-splice's agentic AI: the session engine, the
operations agents use, permissions, attribution and providers. To use it,
see [Agentic AI](guide/agentic-ai.md). For working on this repository, see
the root [AGENTS.md](../AGENTS.md).

## Architecture

```text
CLI (nf-splice ask | session ...)   Wizard (Ask AI, session views)
                 \                      /
                  SessionEngine  ─────────  ask_for_help (manual mode)
                 /      |      \
        stages.py   state.py   toolbox.py ── permissions.py
        (gates)    (sessions)      |
                               operations.py ── nf-splice services
                                   |            (layers, lifecycle,
                               sandbox.py        coverage, checks)
   providers: claude, openai, codex, opencode, scripted (protocol.py)
```

- `src/nf_splice/agents/engine.py` drives assisted and autonomous sessions
  as a typed state machine over the stages in `stages.py`.
- `operations.py` is the only way an agent acts: typed operations over the
  same services the CLI uses. `toolbox.py` mediates every call.
- `sandbox.py` runs staged operations on a private copy for previews.
- `state.py` persists sessions, checkpoints and the repository lock.
- `protocol.py` is the provider protocol; adapters live in `providers/`,
  registered in `providers/__init__.py`.

Importing `nf_splice.agents` never imports a provider SDK.

## Stages, gates and reviews

| Stage | Gate (deterministic) | Draft operations offered |
| --- | --- | --- |
| discover | every draft exists and parses | `initialise_drafts` (run without a model) |
| identity | `bundle` layer valid | `replace_draft`, `set_identity`, `patch_draft`, `add_assay_capability`, `remove_assay_capability`, `confirm_values` |
| inputs | `inputs` layer valid | `replace_draft`, `set_parameter_access`, `sync_identity`, `reimport_inputs`, `patch_draft`, `confirm_values` |
| outputs | `outputs` layer valid | `replace_draft`, `add_output`, `update_output`, `remove_output`, `set_output_contract_version`, `patch_draft`, `confirm_values` |
| components | `components` layer valid | `replace_draft`, `set_image_policy`, `discover_components`, `accept_component`, `accept_unambiguous_components`, `reject_component`, `patch_draft`, `confirm_values` |
| profiles | `execution-profiles` layer valid | `replace_draft`, `write_config`, `set_default_profile`, `discover_profiles`, `review_profile`, `reject_profile`, `add_slurm_default_profile`, `patch_draft`, `confirm_values` |
| provenance | `provenance` layer valid | `replace_draft`, `provenance_strategy`, `generate_ro_crate` (`external_tools` and `network`), `patch_draft`, `confirm_values` |
| validate | publication plan has no blockers | none; failing layers are reopened |
| build | published bundle valid and current; its summary is the lifecycle headline (ADR-0062) | `build_bundle` (run without a model) |
| verify | records the assessment | `run_optional_checks` |
| report | writes the report | none |

A layer stage completes only when its gate passes **and** a review is
recorded for the current draft (ADR-0063): an approved proposal, or the
agent's `complete_review`. Passing the gate never skips the review. The
toolbox records every read the model makes (file and line range, search,
analysis) in the stage's `investigation`.

`src/nf_splice/agents/review_scope.py` derives, for each layer stage, the
evidence classes that apply to the repository, each required or advisory:

| Stage | Required | Advisory |
| --- | --- | --- |
| identity | the draft; assay evidence through the vocabulary tools; the pipeline's metadata (`nextflow.config`, `main.nf`); its documentation (README, usage, `CITATION.cff`) | alternative routes |
| inputs | the draft; `parameter_usage`; `nextflow_schema.json`; workflow code; configs that set values | — |
| outputs | the draft; `analyse_routes`; the entry workflow and every file under `workflows/`; every config that declares `publishDir`; the example outputs supplied | local subworkflows |
| components | the draft; `component_inventory`; `modules.json`; every module with an `unresolved` item | configs that override containers |
| profiles | the draft; `analyse_execution`; every profile's config; the pipeline's resource config | modules that use `task.memory` |
| provenance | the draft; `analyse_ro_crate` or `validate_ro_crate`; the identity draft; the root crate | authorship sources; the standards check |

A class whose evidence does not exist is not applicable. `review_scope`
returns the classes, what was inspected, the gaps and calls that would close
them. `complete_review` and `submit_stage_proposal` are refused while a
required class is uninspected or when `evidence` cites a file (`path` or
`path:line`) the trace does not show was read; at least one citation must be
a read file or an analysis that ran. `complete_review` also takes
`draft_assessment` (`omissions`, `incorrect_assumptions`,
`unsupported_declarations`, `confirmed`); an unchanged draft needs
`confirmed` entries, and an outputs review must name every uncovered
alternative route it leaves out. The review is stored with its kind
(`scientific` for identity, inputs, outputs and provenance; `operational`
for components and profiles), its basis (`revised` or
`verified_unchanged`), evidence, assessment, coverage and gaps, the draft
hash, the sources fingerprint, the provider, model and reasoning effort. With the session
policy `review: reuse_unchanged` (`--review reuse-unchanged`), a completed
review from an earlier session is reused only while the draft and the
sources are byte-identical. The report lists each stage's markers
(`draft-valid`, `scientific-review-complete`, `operational-review-complete`)
and the readiness dimensions.

`replace_draft` takes the sha256 returned by `read_draft` and either complete
YAML text or a section (JSON pointer) and its data; `write_config` writes a
native profile config. Both refuse unsafe content and concurrent edits, keep
semantically invalid content, and return the validation issues. Capabilities
cannot be changed through `replace_draft`.

Every stage also offers the read operations: `workspace_status`,
`inspect_draft`, `read_draft`, `contract_reference`, `read_source`,
`search_source`, `parameter_usage`, `component_inventory`,
`analyse_execution`, `read_config`, `list_pending`, `analyse_routes`,
`route_coverage`, `list_example_outputs`, `reconcile_example_outputs`, `preview_build`,
`validate_layer`, `validate_bundle`, `assess`, `explain_term`,
`classify_container`, `analyse_ro_crate`, `validate_ro_crate`, the assay
tools and `read_skill`.

Session-control tools record intent without touching files:
`review_scope`, `submit_stage_proposal`, `complete_review`,
`assess_objection`, `record_blocker` and `record_evidence`.

`nf-splice session tools` prints every schema; `--stage outputs` shows one
stage's offer.

## Focused assistance, interventions and resume

`SessionEngine.assist(stage, actor, guidance)` plans one stage on a
person's request (the workspace's *Assist*) and stops at its proposal; it
never moves on to other stages unasked. `reject(actor, reason)` withdraws a
proposal with the person's reason. A `record_blocker` call may name the
`pointer` of the field the decision concerns; the engine keeps it with a
checkpoint, and `open_interventions()` lists the unresolved ones. After the
person edits the drafts, `resume(actor, note)` continues the **same**
session: blocked stages reopen with the note as their resolution, stale
proposals are withdrawn and the finishing stages are planned again. A
cancelled session never resumes.

In the workspace, `AgentCoordinator`
(`src/nf_splice/interfaces/tui/coordinator.py`) owns this work in one
background thread, independent of the dock. It reports *pause requested*
until the engine stops at a safe point (`request_cancel`), refuses manual
writes while the agent may write drafts, and reopens the latest unfinished
session as paused when the workspace starts again (ADR-0067).

## Reasoning effort

`Budgets.reasoning_effort` (`--reasoning-effort low|medium|high|xhigh|max|default`,
default `high`) travels in every `TurnRequest`. Each adapter maps it with
`resolve_effort` to its real control and emits a `notice` event when it
cannot apply the request:

| Provider | Native control | Values |
| --- | --- | --- |
| Claude | Claude Agent SDK `effort` with `thinking: {type: adaptive}` | the installed SDK's `EffortLevel` |
| OpenAI | Responses API `reasoning.effort` | low, medium, high |
| Codex | app-server `turn/start` `effort` | low, medium, high, xhigh |
| OpenCode | the selected model's `variant` | the variants the model lists |
| Scripted | none | none |

An unsupported value is lowered to the nearest supported one below it, never
raised; with no control nothing is sent. The session records what was
requested and applied. Effort is separate from turns, time, cost and
context.

## How a call is handled

1. The tool must be offered in this turn, its arguments must match its JSON
   schema, layer-scoped calls must target the stage's draft, and the
   session's budgets must not be exhausted.
2. The operation's permission must be granted.
3. Read operations run directly; while planning they read the preview copy,
   so the agent sees its staged changes.
4. Draft and build operations are *observed* (refused, in Ask AI and
   questions), *staged* (assisted planning: run on the preview copy and
   recorded) or *executed* (approved proposals and autonomous runs).
5. Results are redacted, size-bounded and returned as structured data;
   repository text is marked `untrusted_repository_content`. Failures are
   returned, never raised, and every call is logged to `events.jsonl`.

## Permissions

| Permission | Effect |
| --- | --- |
| `read` | Inspect repository text, drafts and authorised examples |
| `draft_edit` | Change `.splice-local/drafts/` through the layer services |
| `build` | Publish into `splice/` transactionally |
| `overwrite` | Replace differing or hand-edited published files |
| `external_tools`, `run_nextflow`, `network` | Run optional checks (nf-core lint, rocrate-validator) |

`install`, `publish_external`, `credentials` and `human_consent` can never
be granted. Paths are resolved inside the repository; `..`, absolute paths,
symbolic-link exits, `.git/`, `.splice-local/` and secrets-like files are
refused.

## Approvals and attribution

| Mode | Origin | Approval status | `approved_by` |
| --- | --- | --- | --- |
| Manual | `manual_cli` or `manual_tui` | `approved` | — |
| AI-assisted | `agent_assisted` | `approved` | the person who approved |
| Autonomous | `agent_autonomous` | `agent_policy` | none |

An approval binds the proposal's operations (by digest) and the draft
fingerprint; a proposal whose files changed is stale and cannot be applied.
Approved operations run under a checkpoint and are rolled back if one fails.

## Sessions

Sessions are stored in `.splice-local/sessions/<id>/` in the
repository (or under `NF_SPLICE_AGENT_DIR`): `session.json` (format `1`,
validated on load), `events.jsonl`, `checkpoints/` and the
`analysis-output/` files generated during verification. A lock file stops two
sessions changing the same drafts. An interrupted action is rolled back when
the session is next opened.

## Providers

A provider implements `AgentProvider` from `nf_splice.agents.protocol`:

```python
class AgentProvider(Protocol):
    @property
    def capabilities(self) -> ProviderCapabilities: ...
    def open(self, repository: Path) -> ProviderSession: ...

class ProviderSession(Protocol):
    @property
    def conversation_ref(self) -> str | None: ...
    def turn(self, request: TurnRequest) -> AsyncIterator[AgentEvent]: ...
    async def cancel(self) -> None: ...
```

A turn receives the instruction, the system prompt (rules, mode, vocabulary
and the relevant skills) and a tool invoker. The provider may call the
offered tools through the invoker and streams `message`, `tool_call`,
`tool_result`, `denied`, `usage` and `done` events. Providers without
structured tool calling are refused; remote providers need
`--allow-remote-model`.

A provider reports failure by raising `ProviderError`
(`src/nf_splice/agents/providers/base.py`) with one of twelve kinds. The
engine retries only `rate_limited`, `provider_unavailable` and
`connection_lost`, at most twice and only before any tool was touched;
every other kind pauses the session with the reason
(ADR-0050). Credentials are read from `src/nf_splice/credentials.py`, never
from the project. Each adapter also offers `diagnose()` and
`list_models()` for `nf-splice provider doctor` and `models`.

In every adapter the only model-callable tools are the nf-splice tools
offered for the turn, and the restriction is enforced by configuration and
tested by attempting forbidden calls, not by the prompt.

| Provider | Module | Restriction | Tests |
| --- | --- | --- | --- |
| Claude Agent SDK | `claude.py` | `tools=[]`, built-ins in `disallowed_tools`, no user or project settings, only the in-process `nf_splice` MCP server, `can_use_tool` and a `PreToolUse` hook deny the rest; Console API key and a private `CLAUDE_CONFIG_DIR` | `tests/test_agent_interfaces.py` |
| OpenAI Responses | `openai.py`, `openai_auth.py` | Function tools only, `store: false`, `stream: true`; any other call is refused | `tests/test_openai_provider.py` |
| Codex app-server | `codex.py` | Private `CODEX_HOME`, native features disabled, read-only sandbox in an empty folder, ephemeral threads, dynamic tools only, approvals cancelled; 0.162.x only | `tests/test_codex_provider.py` |
| OpenCode server | `opencode.py`, `mcp_bridge.py` | Loopback server with a random password, project config off, deny-all permissions except `nfsplice_*`, token-protected loopback MCP bridge; 2.0.x only | `tests/test_opencode_provider.py` |
| Scripted | `scripted.py` | No model | many |

Live tests are opt-in and skipped without credentials:
`NF_SPLICE_LIVE_AGENT=1 pytest -m live_agent` (Claude). The real Codex and
OpenCode lockdown tests run when the binaries are present
(`NF_SPLICE_CODEX`, `NF_SPLICE_OPENCODE` or `PATH`) and use local fake model
endpoints, so they cost nothing.

### Assay capabilities

Assay operations (`search_assay_catalogue`, `show_assay`,
`add_assay_capability`, `remove_assay_capability`) use the one resolver in
`src/nf_splice/catalogue/` and the identity layer service, exactly as the
CLI and the workspace do. Nothing scores, matches or infers an assay
(ADR-0069): the agent reads the pipeline itself with the source tools.
nf-splice's own earlier output (`splice/`, `.splice-local/`) is never
accepted as evidence. `patch_draft` and `set_identity` refuse to write
capabilities. Only a person may assert a capability without evidence; an
agent cites documented or detected evidence. An autonomous stage with a
recorded blocker stays open even when validation passes.

### Scripted

`ScriptedProvider` replays a JSON list of turns, or calls a Python function,
through the real engine and services. It is used for offline tests and
reproducible demonstrations.

### Adding another provider

Implement the protocol in `src/nf_splice/agents/providers/`, raise
`ProviderError` for failures, add `diagnose()` and `list_models()`, register
it in `providers/__init__.py`, and add tests that attempt forbidden native
tools. The engine, permissions, validation and persistence need no change.

## Skills

The canonical skills are in `skills/`; packaged copies in
`src/nf_splice/agents/skills/` are loaded into every turn's system prompt
(`src/nf_splice/agents/prompts.py`). `nf-splice skills export --dest DIR`
writes them where an external coding agent discovers skills, for example
`.claude/skills` for Claude Code.

External coding agents do not use this engine. `nf-splice skills install`
puts the `nf-splice-integration` skill in an integration copy for Codex,
Claude Code or OpenCode, which then author the drafts with their own tools
and use the CLI to validate and publish (ADR-0072,
[External coding agents](guide/coding-agents.md)). The embedded engine's
prompts never load that skill.
