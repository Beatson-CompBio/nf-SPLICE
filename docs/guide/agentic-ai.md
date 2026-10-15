# Agentic AI

nf-splice has agentic AI built in to speed up pipeline integration. An agent
can read your Nextflow code, trace where outputs are published, fill in the
drafts, check them and build the bundle, using the same nf-splice operations
you would use yourself. You choose how much control to keep.

## Three ways to work

| | Manual | AI-assisted | Autonomous |
| --- | --- | --- | --- |
| Who drives | You | The agent, stage by stage | The agent, unattended |
| Changes | You make them | The agent proposes; you approve | The agent makes routine decisions within the scope you approved |
| AI | Optional *Ask AI* questions, read-only | A conversation: approve, object, ask, reply | None needed during the run; a full report at the end |
| Start with | `nf-splice tui` or the [command line](getting-started.md) | `nf-splice session start --mode assisted` | `nf-splice session start --mode autonomous` |
| Guide | [Ask AI in manual mode](ask-ai.md) | [AI-assisted sessions](assisted-sessions.md) | [Autonomous integration](autonomous.md) |

All three write the same draft files and pass the same validation. You can
switch at any time, for example finishing an autonomous run's open questions
in an assisted session, or pausing a session to edit a draft yourself.

nf-splice works completely without AI. Nothing AI-related is loaded until
you ask for it.

## Install

```bash
python -m pip install "nf-splice[claude] @ git+https://github.com/Beatson-CompBio/nf-SPLICE.git"
```

This adds the Claude Agent SDK. The Claude provider sends repository context
to Anthropic's API, so every command that uses it needs your explicit
consent with `--allow-remote-model`.

## What an agent can and cannot do

Agents act only through nf-splice's own operations, the same ones the CLI
uses. Every change is validated by nf-splice, never by the model's word.

| Permission | Lets the agent | Default |
| --- | --- | --- |
| `read` | Inspect the repository, drafts and example output you supplied | Granted |
| `draft_edit` | Edit drafts in `splice/drafts/` | Granted |
| `build` | Publish validated drafts into `splice/` | Granted |
| `overwrite` | Replace published files that were edited by hand | Ask with `--allow overwrite` |
| `external_tools`, `run_nextflow`, `network` | Run nf-core lint, which runs `nextflow config` and may use the network | Ask with `--allow` |

An agent can never run your pipeline, install software, upload data, read
credentials or secrets files, change your pipeline's code, or decide to
publish people's contact details. Text in your repository that tries to
instruct the agent is treated as data, not instructions.

In an assisted session, every change also needs your approval. In an
autonomous run, changes are recorded as the agent's decisions under the
scope you approved, never as your review.

## Where sessions are kept

Sessions, conversation, tool logs and checkpoints are stored in your
repository's `.nf-splice-local/agent/` directory, which nf-splice protects
with its own `.gitignore`. They are never part of the published bundle. Set
`NF_SPLICE_AGENT_DIR` to keep them somewhere else.

```bash
nf-splice session list
nf-splice session report
```

## Choosing a provider

| Provider | Use |
| --- | --- |
| `claude` | Claude through the Claude Agent SDK. Needs the `claude` extra and `--allow-remote-model`. |
| `scripted` | Offline replay of a JSON script, for tests and reproducible demonstrations. |

Support for other agent providers, such as Codex or OpenCode, is planned.

**Accounts and billing.** Claude Agent SDK usage is billed through a Claude
Platform (API) organisation. A Claude Team or Enterprise subscription does
not by itself authorise or pay for it. Confirm your organisation's setup
before use. `--max-budget-usd` caps spending per session.

## Skills for your own coding agent

nf-splice's procedures for agents are published as skills, which the
built-in agent follows. To give them to a coding agent you already use:

```bash
nf-splice skills list
nf-splice skills export --dest .claude/skills
```

Developers building integrations: see the [agent contract](../AGENTS.md).
