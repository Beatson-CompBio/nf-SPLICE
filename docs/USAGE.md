# nf-splice user guide

nf-splice prepares a Nextflow pipeline for the SPLICE platform. It reads your
repository, helps you review what it finds, and publishes a validated SPLICE
workflow bundle in `splice/`. Do the work yourself, or let the built-in
agentic AI do it with you or for you.

New to nf-splice? Start with **[Getting started](guide/getting-started.md)**.

## Start here

| Page | What you will learn |
| --- | --- |
| [Getting started](guide/getting-started.md) | Install nf-splice and publish your first bundle |
| [Core concepts](guide/concepts.md) | Layers, seeded drafts, review, readiness, and job/sample/run |

## Review the bundle, layer by layer

| Layer | Page | You decide |
| --- | --- | --- |
| Identity | [Identity](guide/identity.md) | Name, version, description, authors |
| Assay capabilities | [Assay capabilities](guide/assays.md) | Which assays the pipeline can process, by modality |
| Inputs | [Inputs](guide/inputs.md) | Who may change each parameter |
| Outputs | [Outputs](guide/outputs.md) | What the pipeline produces and who owns it |
| Components | [Components](guide/components.md) | Modules and container images |
| Execution profiles | [Execution profiles](guide/execution-profiles.md) | How the pipeline runs, and the default |
| Provenance | [Provenance](guide/provenance.md) | The RO-Crate, and attribution |

## Publish and run

| Page | Covers |
| --- | --- |
| [Publishing and updating](guide/publishing.md) | Publishing, new releases, hand edits, recovery |
| [Working copy and Git](guide/working-copy.md) | The safe integration copy, `.splice-local/`, local commits and pushing |
| [Export a ZIP archive](guide/export.md) | A verified archive of the bundle or the whole pipeline |
| [Job outputs](guide/job-outputs.md) | The `analysis_output.json` of each completed job |
| [Output routes and evidence](guide/output-coverage.md) | Alternative routes, example results and `nf-splice assess` |

## Ways of working

| Page | Covers |
| --- | --- |
| [Agentic AI](guide/agentic-ai.md) | The three ways to work, permissions, providers and privacy |
| [AI providers and accounts](guide/providers.md) | Claude, OpenAI, Codex and OpenCode: sign-in, local or remote, billing, limits |
| [Ask AI in manual mode](guide/ask-ai.md) | Doing it yourself, with read-only answers to your questions |
| [AI-assisted sessions](guide/assisted-sessions.md) | The agent proposes each stage; you approve, object or ask |
| [Autonomous integration](guide/autonomous.md) | The agent integrates the pipeline within a scope you approve |
| [The guided wizard](guide/wizard.md) | Reviewing everything step by step in the terminal |
| [Automation and CI](guide/automation.md) | Checks, JSON output and reproducible review in CI |

## Tutorials

| Tutorial | Page |
| --- | --- |
| Manual integration with Ask AI | [Ask AI in manual mode](guide/ask-ai.md#tutorial-manual-integration-with-ask-ai) |
| Assisted integration with disagreement and repair | [AI-assisted sessions](guide/assisted-sessions.md#tutorial-disagreement-and-repair) |
| Unattended integration and its report | [Autonomous integration](guide/autonomous.md#tutorial-an-unattended-integration) |
| A blocker, resolved in an assisted session | [Autonomous integration](guide/autonomous.md#tutorial-a-blocker-resolved-in-an-assisted-session) |
| Several Nextflow routes, one example run | [Output routes and evidence](guide/output-coverage.md#tutorial-several-routes-one-example) |
| No example results | [Output routes and evidence](guide/output-coverage.md#tutorial-no-example-results) |
| Optional nf-core checks | [Output routes and evidence](guide/output-coverage.md#tutorial-optional-nf-core-checks) |

## Reference

| Page | Covers |
| --- | --- |
| [Command reference](reference/cli.md) | Every command and option |
| [Troubleshooting](guide/troubleshooting.md) | Messages, codes and what to do |
| [Glossary](GLOSSARY.md) | Precise meanings of bundle, job, sample, run and other terms |
| [Building on SPLICE bundles](CONTRACTS.md) | File formats, for platform and tool developers |
