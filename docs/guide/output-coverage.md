# Output routes and evidence

A pipeline can publish different files depending on its parameters: one of
several aligners, an optional quantifier, quality control that can be
switched off. One run shows only some of them. This page explains how
nf-splice finds every output a pipeline may publish, how example results
are used, and how to check the result.

## Two different things

| | Output catalogue | `analysis_output.json` |
| --- | --- | --- |
| Lives in | `splice/outputs.schema.json` and `splice/outputs.yaml` | The results of one job |
| Lists | Every output type the pipeline **may** publish, across its routes | The files **one job actually** published |
| Built from | Your review of the pipeline's code, helped by examples | That job's files, classified against the catalogue |

A job's `analysis_output.json` never needs to contain every catalogue type.
A run that used STAR has no HISAT2 files, and that is correct.

## How nf-splice finds outputs

nf-splice reads your pipeline's code without running it. A process's
`output:` block only says what the process produces in its work directory;
a file is published only if a publication rule copies it to the results:

- `publishDir` in the process,
- `publishDir` in a configuration `withName` selector,
- the configuration's default `publishDir` rule.

It follows these rules, including `pattern` filters, `enabled` flags and
`saveAs`, and records the `if`/`else` conditions under which each process
runs. Only published outputs become candidates for review. Intermediates,
such as a sorting step whose output nothing publishes, are listed
separately and never offered.

Each published route gets a status:

| Status | Meaning |
| --- | --- |
| `confirmed_from_code` | An explicit rule publishes it and the process is invoked |
| `inferred_unverified` | Published by a default rule, `saveAs` or a path with run-time values; check it |
| `unresolved` | The publication path is computed at run time |
| `not_reachable` | The process is never invoked |
| `observed_in_example` | Also seen in an example run |

## Using example results

Example results are evidence from one run. Give nf-splice the results
directory, a saved `ls -R` or `tree` listing, or an output index:

```bash
nf-splice configure outputs --example-output-tree ../results
nf-splice configure outputs --publish-directory ../results
```

Examples improve candidates (for example, per-sample file names) and reveal
mistakes, but never remove supported routes that the run did not take.
nf-splice never follows symbolic links in an example or reads outside it.

## Check: three separate results

```bash
nf-splice assess --example-output ../results-star
```

```text
Contract validity: valid
Observed-output compatibility: compatible
  ../results-star: 12 entries, 9 classified, 0 unclassified, 0 ambiguous; analysis_output.json valid
    not observed (allowed): hisat2_alignment, salmon_quantification
Coverage assessment:
  7 published route(s) were identified statically: 7 covered by the catalogue,
  0 excluded by review, 0 not covered, 0 unresolved. 5 were observed in example
  output. Static analysis cannot prove completeness: ...
Optional checks:
  nf-core pipelines lint: not_applicable (...)
```

| Result | What it shows | What it does not show |
| --- | --- | --- |
| Contract validity | The bundle's files and their cross-references are valid | That every output is catalogued |
| Observed-output compatibility | Each example's files are classified and a real `analysis_output.json` validates | That other routes are covered |
| Coverage assessment | Which published routes the catalogue covers | Outputs only a run could reveal |

For the check, `analysis_output.json` is generated with a placeholder job
identity; `--write-analysis-output` keeps the generated files. `assess`
exits with status 2 when the contract is invalid or an example has
unclassified or ambiguous files. Use `--json` in CI.

## Tutorial: several routes, one example

The pipeline aligns with STAR or HISAT2, can quantify with Salmon and can
skip QC. You have results from one STAR run with QC.

1. Create drafts and discover outputs with the example:

   ```bash
   nf-splice init --accept-detected
   nf-splice configure outputs --example-output-tree ../results-star --export-unresolved -
   ```

   Candidates include both `star_align_bam` and `hisat2_align_bam`, Salmon's
   `quant` and MultiQC's `report`, but no samtools sorted BAM.

2. Accept every supported route, including HISAT2 and Salmon, and reject
   anything that is not a platform output (see [Outputs](outputs.md)).

3. Build, then check:

   ```bash
   nf-splice build all
   nf-splice assess --example-output ../results-star
   ```

   The example is compatible; HISAT2 and Salmon are listed as *not observed
   (allowed)*; coverage reports every route as covered.

4. Add an unexpected file to a copy of the results and check again: it is
   reported as unclassified and `assess` exits with status 2. Generating a
   job's inventory also fails until you add the output to the catalogue, or
   leave such files out explicitly with
   `nf-splice analysis-output generate --allow-unclassified`, which lists
   every omitted file.

## Tutorial: no example results

You can integrate a pipeline without any results:

```bash
nf-splice init --accept-detected
nf-splice configure outputs --export-unresolved -
nf-splice assess
```

Candidates come from the code alone. `assess` reports observed-output
compatibility as *not assessed*: that is not a failure, only less evidence.
Path patterns for per-sample files are derived from the code; check the ones
marked `inferred_unverified` against the module source before accepting
them.

## Tutorial: optional nf-core checks

For nf-core pipelines, nf-splice can also run `nf-core pipelines lint`, when
nf-core 3.x or 4.x and Nextflow are installed. Because lint runs
`nextflow config` and may contact the network, it runs only with your
explicit permission:

```bash
nf-splice assess --allow external_tools --allow run_nextflow --allow network
```

```text
Optional checks:
  nf-core pipelines lint: passed_with_warnings (212 passed, 3 warned)
```

Without the permissions, or without nf-core or Nextflow, the check is
reported as `not_run` with the reason. For pipelines that are not nf-core
pipelines it is `not_applicable`. A check that did not run is never reported
as passed.
