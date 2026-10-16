# The guided wizard

`nf-splice tui` opens a step-by-step wizard in your terminal. It covers every
layer, from creating the drafts to publishing the bundle, without editing
files by hand. It works without AI, and with a provider it also runs
AI-assisted and autonomous sessions.

```bash
nf-splice tui
```

## Steps

```text
Welcome → Repository → Identity → Inputs → Outputs → Components
        → Execution profiles → Provenance → Drafts → Readiness → Build → Done
```

On the Welcome step, choose how to work:

- **Create new** to create drafts from your repository and review them
  yourself;
- **Resume existing** to continue from where you left off;
- **Inspect only** to browse without writing anything;
- **AI-assisted session** to let an agent propose each stage for your
  approval (see [AI-assisted sessions](assisted-sessions.md));
- **Autonomous integration** to let an agent do the integration within a
  scope you approve (see [Autonomous integration](autonomous.md)).

The rail on the left shows each step's state: ✓ complete, ○ to do,
! blocked, » deferred, · locked. Visiting a step unlocks the next ones.
Build stays locked until every layer is ready.

## Keys

| Key | Action |
| --- | --- |
| Ctrl+N or **Continue** | Next step |
| Escape or **Back** | Previous step |
| Ctrl+D or **Finish later** | Defer the step. Publishing stays blocked. |
| Ctrl+R | Reload all files from disk |
| F1 | Help for the current step |
| Ctrl+A | Ask AI: read-only help on the current step |
| Ctrl+Q | Quit |

In tables:

| Step | Keys |
| --- | --- |
| Inputs | `u` user, `p` platform, `g` agent, `v` visibility, then **Save policies** |
| Outputs | `a` accept, `r` reject (enter a reason), Space mark, `m` merge marked, `s` split |

## Working alongside your editor

The wizard writes the same draft files as the command line and only changes
the fields you edit. If you change a draft in another editor, press Ctrl+R:
the wizard re-reads it and tells you which files changed. It never
overwrites your edits.

## Sessions

The wizard remembers the current step, deferred steps and half-typed form
values between sessions. Sessions contain no review decisions, so deleting
one loses nothing that matters. They are stored in the working copy's
private `.splice-local/sessions/wizard/`, next to the drafts, and are never
committed. Set `NF_SPLICE_SESSION_DIR` to keep them somewhere else.

Start without a session:

```bash
nf-splice tui --no-session
```

## Agentic AI in the wizard

Start the wizard with a provider to enable Ask AI and the session views:

```bash
nf-splice tui --provider claude --allow-remote-model
```

Sessions started in the wizard use the same session files as the
`nf-splice session` commands. See [Agentic AI](agentic-ai.md).
