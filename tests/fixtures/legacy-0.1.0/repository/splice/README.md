# legacy-example SPLICE pipeline bundle

This directory is the static integration harness consumed by the SPLICE platform. It complements the pipeline's native Nextflow and nf-core files.

## Contents

| File | Purpose |
| --- | --- |
| `bundle.json` | Static bundle entry point. |
| `inputs.schema.json` | Reviewed platform-configurable inputs. |
| `outputs.yaml` | Reviewed output catalogue. |
| `outputs.schema.json` | Schema for per-run analysis_output.json. |
| `ro-crate-metadata.json` | Developer-generated workflow RO-Crate. |
| `components.json` | Reviewed software and container inventory. |
| `execution-profiles.json` | Supported execution profile catalogue. |
| `nf-splice.lock.json` | Generator, source, and content provenance. |
| `configs/profile-local-6c6f63616c.config` | Reviewed execution configuration. |

## Ownership

`nf-splice.yaml` records reviewed developer decisions. Generated contracts must be changed by reviewing source evidence and rebuilding, not by editing materialised files directly. The root RO-Crate and selected source configs remain developer-owned and are copied unchanged.

Run-specific results, reports, logs, and `analysis_output.json` belong in a completed run's output directory, not in this static bundle.
