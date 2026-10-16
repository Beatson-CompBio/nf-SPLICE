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

Assay operations (`assess_assays`, `search_assay_catalogue`, `show_assay`,
`list_assay_candidates`, `add_assay_capability`, `remove_assay_capability`,
`reject_assay_candidate`) use the deterministic discovery service in
`src/nf_splice/services/assay_discovery.py`, the one resolver in
`src/nf_splice/catalogue/` and the identity layer service, exactly as the
CLI and wizard do. `patch_draft` and `set_identity` refuse to write
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
