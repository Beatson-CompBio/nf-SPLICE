# AI-assisted sessions

In an AI-assisted session the agent does the integration work stage by
stage, and you stay in charge. For each stage it shows you exactly what it
will change, why, what it is unsure about and what the validation will say.
Nothing changes until you approve. You can object, ask questions or answer
its questions at any point.

## Start a session

From the root of your pipeline repository:

```bash
nf-splice --actor "Ada Lovelace" session start --mode assisted --provider claude --allow-remote-model --example-output ../results
```

- `--actor` is your name as recorded with each approval. Set
  `NF_SPLICE_ACTOR` to avoid typing it.
- `--example-output` is optional: the results directory (or a saved listing)
  of one completed run, which the agent may read as evidence.

In a terminal, the session becomes a conversation:

```text
Session session-20261015-101500-a1b2c3: assisted, awaiting approval
Proposal proposal-4 (revision 1) for outputs:
Review every published output route into the catalogue.
Operations:
- accept_output {"candidate_id": "output:5c0e...", "output": {"key": "star_alignment", ...}}
- reject_output {"candidate_id": "output:91aa...", "reason": "Not observed in the example run"}
Evidence:
- modules/local/star/main.nf:3 publishDir "${params.outdir}/star"
Uncertainties:
- HISAT2 output was not observed in the example run
Diff:
--- a/.splice-local/drafts/outputs.draft.yaml
+++ b/.splice-local/drafts/outputs.draft.yaml
...
[a]pprove, [o]bject, ask a [q]uestion, [p]ause or [c]ancel (q):
```

The diff and the validation result come from running the proposed changes
on a private copy of your repository. Your files are untouched.

## Respond to a proposal

| You want to | In the terminal | As a command |
| --- | --- | --- |
| Apply it | `a` | `nf-splice session approve` |
| Say it is wrong | `o`, then explain | `nf-splice session object "..."` |
| Ask about it | `q`, then ask | `nf-splice session ask "..."` |
| Answer the agent's question | `r`, then answer | `nf-splice session reply "..."` |
| Stop for now | `p` | `nf-splice session pause` |

When you approve, nf-splice applies exactly the operations you saw, then
runs the stage's validation. If it passes, the agent moves on and proposes
the next stage. If it fails, the agent proposes a repair, and you approve it
or not.

Questions and objections never count as approval, and neither does
silence.

## When you disagree

When you object, the agent investigates your concern against the code, its
tool results and the example output, and tells you whether the evidence
supports it. If it does, the agent revises the proposal and asks again. If
it does not, it explains the evidence and asks how you want to proceed. It
does not assume you are wrong, and it does not accept a correction the
evidence contradicts.

## Tutorial: disagreement and repair

The pipeline has two alternative aligners (STAR and HISAT2), optional Salmon
quantification and conditional QC. Your example run used STAR.

1. Start the session as above and approve the drafts, identity and inputs
   proposals after reading each diff.

2. The outputs proposal accepts the STAR outputs but rejects the HISAT2
   alignment because it was *"Not observed in the example run"*.

3. Object:

   ```bash
   nf-splice --actor "Ada Lovelace" session object "HISAT2 is an alternative aligner. It must stay in the catalogue even though the example used STAR."
   ```

4. The agent reads `main.nf` and the route analysis, finds that
   `HISAT2_ALIGN` runs when `params.aligner` is not `star` and that its BAM
   files are published by the `withName: 'HISAT2_ALIGN'` rule, and records:

   ```text
   [agent] Assessment: supported. HISAT2_ALIGN runs when params.aligner is not
   'star' and its BAM files are published by the withName rule; the example
   only took the STAR route.
   ```

   It then shows revision 2 of the proposal, now accepting
   `hisat2_alignment`, with the new diff.

5. Object to something the evidence does not support, for example *"Also
   publish the samtools sorted BAM"*. The agent checks the route analysis,
   finds that `SAMTOOLS_SORT` has no publication rule (an intermediate), says
   so, and keeps the current proposal.

6. Approve revision 2. The outputs validation passes and the agent proposes
   the next stage.

7. Continue until the build proposal; approve it, then read the report:

   ```bash
   nf-splice session report
   ```

## Pause, edit and continue

Switch to manual mode at any time to edit drafts yourself:

```bash
nf-splice session resume --mode manual
nf-splice configure outputs --contract-version 1.1.0
nf-splice --actor "Ada Lovelace" session resume --mode assisted
```

When the session continues, nf-splice notices files that changed outside
it, checks completed stages again and withdraws any proposal made before
your edit. An out-of-date proposal can never be approved.

## In the wizard

```bash
nf-splice tui --provider claude --allow-remote-model
```

Choose **AI-assisted session** on the Welcome step. The session view shows
the stage progress, the conversation, the proposal with its diff, and
**Approve**, **Object**, **Reply**, **Ask**, **Continue** and **Pause**. It
uses the same session files as the commands, so you can start in one and
continue in the other.

## Undo an approved change

Before applying each approved proposal, nf-splice saves a checkpoint of
`splice/`. To return to one:

```bash
nf-splice --actor "Ada Lovelace" session rollback checkpoint-3
```

The session report lists the checkpoints.
