# Autonomous integration

In autonomous mode the agent integrates the pipeline with SPLICE on its own:
it creates and reviews every draft, builds the bundle, verifies it and
writes a report, without asking you at each stage. You decide the scope
before it starts. Anything it cannot decide with sufficient evidence is
reported as a blocker for you to resolve afterwards.

## Approve the scope and start

```bash
nf-splice --actor "Ada Lovelace" session start --mode autonomous --provider claude --allow-remote-model --example-output ../results --max-tool-calls 300 --max-budget-usd 5
```

By starting the run you approve its scope:

| Scope | Default | Change with |
| --- | --- | --- |
| Edit drafts in `.splice-local/drafts/` | Allowed | — |
| Build the bundle into `splice/` | Allowed | — |
| Replace hand-edited published files | Not allowed | `--allow overwrite` |
| Run nf-core lint if installed | Not allowed | `--allow external_tools --allow run_nextflow --allow network` |
| Tool calls, attempts per stage, time per turn, spending | 300, 3, 600 s, no cap | `--max-tool-calls`, `--max-stage-attempts`, `--turn-timeout`, `--max-budget-usd` |

The agent never runs your pipeline, installs software, uploads data, reads
secrets or changes your pipeline's code, whatever the scope.

## How the run works

For each stage (discover, identity, inputs, outputs, components, execution
profiles, provenance, cross-layer validation, build, verify), the agent
makes the routine decisions and nf-splice validates the stage. A stage is
complete only when its validation passes. If it does not, the agent tries
again with the remaining issues, but only while it is making progress. If
it still cannot finish, it records a blocker: the decision it could not
make, the file affected, the checks it tried and a suggestion. Stages that
do not depend on the blocked one continue.

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
   nf-splice --actor "Ada Lovelace" session resume --mode assisted
   ```

   Completed stages are not repeated. The agent proposes the outputs stage
   again.

3. Answer or object, for example *"Yes: users download quant.sf for each
   sample."* Approve the revised proposal, then approve the build.

4. `nf-splice session report` now says `complete`.

## Stop or switch

Press **Stop** in the wizard, or switch the paused session to another mode:

```bash
nf-splice session pause
nf-splice --actor "Ada Lovelace" session resume --mode assisted
```

Switching keeps the drafts, the evidence and the history.

## In the wizard

Choose **Autonomous integration** on the Welcome step. The form shows the
scope; **Approve scope and start** begins the run. The view shows progress,
a **Stop** button and, at the end, the report and **Resume in assisted
mode**.
