# Autonomous integration

In autonomous mode the agent integrates the pipeline with SPLICE on its own:
it creates and reviews every draft, builds the bundle, verifies it and
writes a report, without asking you at each stage. You decide the scope
before it starts. Anything it cannot decide with sufficient evidence is
reported as a blocker for you to resolve afterwards.

## Approve the scope and start

```bash
nf-splice --user "Ada Lovelace" session start --mode autonomous --provider claude --allow-remote-model --example-output ../results --max-tool-calls 300 --max-budget-usd 5
```

By starting the run you approve its scope:

| Scope | Default | Change with |
| --- | --- | --- |
| Edit drafts in `.splice-local/drafts/` | Allowed | — |
| Build the bundle into `splice/` | Allowed | — |
| Replace hand-edited published files | Not allowed | `--allow overwrite` |
| Run nf-core lint if installed | Not allowed | `--allow external_tools --allow run_nextflow --allow network` |
| Tool calls, attempts per stage, time per turn, spending | 1500, 3, 1800 s, no cap | `--max-tool-calls`, `--max-stage-attempts`, `--turn-timeout`, `--max-budget-usd` |
| Reasoning effort | `high` | `--reasoning-effort` |
| Review layers that already validate | always | `--review reuse-unchanged` |

The agent never runs your pipeline, installs software, uploads data, reads
secrets or changes your pipeline's code, whatever the scope.

## How the run works

For each layer (identity, inputs, outputs, components, execution profiles,
provenance), the agent investigates the pipeline's code, configs and
documentation, authors the draft (often rewriting what `init` seeded),
validates it, and revises while it makes progress. A layer is complete only
when its validation passes **and** the agent has recorded a review that
inspected the evidence this layer needs in your pipeline, assessed the
draft and cited its support (see
[what a finished review needs](assisted-sessions.md#what-a-finished-review-needs));
a draft that already validated is still reviewed. A finished run reports
`Published and ready for SPLICE ingestion` only when every readiness
dimension is ready; otherwise it is partial, with the reasons.
If it cannot decide something from the evidence, it records a blocker: the
decision, the alternatives and the evidence for each, the checks it tried
and what would decide it. The latest useful draft stays in place, even if it
does not validate yet, and stages that do not depend on the blocked one
continue. Then cross-layer validation, build and verification run.

Every change is recorded as the agent's decision under your approved scope,
never as your review, and a checkpoint is saved before each stage.

## Read the report

When the run finishes, the report is printed and saved:

```bash
nf-splice session report
```

```text
Session session-20261015-110200-c4d5e6 (autonomous): complete
Complete: every stage passed its deterministic checks and the published bundle is valid.

Stages:
  Discover: completed - every draft exists
  Identity: completed - bundle: ready
  ...
  Build: completed - valid bundle (6 contract files)
  Verify: completed - contract valid; observed compatible

Verified artefacts:
  splice/bundle.json
  ...

Contract validity: valid
Observed-output compatibility: compatible
Coverage: 7 published route(s) were identified statically: 7 covered by the catalogue, ...
```

`complete` means every stage passed and the published bundle is valid. Any
other result is reported as `partial`, with its blockers.

## Tutorial: an unattended integration

1. Run the pipeline once and keep its results, for example in `../results`.
2. Start the run as above.
3. Read the report. Check the verified artefacts, the three assessment
   results and the limitations.
4. Review the diff of `splice/` in Git and commit it.

## Tutorial: a blocker, resolved in an assisted session

1. Start an autonomous run. Suppose the agent cannot tell whether Salmon's
   `quant.sf` is meant for platform users. The report ends:

   ```text
   Session session-20261015-113000-f7a8b9 (autonomous): partial
   Partial: 1 unresolved blocker(s); the bundle is not built and valid.
   ...
   Blockers:
     [outputs] Whether Salmon quantification is a platform output
       affects: .splice-local/drafts/outputs.draft.yaml
       suggestion: Confirm whether users need quant.sf.
   ```

   Identity, inputs, components, profiles and provenance are complete;
   validation and the build are blocked because they depend on outputs.

2. Resume the same session in assisted mode:

   ```bash
   nf-splice --user "Ada Lovelace" session resume --mode assisted
   ```

   Completed stages are not repeated. The agent proposes the outputs stage
   again.

3. Answer or object, for example *"Yes: users download quant.sf for each
   sample."* Approve the revised proposal, then approve the build.

4. `nf-splice session report` now says `complete`.

## Stop or switch

Press **Stop** in the workspace's dock, or switch the paused session to another mode:

```bash
nf-splice session pause
nf-splice --user "Ada Lovelace" session resume --mode assisted
```

Switching keeps the drafts, the evidence and the history.

## In the workspace

Choose **Start autonomous integration** on Welcome, or the dock's
**Autonomous** card. The card shows the scope: reading sources and editing
the private drafts always, and publishing, replacing published files,
exports and external checkers as separate grants, with a tool-call budget.
**Approve scope and start** begins the run. The card shows each stage, the
recent activity, **Request pause** (the header says *pause requested* until
the agent has reached a safe point) and **Stop**. A **human intervention**
card names the decision, why, the evidence, and **Open the field**; edit it
and choose **Resume same session**. See [The workspace](workspace.md).
