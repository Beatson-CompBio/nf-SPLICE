# nf-splice user guide

nf-splice prepares a Nextflow pipeline for the SPLICE platform. It reads your
repository, helps you review what it finds, and publishes a validated SPLICE
workflow bundle in `splice/`.

New to nf-splice? Start with **[Getting started](guide/getting-started.md)**.

## Start here

| Page | What you will learn |
| --- | --- |
| [Getting started](guide/getting-started.md) | Install nf-splice and publish your first bundle |
| [Core concepts](guide/concepts.md) | Layers, drafts, review, and job/sample/run |

## Review the bundle, layer by layer

| Layer | Page | You decide |
| --- | --- | --- |
| Identity | [Identity](guide/identity.md) | Name, version, description, authors |
| Inputs | [Inputs](guide/inputs.md) | Who may change each parameter |
| Outputs | [Outputs](guide/outputs.md) | What the pipeline produces and who owns it |
| Components | [Components](guide/components.md) | Modules and container images |
| Execution profiles | [Execution profiles](guide/execution-profiles.md) | How the pipeline runs, and the default |
| Provenance | [Provenance](guide/provenance.md) | The RO-Crate, and attribution |

## Publish and run

| Page | Covers |
| --- | --- |
| [Publishing and updating](guide/publishing.md) | Publishing, new releases, hand edits, recovery |
| [Job outputs](guide/job-outputs.md) | The `analysis_output.json` of each completed job |
| [Output routes and evidence](guide/output-coverage.md) | Alternative routes, example results and `nf-splice assess` |

## Ways of working

| Page | Covers |
| --- | --- |
| [The guided wizard](guide/wizard.md) | Reviewing everything step by step in the terminal |
| [Automation and CI](guide/automation.md) | Checks, JSON output and reproducible review in CI |
| [AI assistance](guide/ai-assistant.md) | Optional suggestions, always approved by a person |

## Tutorials

| Tutorial | Page |
| --- | --- |
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
