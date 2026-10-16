# Schema reference

Key-by-key references for every format in a SPLICE workflow bundle. Start
with [Building on SPLICE bundles](../CONTRACTS.md) for how the files fit
together, how to read them and how they are versioned.
To give a coding agent the same knowledge, use the
[bundle consumer kit](../../bundle-consumer-kit/README.md).

## Contract files

| File | Reference | Definition | Example |
| --- | --- | --- | --- |
| `bundle.json` | [bundle](bundle/README.md) | [schema](bundle/v0.3.0/schema.json) | [example](bundle/v0.3.0/example.json) |
| `inputs.schema.json` | [inputs](inputs/README.md) | [schema](inputs/v0.3.0/schema.json) | [example](inputs/v0.3.0/example.json) |
| `outputs.schema.json` | [outputs](outputs/README.md) | [schema](outputs/v0.3.0/schema.json) | [example](outputs/v0.3.0/example.json) |
| `components.json` | [components](components/README.md) | [schema](components/v0.3.0/schema.json) | [example](components/v0.3.0/example.json) |
| `execution-profiles.json` | [execution-profiles](execution-profiles/README.md) | [schema](execution-profiles/v0.3.0/schema.json) | [example](execution-profiles/v0.3.0/example.json) |

## Other formats

| Format | Reference |
| --- | --- |
| `analysis_output.json`, one per completed job | [analysis-output.md](analysis-output.md) |
| `outputs.yaml`, RO-Crate, profile configurations, lock, README | [companion-files.md](companion-files.md) |

The contract reference pages are generated from the packaged definitions
and [`fields.yaml`](fields.yaml) by `scripts/generate_schema_docs.py`.
