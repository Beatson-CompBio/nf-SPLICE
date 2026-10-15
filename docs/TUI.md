# Guided terminal wizard

`nf-splice tui` opens a step-by-step wizard. It authors and validates a
complete bundle without AI and without editing files by hand, while drafts
remain ordinary files you can edit in any editor.

```text
Welcome → Repository → Migration → Identity → Inputs → Outputs → Components
        → Execution profiles → Provenance → Drafts → Readiness → Build → Done
```

The assistant panel (Ctrl+A) is reachable from every step and is optional.

## Navigation and keys

| Key | Action |
| --- | --- |
| Ctrl+N / Continue | Next unlocked step |
| Escape / Back | Previous step |
| Ctrl+D / Finish later | Defer the step (publishing stays blocked) |
| Ctrl+R | Re-read every file from disk |
| F1 | Contextual help |
| Ctrl+A | Assistant panel |
| Ctrl+Q | Quit |

Inputs table: `u` user, `p` platform, `g` agent, `v` visibility, then
**Save policies**. Outputs table: `a` accept, `r` reject (enter a reason),
space marks candidates, `m` merges marked ones, `s` splits comma-separated
patterns.

The rail shows ✓ complete, ○ to do, ! blocked, » deferred and · locked.
Visiting a step unlocks the following ones; Build is locked until every layer
is ready. Status messages persist until a later success.

## Service boundary

Every view calls the same services as the CLI (ADR-0014, ADR-0038); choices
are saved as targeted, attributed draft patches with origin `manual_tui`.
Long operations run in worker threads. Candidate tables use stable candidate
IDs as row keys, so rediscovery cannot apply a review to the wrong row.

## Sessions

Sessions store only the current step, visited/deferred steps, half-typed form
values and draft hashes. They live under `NF_SPLICE_SESSION_DIR` (default
`$XDG_CACHE_HOME/nf-splice/sessions`), never in `splice/`. Deleting a session
loses no reviewed state. On resume, drafts changed outside the wizard are
reported. `--no-session` disables sessions. **Inspect only** never writes.

## Testing

`tests/test_tui.py` drives the wizard with Textual Pilot and requires the
CLI and TUI to produce identical drafts and byte-identical published files.
Reviewed text snapshots of every step are in `tests/snapshots/tui/`;
regenerate deliberately with `NF_SPLICE_UPDATE_SNAPSHOTS=1` and review the
diff.
