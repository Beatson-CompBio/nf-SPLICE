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

Install the extra for the provider you will use, for example:

```bash
python -m pip install "nf-splice[claude] @ git+https://github.com/Beatson-CompBio/nf-SPLICE.git"
python -m pip install "nf-splice[openai] @ git+https://github.com/Beatson-CompBio/nf-SPLICE.git"
```

Codex and OpenCode are separate programs you install yourself. See
[AI providers and accounts](providers.md) for signing in, local models and
billing. A provider that sends repository context to a remote model needs
your explicit consent with `--allow-remote-model` on every command.

## What an agent can and cannot do

Agents act only through nf-splice's own operations, the same ones the CLI
uses. Every change is validated by nf-splice, never by the model's word.

| Permission | Lets the agent | Default |
| --- | --- | --- |
| `read` | Inspect the repository, drafts and example output you supplied | Granted |
| `draft_edit` | Edit drafts in `.splice-local/drafts/` | Granted |
| `build` | Publish validated drafts into `splice/` | Granted |
| `overwrite` | Replace published files that were edited by hand | Ask with `--allow overwrite` |
| `external_tools`, `run_nextflow`, `network` | Run optional checks: nf-core lint, `rocrate-validator`, `nextflow config` (which may use the network) | Ask with `--allow` |

An agent can never run your pipeline, install software, upload data, read
credentials or secrets files, change your pipeline's code, or decide to
publish people's contact details. Text in your repository that tries to
instruct the agent is treated as data, not instructions.

Every layer stage ends with a review of the pipeline's own code, even when
the seeded draft already validates; the agent cannot finish a stage by
reading only the draft. Sessions ask for `high` reasoning effort by default
(`--reasoning-effort`); see [AI providers](providers.md#reasoning-effort).

In an assisted session, every change also needs your approval. In an
autonomous run, changes are recorded as the agent's decisions under the
scope you approved, never as your review.

## Where sessions are kept

Sessions, conversation, tool logs and checkpoints are stored in your
repository's private `.splice-local/sessions/` directory, which nf-splice protects
with its own `.gitignore`. They are never part of the published bundle. Set
`NF_SPLICE_AGENT_DIR` to keep them somewhere else.

```bash
nf-splice session list
nf-splice session report
```

## Choosing a provider

| Provider | Use |
| --- | --- |
| `claude` | Claude through the Claude Agent SDK, with a Claude Platform API key. |
| `openai` | OpenAI's Responses API with Sign in with ChatGPT (your Plus or Pro plan), or an API key you choose explicitly. |
| `codex` | OpenAI's Codex agent through its app-server, locked to nf-splice's tools. |
| `opencode` | Any model configured in OpenCode, including local models on your computer. |
| `scripted` | Offline replay of a JSON script, for tests and reproducible demonstrations. |

```bash
nf-splice provider list
nf-splice provider doctor
```

[AI providers and accounts](providers.md) explains, for each provider, how
to sign in, where the model runs, who pays, what to ask an administrator,
and what happens when a usage limit is reached. `--max-budget-usd` caps
spending per session where the provider reports cost.

## Skills for your own coding agent

nf-splice's procedures for agents are published as skills, which the
built-in agent follows. To give them to a coding agent you already use:

```bash
nf-splice skills list
nf-splice skills export --dest .claude/skills
```

Developers building integrations: see the [agent contract](../AGENTS.md).
