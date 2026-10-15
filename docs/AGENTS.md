# Agent tool contract

Developer reference for assistant integrations: modes, tools, policy and
providers. To use the assistant, see [AI assistance](guide/ai-assistant.md).

nf-splice works completely without AI. The agent integration is **off by
default**, never imported at CLI/TUI start-up, and can only *propose*
changes. Deterministic nf-splice services remain the only source of
validation and truth, and only a human approval turns a proposal into an
attributed draft edit.

## Modes

| Mode | What the agent may do |
| --- | --- |
| `off` (default) | Nothing; no SDK is loaded, no credentials are needed. |
| `ask` | Read-only tools: status, draft inspection, candidates, plan preview, validation, container classification, RO-Crate findings, vocabulary. |
| `suggest` | `ask` plus `propose_*` tools that validate a change and store a pending proposal. No file changes. |
| `draft` | Same tools as `suggest`, for multi-layer iteration over its own proposals. |
| `apply` | Additionally `apply_approved_proposal`, which works only for proposals a human has already approved. Not offered by `nf-splice agent run`. |

## Tool contract

`nf-splice agent tools --mode suggest` prints the JSON schemas. Every tool
returns a structured result with `success`, `issues`, and where relevant
`candidate_ids`, `diff`, `requires_approval` and `proposal_id`. Results are
redacted (secret-like values, e-mail addresses) and size-bounded.

| Tool | Effect |
| --- | --- |
| `workspace_status`, `inspect_draft`, `read_draft` | Read layer states and draft content. |
| `list_output_candidates`, `list_component_candidates` | Pending candidates with evidence locations. |
| `preview_promotion`, `validate_bundle` | Read-only plan and validation. |
| `classify_container`, `analyse_ro_crate`, `explain_term` | Offline diagnostics and glossary. |
| `propose_patch` | JSON-pointer operations (with `expected` base values) on one draft; validated as a three-way merge, never written. |
| `propose_output_review` | Accept (with a complete reviewed output) or reject one candidate. Unknown candidate IDs fail. |
| `propose_access` | Who may edit parameters. Applying it always needs a human approver. |
| `propose_identity` | Identity field values for `bundle.draft.yaml`. |
| `apply_approved_proposal` | Only for human-approved proposals (mode `apply`). |

An agent cannot run shell commands, read files outside the repository,
access the network, publish files, upload images or approve its own
proposals. Denied requests are returned to the model as denials and
recorded in the private audit store.

## Human review

```bash
nf-splice agent run "Suggest reviews for the output candidates" \
  --provider claude --mode suggest --allow-remote-model
nf-splice agent proposals
nf-splice --actor "Ada Lovelace" agent approve proposal-0123456789ab
nf-splice agent reject proposal-0123456789ab --reason "Platform decides"
```

Approval requires a human actor label. Applied changes are recorded with
origin `agent_suggestion`, the agent as actor and the human as
`approved_by`. In the wizard, press **Ctrl+A** for the assistant panel
(`nf-splice tui --agent claude --allow-remote-model`); switching it on or off
never changes authoring formats or wizard state. Proposals are stored
outside the repository next to wizard sessions (`NF_SPLICE_SESSION_DIR`).

## Claude Agent SDK provider

Install the `claude` extra (Claude Agent SDK
`>=0.2.167,<0.3`, Python 3.10-3.14). The adapter configures the SDK for least
privilege: built-in tools are disabled (`tools=[]`) **and** listed in
`disallowed_tools`; user/project settings are not loaded
(`setting_sources=[]`); only the in-process `nf_splice` MCP server is
configured (`strict_mcp_config`); `can_use_tool` and a `PreToolUse` hook deny
any non-nf-splice tool; the working directory is the repository; turn and
budget limits apply. nf-splice re-checks every call with its own policy.

Context is minimised: rules, glossary and layer states are sent up front;
draft content is sent only when the agent calls a read tool. Sending any
repository context to a remote model requires explicit consent
(`--allow-remote-model`). nf-splice never selects a paid provider silently.

**Accounts and billing.** A Claude Team or Enterprise subscription, Claude
Code access and Claude Platform (API / Agent SDK) access are separate
entitlements. Do not assume a Team subscription authorises or pays for Agent
SDK usage: API usage is billed through a Claude Platform (Console)
organisation, and any subscriber API credits follow their own rules after
account linking. Confirm the organisation's settings and authentication
before use. The live smoke test is opt-in:
`NF_SPLICE_LIVE_AGENT=1 pytest -m live_agent`.

## Adding providers

Codex, OpenCode or local-model adapters are future work. A provider
implements `nf_splice.agents.protocol.AgentProvider` (capabilities and a
cancellable streaming session that calls the supplied tool invoker) inside
`nf_splice/agents/providers/`; no change to services, the CLI/TUI flow or
validators is needed. The offline `ScriptedProvider` is the reference
implementation used by CI.
