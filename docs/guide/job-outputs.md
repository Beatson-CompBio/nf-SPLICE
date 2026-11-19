# Job outputs

After each job finishes, the platform needs an inventory of what the job
published: `analysis_output.json`. nf-splice generates it from the job's
results and the published output catalogue, and validates it before writing.
It lists only the files this job produced; catalogue outputs from routes the
job did not take are simply absent, which is valid.

This step usually runs on the platform, not on a developer's machine.

## Generate the inventory

```bash
nf-splice analysis-output generate \
  --publish-directory results \
  --job-metadata job.json \
  --sample-metadata samples.csv \
  --output-directory results
```

| Option | Purpose |
| --- | --- |
| `--publish-directory` | The job's results directory. nf-splice walks it. |
| `--job-metadata` | Job identifiers and details, see below. |
| `--sample-metadata` | Optional sample sheet linking runs to samples. |
| `--output-directory` | Where to write `analysis_output.json`. |
| `--checksum sha256` | Optional: record a checksum of each file. |

Instead of `--publish-directory`, you can give `--native-output-index` (an
index file the pipeline wrote) or `--output-tree` (a saved listing). Supply
exactly one of the three.

Run the command from the pipeline repository, or point to it with
`--repository`. It reads the published `splice/outputs.schema.json`.

## Job metadata

`job.json` identifies the job. At least one job identifier is required:

```json
{
  "job_id_short": "A123",
  "job_id_long": "3f2c8a3e-6b1d-4c4e-9a52-1f0d2b7c9e10",
  "config_profile": "slurm",
  "execution_timestamp": "2026-10-15T09:30:00Z",
  "job_metadata": {
    "engine": "nextflow",
    "nextflow": {"session_id": "7e1d9c2b-5a4f-4e3b-8c6d-0a1b2c3d4e5f", "run_name": "happy_turing"}
  }
}
```

## Sample sheet

A CSV with a sample column (`sample` or `sample_id`) and, for run-level
outputs whose path does not include the sample, a `run_id` column:

```text
sample,run_id
S1,S1_L001
S1,S1_L002
S2,S2_L001
```

## When a file is not in the catalogue

If the job published a file that matches no reviewed output, generation
stops and lists the file. Either add the output to the catalogue (see
[Outputs](outputs.md)) and publish again, or leave such files out of the
inventory explicitly with `--allow-unclassified`.

## Validate an existing inventory

```bash
nf-splice analysis-output validate results/analysis_output.json
```

Field reference: [`analysis_output.json`](../schemas/analysis-output.md).
