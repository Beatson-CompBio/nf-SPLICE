# The workspace

`nf-splice tui` opens one workspace in your terminal for the whole
integration: author the drafts by hand, ask AI about any screen, approve AI
proposals one step at a time, or let an agent work within a scope you
approve. Manual work and AI work use the same files, so you can switch at
any time without losing your place.

```bash
nf-splice --user "Ada Lovelace" tui
```

`--user` (or `NF_SPLICE_USER`) names you: every change, approval, pause and
resume is recorded with your name. Without it the workspace asks for a name
the first time an action must be attributed.

## Layout

- **Top bar**: the pipeline, the mode, and the agent's state (AI off, AI
  ready, thinking, proposal waiting, autonomous running, needs your input,
  pause requested, paused, blocked, completed, failed or stopped).
- **Step rail**: Welcome, Pipeline overview, Identity, Supported assays,
  Parameters, Outputs, Software, Execution, Provenance, Review and Publish,
  each with its state: ○ not started, ◐ in progress, ! needs review,
  ✓ ready, ✕ blocked, ● published. Steps can be visited in any order.
- **The page** for the current step, with *Ask AI about this screen* and a
  contextual *Assist* action at the top.
- **The AI dock** (Ctrl+A), beside the page on wide terminals and over it on
  narrow ones, with Ask, Assist and Autonomous cards. Closing the dock only
  hides it: a running session keeps running.
- **Status line**: what just happened, and the main keys.

## Starting

On Welcome choose **Start manually** (creates the six drafts once, from
exact metadata in the repository, then opens the overview), **Resume where
I left off**, **Inspect only** (browse without writing anything; also
`nf-splice tui --inspect-only`), or one of the AI options. Starting again
never changes an existing draft.

Drafts made by an earlier version may contain guessed entries, such as an
output per published route. **Start fresh from exact metadata…** on the
overview copies every draft to a private backup under
`.splice-local/backups/` and recreates the drafts.

## Keys

| Key | Action |
| --- | --- |
| F1 | Help for the current page |
| Ctrl+A | Open or close the AI dock |
| Ctrl+R | Reload all files from disk |
| Ctrl+Right / Ctrl+Left | Next / previous step |
| Escape | Close the dock or a dialog |
| Ctrl+Q | Quit (pauses a running agent safely first) |
| Ctrl+P | Commands, including the theme |

In tables:

| Page | Keys |
| --- | --- |
| Supported assays | Space ticks or unticks the highlighted assay |
| Parameters | `u` user, `p` platform, `g` agent, `v` visibility, Space selects a row; **Set access for selected…** for many at once, then **Save policies** |

## Pages

- **Identity** shows each field with where its value came from: a
  structured source, edited by a person, or not found. Only documented keys
  are imported (ADR-0069); the README is never copied into a field. Authors
  take an optional ORCID iD, checked and stored as `https://orcid.org/…`.
- **Supported assays** is the SPLICE assay vocabulary as a tree. Tick what
  the pipeline can process; nothing is inferred for you.
- **Parameters** lists every imported parameter with who may supply it.
  Required parameters nobody may supply are shown as blockers until you
  assign them.
- **Outputs** starts empty: describe each output SPLICE should expose with
  the two-step editor (what is produced, then where it is published, with a
  path-pattern builder that checks an example path). **Browse routes** lists
  the routes the code publishes, read-only, and lets you exclude one with a
  reason. Set the analysis-output version yourself; it is not the pipeline
  version.
- **Software**, **Execution** and **Provenance** show the components and
  their images, the execution profiles with their native configs, and the
  RO-Crate strategy.
- **Review** groups what still blocks publication or readiness by page,
  with a **Fix** button per group that opens the exact page and field.
- **Publish** shows what will be written to `splice/`, asks before
  replacing edited files, and offers Export ZIP and a local commit
  afterwards.

## Working alongside your editor

The workspace writes the same draft files as the command line and changes
only the fields you edit. **View drafts** in the rail lists every draft and
opens one in `$VISUAL` or `$EDITOR`; **Browse sources** shows the pipeline's
files read-only.
If a draft changes on disk while a form is open, saving offers **Reload**,
**Compare** or **Cancel**; nothing is overwritten. Ctrl+R re-reads all files.

## Working with AI

Start with a provider to enable the dock:

```bash
nf-splice --user "Ada Lovelace" tui --provider claude
```

A remote provider asks for your consent in the dock before any repository
context is sent (or pass `--allow-remote-model`).

- **Ask** answers questions about the current page and selection with
  read-only tools. It never changes a file and can run while a session
  works.
- **Assist** prepares one step's proposal: a summary, evidence,
  uncertainties, the diff and a validation preview. Nothing changes until
  you **Approve**; you can request a revision, edit manually or reject it.
  A proposal made before the drafts changed is withdrawn, not applied.
- **Autonomous** works across the integration within the scope you approve.
  Publishing, replacing published files, exports and external checkers are
  separate grants, never implied. **Request pause** stops at the next safe
  point (the header shows *pause requested* until it has); **Stop** ends the
  session for good.

When the agent needs a decision it shows a **human intervention** card:
what it needs, why, and **Open the field**, which takes you to the exact
page and field. While the agent may be writing drafts, the workspace offers
to pause it before you edit. After your edit, **Resume same session**
continues from the current files. Closing the workspace while the agent
works pauses it first; the next start reopens the paused session. See
[AI-assisted sessions](assisted-sessions.md) and
[Autonomous integration](autonomous.md).

## Themes and terminal size

Six themes: SPLICE Night (default), SPLICE Day, Ocean Amber, Violet Gold,
High contrast dark and High contrast light. Every text colour meets a 4.5:1
contrast ratio and every control border 3:1, and states always carry a
symbol and words as well as a colour. Your choice is saved in your
configuration folder. The layout adapts from wide terminals to 80 columns;
below 60 columns by 20 lines the workspace asks for a larger window.

## Where you left off

The workspace remembers the current page between runs. It is stored in the
working copy's private `.splice-local/sessions/workspace/` and holds no
decisions; set `NF_SPLICE_SESSION_DIR` to keep it elsewhere, or start with
`nf-splice tui --no-session`.
