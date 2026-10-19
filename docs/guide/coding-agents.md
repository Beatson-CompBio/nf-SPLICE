# External coding agents

Codex, Claude Code and OpenCode can build a pipeline's SPLICE integration
themselves. You install one nf-splice skill into the working copy, start the
agent there and ask it in plain language. The agent investigates the
repository, writes the drafts with its own file-editing tools and uses the
ordinary nf-splice commands to validate and publish. nf-splice adds no agent
of its own and needs no AI provider set-up for this.

## Set up

```bash
nf-splice source prepare ./rnaseq --no-open
nf-splice skills install --agent all --repository ./rnaseq-splice-integration
cd rnaseq-splice-integration
codex            # or: claude, or: opencode
```

Then tell the agent:

> Use nf-SPLICE to build the SPLICE integration for this pipeline.

Add whatever you know that the code does not say: the assays the pipeline
processes, who may change which parameters, licences, which outputs matter.
The agent treats your instructions as authoritative alongside the
repository's evidence, and asks you about scientific or policy questions it
cannot settle from either.

`--agent` takes `codex`, `claude`, `opencode` or `all`; `--repository`
defaults to the current folder. The skill is written to each agent's own
project discovery folder:

| Agent | Installed skill |
| --- | --- |
| Codex | `.agents/skills/nf-splice-integration/SKILL.md` |
| Claude Code | `.claude/skills/nf-splice-integration/SKILL.md` |
| OpenCode | `.opencode/skills/nf-splice-integration/SKILL.md` |

OpenCode also reads the Codex and Claude Code folders, so with `--agent all`
it finds the same skill more than once; the copies are identical. No
`AGENTS.md` or `CLAUDE.md` is written.

Running the command again is safe: an unchanged skill is left alone, a copy
an earlier nf-splice wrote is updated, and a file someone changed is kept
(delete it and install again to replace it). Other skills and agent settings
in those folders are never touched.

## What the agent does

The skill (`nf-splice skills show nf-splice-integration`) tells the agent to:

1. run `nf-splice init` once to seed the six drafts in
   `.splice-local/drafts/`;
2. read the whole repository: workflows, modules, configs,
   `nextflow_schema.json`, documentation and every publication route;
3. author the YAML drafts and the native `.draft.config` files directly,
   rewriting them as freely as it needs to;
4. run `nf-splice draft validate`, `nf-splice status` and `nf-splice plan`
   (with `--json` when useful), revise, and repeat;
5. publish with `nf-splice build all`, check with `nf-splice validate`, and
   report the bundle, its readiness and anything still blocking.

The drafts are the source of truth (see [Core concepts](concepts.md)). The
agent never edits `splice/`: only `nf-splice build` writes it, with the same
validation and safeguards as every other way of working.

## Isolation and Git

- `skills install` refuses a folder nf-splice has not been authorised to
  change, so the original pipeline stays untouched. Use the copy from
  `nf-splice source prepare` (or authorise a folder explicitly with
  `nf-splice init --in-place`).
- The installed skill folders are local tools, not part of the integration.
  They are added to the repository's own `.git/info/exclude` (the shared one,
  for a Git worktree), never to `.gitignore`, so they are neither committed
  nor included in `nf-splice export` archives, and never published in
  `splice/`.
- Agent conversations stay with the agent; nf-splice's own state stays in
  the ignored `.splice-local/` folder.

## External agents and nf-splice's AI sessions

nf-splice also has its own embedded agents: [Ask AI](ask-ai.md),
[AI-assisted sessions](assisted-sessions.md) and
[autonomous integration](autonomous.md). Those run inside nf-splice, through
a provider you configure, with typed operations, permissions, approvals and
an audit trail. An external coding agent is a different route: it is
already an agent with its own tools and conversation, so it uses the
command line and edits the drafts itself. Do not combine the two on the same
copy at the same time; either produces the same kind of drafts and the same
validated bundle.

The quality of an external agent's authoring depends on the agent and
model; nf-splice's validation decides only whether the result is valid and
ready for ingestion.
