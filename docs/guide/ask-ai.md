# Ask AI in manual mode

In manual mode you do the integration yourself, with the wizard or commands.
*Ask AI* answers questions along the way. It reads your repository and
drafts but cannot change anything, and it never takes over the work.

## Ask from the command line

```bash
nf-splice ask "Which outputs only appear when Salmon runs?" --provider claude --allow-remote-model
```

Point it at what you are looking at for a sharper answer:

```bash
nf-splice ask "Why is this field an error?" --layer outputs --pointer /outputs/2/path_patterns --provider claude --allow-remote-model
nf-splice ask "What does this mean?" --error "route_not_covered: HISAT2_ALIGN publishes hisat2/*.bam" --provider claude --allow-remote-model
```

| Option | Use |
| --- | --- |
| `--layer`, `--pointer` | The draft and field you are looking at |
| `--error` | An error message to explain |
| `--candidate` | A candidate identifier to explain |
| `--example-output` | Results of a run the answer may look at |
| `--json` | The answer and the read-only tool calls behind it |

## Ask from the wizard

```bash
nf-splice tui --provider claude --allow-remote-model
```

Press **Ctrl+A** on any step, type a question and choose **Ask**. The answer
knows which step you are on.

## Tutorial: manual integration with Ask AI

You will review a pipeline yourself and ask AI two questions on the way.

1. Create the drafts and open the wizard:

   ```bash
   nf-splice init
   nf-splice tui --provider claude --allow-remote-model
   ```

2. Work through **Identity** and **Inputs** as usual (see
   [Getting started](getting-started.md)).

3. On **Outputs**, the catalogue has a `hisat2_align_bam` entry that your test
   run did not produce. Press Ctrl+A and ask *"Does HISAT2_ALIGN always run?"*.
   The answer cites `main.nf`: HISAT2 runs only when `params.aligner` is not
   `star`, so it is an alternative route and belongs in the catalogue.

4. Keep it, with a description you choose. Ask AI did not change the draft;
   you did.

5. On **Components**, ask *"Why is this container reference unresolved?"*,
   then decide.

6. Finish the remaining steps and build.

Everything in the bundle was decided by you. Every answer came from reading
your files with read-only tools.
