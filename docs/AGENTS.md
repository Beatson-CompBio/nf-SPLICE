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
                 providers: claude, scripted (protocol.py)
```

- `src/nf_splice/agents/engine.py` drives assisted and autonomous sessions
  as a typed state machine over the stages in `stages.py`.
- `operations.py` is the only way an agent acts: typed operations over the
  same services the CLI uses. `toolbox.py` mediates every call.
- `sandbox.py` runs staged operations on a private copy for previews.
- `state.py` persists sessions, checkpoints and the repository lock.
- `protocol.py` is the provider protocol; adapters live in `providers/`.

Importing `nf_splice.agents` never imports a provider SDK.

## Stages and gates

| Stage | Gate (deterministic) | Operations offered |
| --- | --- | --- |
| discover | every draft exists and parses | `initialise_drafts` (run without a model) |
| identity | `bundle` layer valid | `set_identity`, `confirm_values`, `patch_draft` |
| inputs | `inputs` layer valid | `sync_identity`, `reimport_inputs`, `set_parameter_access`, `confirm_values`, `patch_draft` |
| outputs | `outputs` layer valid | `discover_outputs`, `set_output_contract_version`, `accept_output`, `reject_output`, `merge_outputs`, `split_output`, `update_output`, `confirm_values`, `patch_draft` |
| components | `components` layer valid | `discover_components`, `accept_component`, `accept_unambiguous_components`, `reject_component`, `set_image_policy`, `confirm_values`, `patch_draft` |
| profiles | `execution-profiles` layer valid | `discover_profiles`, `review_profile`, `reject_profile`, `set_default_profile`, `add_slurm_default_profile`, `confirm_values`, `patch_draft` |
| provenance | `provenance` layer valid | `provenance_strategy`, `confirm_values`, `patch_draft` |
| validate | publication plan has no blockers | none; failing layers are reopened |
| build | published bundle valid and current | `build_bundle` (run without a model) |
| verify | records the assessment | `run_optional_checks` |
| report | writes the report | none |

Every stage also offers the read operations: `workspace_status`,
`inspect_draft`, `read_draft`, `read_source`, `search_source`,
`list_pending`, `analyse_routes`, `list_example_outputs`,
`reconcile_example_outputs`, `preview_build`, `validate_layer`,
`validate_bundle`, `assess`, `explain_term`, `classify_container`,
`analyse_ro_crate` and `read_skill`.

Session-control tools record intent without touching files:
`submit_stage_proposal`, `assess_objection`, `record_blocker` and
`record_evidence`.

`nf-splice session tools` prints every schema; `--stage outputs` shows one
stage's offer.

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
| `external_tools`, `run_nextflow`, `network` | Run nf-core lint |

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
`usage` and `error` events. Providers without structured tool calling are
refused; remote providers need `--allow-remote-model`.

### Claude Agent SDK

Install the `claude` extra (`claude-agent-sdk>=0.2.167,<0.3`). Each turn
configures the SDK with built-in tools disabled (`tools=[]`) and listed in
`disallowed_tools`, no user or project settings, only the in-process
`nf_splice` MCP server with this turn's tools, and both `can_use_tool` and a
`PreToolUse` hook denying anything else. Conversations continue across turns
and processes with the SDK's `resume` option. Spending is capped with
`max_budget_usd`. The live smoke test is opt-in:
`NF_SPLICE_LIVE_AGENT=1 pytest -m live_agent`.

### Scripted

`ScriptedProvider` replays a JSON list of turns, or calls a Python function,
through the real engine and services. It is used for offline tests and
reproducible demonstrations.

### Adding Codex, OpenCode or another provider

Implement the protocol in `src/nf_splice/agents/providers/`, register it in
`provider_for`, and run the provider conformance tests in
`tests/test_agent_interfaces.py` against it. The engine, permissions,
validation and persistence need no change. These adapters are not
implemented yet.

## Skills

The canonical skills are in `skills/`; packaged copies in
`src/nf_splice/agents/skills/` are loaded into every turn's system prompt
(`src/nf_splice/agents/prompts.py`). `nf-splice skills export --dest DIR`
writes them where an external coding agent discovers skills, for example
`.claude/skills` for Claude Code.
