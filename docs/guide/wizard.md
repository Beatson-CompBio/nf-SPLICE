# The guided wizard

`nf-splice tui` opens a step-by-step wizard in your terminal. It covers every
layer, from creating the drafts to publishing the bundle, without editing
files by hand and without AI.

```bash
nf-splice tui
```

## Steps

```text
Welcome → Repository → Identity → Inputs → Outputs → Components
        → Execution profiles → Provenance → Drafts → Readiness → Build → Done
```

On the Welcome step, choose:

- **Create new** to create drafts from your repository;
- **Resume existing** to continue from where you left off;
- **Inspect only** to browse without writing anything.

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
| Ctrl+A | Assistant panel (optional) |
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
one loses nothing that matters. They are stored outside the repository, in
`NF_SPLICE_SESSION_DIR` (default `$XDG_CACHE_HOME/nf-splice/sessions`).

Start without a session:

```bash
nf-splice tui --no-session
```

## The assistant

The assistant panel is optional and off unless you start the wizard with an
assistant. See [AI assistance](ai-assistant.md).
