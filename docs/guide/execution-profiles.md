# Execution profiles

The execution-profiles layer lists the ways to run the pipeline on the
platform, each with its own Nextflow configuration, and names one default.
It is published as `execution-profiles.json` and `configs/<profile>.config`.

- **Draft:** `.splice-local/drafts/execution-profiles.draft.yaml` (profile
  metadata and references) and the native config files in
  `.splice-local/drafts/configs/` (the configuration itself)
- **Required:** at least one profile, exactly one default, and a config for
  each profile

## Metadata in YAML, configuration in Nextflow

The YAML describes each profile and points at its configuration; it never
holds configuration settings:

```yaml
default_profile: default
profiles:
  - id: default
    name: Default
    description: Local development on one machine.
    type: development          # test, development or production
    engine: nextflow
    executor: local
    container_engine: singularity
    config:
      draft: default.draft.config     # .splice-local/drafts/configs/default.draft.config
  - id: cluster
    name: Cluster
    description: Production on the department's Slurm cluster.
    type: production
    engine: nextflow
    executor: slurm
    container_engine: apptainer
    config:
      adopt: conf/cluster.config      # a repository config, published unchanged
```

`init` creates a `default` profile and its config scaffold (or carries over
the profiles and configs of an earlier `splice/` bundle). The scaffold is an
ordinary Nextflow config with two conventional sections:

```groovy
process {
    executor = 'local'
}

singularity {
    enabled    = true
    autoMounts = true
}

// ***** User Pipeline Input Params *****
params {
}

// ***** SPLICE Pipeline Input Params *****
params {
}
```

Put values users may change in the first `params` block and values the
deployment sets or fixes in the second. Add any other valid configuration:
`process` selectors, `executor`, `env`, `singularity`, `report`, `trace`,
`profiles`. nf-splice publishes the file as you wrote it (without its first
comment line) and never regenerates it.

To add a profile, create another `.draft.config` file and register it in
the YAML, or use **+ Add profile…** on the workspace's **Execution** page. From the command line:

```bash
nf-splice configure execution-profiles \
  --set default.type=development \
  --set default.description="Local development." \
  --set default.config_adopt=conf/local.config \
  --default default
```

Profiles detected in your `nextflow.config` are optional hints
(`nf-splice configure execution-profiles --export-unresolved FILE` lists
them).

## Checks

```bash
nf-splice draft validate execution-profiles
```

checks one default and unique IDs, that every config exists, that no config
contains a secret, a personal path, a literal account or a test setting in a
production profile, and that the parameter sections agree with the
[input access policy](inputs.md): a value in the user section must be one
users may change, and a value users may change must not be fixed in the
SPLICE section. Configs no profile uses are reported.

`nf-splice draft check-config <profile> --allow run_nextflow` asks Nextflow
for the effective configuration (it evaluates the configuration code, so it
needs your permission; no job is submitted) and reports memory requests that
would reach the scheduler.

## A cluster that rejects memory requests

Some Slurm sites, such as EPCC Cirrus for the CRUK deployment, reject jobs
with `#SBATCH --mem` and allot memory per CPU (about 2 GB per core). A
profile for such a site needs care, and `nf-splice draft resources` shows
what the pipeline asks for:

```bash
nf-splice draft resources --config cirrus
```

It reads the pipeline's `withLabel` and `withName` resources, the processes
using each label, every module that uses `task.memory` and whether it is
guarded, and, for the named config, whether memory is null for every
process and the memory per core. With both known it computes the CPUs each
label needs for its intended memory:

```text
withLabel: process_medium: 18 CPU(s) give 36 GB (intended 36 GB, declared 6)
UNGUARDED task.memory in QUALIMAP_RNASEQ at modules/local/qualimap/rnaseq/main.nf:25
```

The configuration then:

```groovy
process {
    executor = 'slurm'
    withName: '.*' {
        memory = null                   // no --mem reaches Slurm
    }
    withLabel: process_medium {
        cpus = 18                       // 36 GB at 2 GB per core
    }
}
env {
    NXF_EXECUTOR_MEM_GIGA_PER_CORE = 2
}
```

Check every module the analysis lists: an unguarded `task.memory` use fails
when memory is null, and a guarded one falls back to a default (FastQC then
uses its minimum, 100 MB per thread). Keep the account, partition, QoS and
paths as values the deployment supplies (from parameters or the
environment), and confirm the effective configuration before relying on it.
Cirrus is one deployment, not a default for every user of nf-splice.

## What never goes into a profile

Accounts, queues, private paths, credentials and organisation addresses are
deployment configuration. nf-splice blocks configurations that contain them.

Field reference:
[`execution-profiles.json`](../schemas/execution-profiles/README.md).
