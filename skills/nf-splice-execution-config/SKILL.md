---
name: nf-splice-execution-config
description: Author execution profiles - metadata and references in execution-profiles.draft.yaml, the configuration itself in native Nextflow .draft.config files - including site profiles where the scheduler must not receive memory requests (memory = null, CPUs sized by memory per core, every task.memory use checked). Use at the execution-profiles stage.
---

# nf-splice execution configuration

## When to use

Use this skill when authoring or reviewing execution profiles, writing a
profile's Nextflow configuration, or preparing a site profile for an HPC
cluster.

## Prerequisites

- `nf-splice init` seeded a `default` profile with a native config scaffold
  (or the profiles and configs of an earlier `splice/` bundle). Each profile
  names its configuration: `config: {draft: <name>.draft.config}` (a file in
  `.splice-local/drafts/configs/`) or `config: {adopt: conf/x.config}` (a
  repository config published unchanged).

## Workflow

1. `read_config` lists the configs; read the one you work on, and
   `conf/base.config`, the process labels and `withName` selectors of the
   pipeline.
2. Keep the profile YAML to identity, description, type, executor,
   container engine, site parameters and the config reference. All
   configuration goes in the native file, written with `write_config` as
   complete Nextflow configuration; never put directives in the YAML.
   The container engine is optional metadata (ADR-0070): record it only
   where a configuration or site document declares one, otherwise leave it
   unset — the site decides which engine consumes the declared images.
   Never invent an engine to satisfy a check; a profile naming an engine its
   own config does not enable is reported as a contradiction.
3. The two conventional sections hold parameter values:
   `// ***** User Pipeline Input Params *****` for values users may change
   and `// ***** SPLICE Pipeline Input Params *****` for values the
   deployment sets or fixes. Add any other valid configuration around them.
   Any executor Nextflow supports is valid (`local`, `slurm`, `lsf`, `sge`,
   `pbspro`, `k8s`, `awsbatch`, `google-batch`, ...), and any engine:
   nothing about one site or scheduler is a default.
4. **Site profiles without memory requests**, when the evidence shows the
   site needs one (for example a Slurm site that rejects
   `#SBATCH --mem` and allots memory per CPU, such as 2 GB per core):
   - `analyse_execution` with the config: label and selector resources,
     memory = null coverage, memory per core, and every `task.memory` use;
   - set memory to null for every process (`withName: '.*' { memory = null }`)
     and `env { NXF_EXECUTOR_MEM_GIGA_PER_CORE = 2 }` (the site's value);
   - size CPUs per label or process from the memory each needs:
     `ceil(memory / memory_per_core)`, never fewer than it asked for, within
     the site's limits; never give every process the same maximum;
   - modules that use `task.memory` without a guard fail when memory is
     null; guarded ones fall back to a derived default (FastQC to 100 MB).
     Propose a supported configuration for them or record a blocker; never
     edit modules silently;
   - keep accounts, partitions, QoS and paths as deployment values (from
     parameters or the environment), never literals you invented.
5. One profile is the default (`default_profile`). Other sites (local,
   ARCHER2, EIDF) get their own profiles and files.
6. Ask the person to check the effective configuration with
   `nf-splice draft check-config <profile> --allow run_nextflow`; no job is
   ever submitted.

## Verification gates

- `validate_layer` on `execution-profiles` reports no errors: one default,
  unique IDs, existing configs, no secrets, personal paths or literal
  accounts, parameter sections consistent with the input access policy.

## Failure handling

- `missing_config_draft`: the profile names a file that does not exist.
- `section_policy`: a value in a section conflicts with who may change that
  parameter.
- `unreferenced_config`: a config file no profile uses.

## Evidence reporting

Cite the selectors and modules behind each resource decision, and state
what only a dry run or a real job could confirm.

## Safety boundaries

Never submit jobs, never write secrets or site credentials into a config,
and never claim a configuration runs on a cluster without a check that ran.
