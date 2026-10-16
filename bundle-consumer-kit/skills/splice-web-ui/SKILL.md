---
name: splice-web-ui
description: Design and build web interfaces on SPLICE bundles and job results: the workflow catalogue and detail pages, parameter launch forms, execution profile choice and results pages. Says which keys and labels to display, which are internal, how to present access and visibility, and what must be enforced on the server. Use for any front-end or design work that shows SPLICE data.
---

# Web interfaces on SPLICE bundles

## When to use

Use this skill when you design or build screens that show workflows, let
people launch jobs or show job results. The data may come straight from
bundle files or from the database (see `splice-bundle-ingestion`); the
meaning of each field is the same. For results, also read
`splice-analysis-output`.

## General rules

- Show the display keys below; keep identifiers (`id`, `key`, `binding`,
  container references) for links, filters and tooltips.
- Every string is plain text from a reviewed file but is still untrusted:
  escape it. Descriptions may contain Markdown-like text; render it, if at
  all, with a sanitising Markdown renderer.
- Optional keys are often absent. Design for absence with a fallback, never
  with an empty label.
- Never show draft or internal tooling details: `generated_by`,
  `x-splice-contract`, `x-splice-source`, lock contents and `evidence` are
  for diagnostics, not for users.

## Workflow catalogue and detail page

From `bundle.json` → `pipeline` (one workflow version):

| Show | Key | Fallback and notes |
| --- | --- | --- |
| Name | `title` | `name` |
| Version | `version` | Always present. Link to `release_url` when present |
| Summary (cards, search results) | `description` | One or two sentences |
| Long description (detail page) | `long_description` | `description` |
| Tags and filters | `keywords`, `pipeline_type`, `modality` | Free text, no fixed vocabulary; build filters from the values present |
| Authors | `authors[]`: `name`, `affiliation`, `orcid`, `role` | Keep the given order (citation order); link `orcid` |
| Funding | `funders[]`: `name`, `award_title`, `award_id`, `url` | |
| How to cite | `citation`: `text`, else a DOI link (`https://doi.org/` + `doi`), else `url` | Offer `cff_path` as "CITATION.cff in the repository" |
| Licence | `licence` (SPDX identifier), `licence_url` | |
| Links | `repository_url`, `documentation_url`, `project_url`, `support_url` | Only those present |
| Released | `released_at` | |
| Contacts | `bundle.json` → `maintainers[]`: `name`, `role`, `affiliation`, `contact_url`, `email` | Personal data published with consent; show only where your privacy policy allows |
| Engine | `engine`, `engine_version_min` | For technical details sections |

Also useful on a detail page: tools used, from `components.json` →
`components[]` (`tool.name`, `tool.version`), and the output catalogue
(below), so people know what results to expect.

## Launch form

Build the form from `inputs.schema.json`. A parameter is a property under
`properties` or under `$defs.<group>.properties`; the submitted parameter
object is always flat.

**Sections.** One section per `$defs` group, titled with the group's
`title` and introduced by its `description`. Parameters outside groups go in
a general section.

**Who may edit.** `x-splice-access.editable_by` decides, per parameter:

| `editable_by` contains | Show as |
| --- | --- |
| `user` | An editable field |
| only `platform` | Not editable by the person; the platform sets it. Usually hidden, or read-only with the value the platform will use |
| only `agent` | Set by an AI agent acting for the person; not a free field |
| nothing (empty) | Fixed: show the `default` read-only, if at all |

Enforce the same rule on the server: reject any submitted value the
submitter is not allowed to set. The form is a convenience, not the
control.

**Visibility and order.** `x-splice-ui.visibility`: `standard` in the main
form, `advanced` in a collapsed advanced section, `hidden` not shown (it
still exists and keeps its access rule). Order fields by `x-splice-ui.order`
(lowest first), then by their order in the file. The contract defines no
default visibility; treat a parameter without `x-splice-ui.visibility` as
`standard`.

**Labels and help.**

| Element | Key | Fallback |
| --- | --- | --- |
| Label | the parameter's `title` | its name, humanised |
| Short help under the field | `description` | |
| Extended help (tooltip or expandable) | `x-splice-ui.help_text` | nf-schema `help_text` |
| Icon | `x-splice-ui.icon` | nf-schema `fa_icon` |

**Widgets and validation.** Choose widgets from standard JSON Schema:
`enum` → select, `boolean` → toggle, `integer` or `number` with `minimum`
and `maximum` → number field, `pattern` and `format` → text with
validation, `default` → initial value. Validate the whole submitted object
against `inputs.schema.json` (JSON Schema 2020-12) on the server, and in the
browser for early feedback.

**Data parameters.** `x-splice-data.kind` is `file`, `directory`, `path` or
`uri`: offer your platform's data picker, not a free text box.
`x-splice-data.samplesheet: true` means the value is a sample sheet: offer
an upload or a sample-sheet builder. When the parameter has nf-schema's
`schema` key, it names the sample sheet's own schema file in the workflow
repository; that file is not part of the bundle.

## Execution profile choice

From `execution-profiles.json` → `profiles[]`: show `name` and
`description`; preselect the `default` profile (also
`bundle.json` → `default_execution_profile`). `type` is `test`,
`development` or `production`; most platforms offer only `production`
profiles to end users. `executor` and `container_engine` belong in
technical details. Operators, not end users, supply `site_parameters`.

## Results pages

From a job's `analysis_output.json` and the bundle's
`outputs.schema.json` → `x-output-catalog`:

| Show | Key |
| --- | --- |
| Section headings | `categories[<category>].title`, falling back to the category key; `description` as intro |
| Output name and explanation | `output_types[]`: `title`, `description` (written for scientists) |
| Grouping and filters | `scope` (job, per sample, per run), `stage`, `labels`, `format` |
| File name and size | the record's `path` (show the last segment), `size_bytes` |
| Integrity | `checksum` with `checksum_algorithm` |
| Job header | `pipeline_name`, `pipeline_version`, `job_id_short`, `execution_timestamp`, the profile's `name` for `config_profile` |

- Lay results out as job outputs, then each sample with its outputs, then
  each sample's runs. Use the sample and run identifiers your platform
  knows; a run always sits inside its sample.
- Choose viewers by `format` and `entity_type`; open untrusted HTML reports
  (MultiQC, FastQC) in a sandboxed frame or a download, never inline.
- Show only outputs the job produced. Do not show "missing" for catalogue
  types that are absent; they belong to routes this job did not take.
- On a workflow page you may preview the catalogue ("This workflow can
  produce…"), grouped by category, with each type's `scope` in words: "for
  the whole job", "per sample", "per run".

## Accessibility and wording

Use the words job, sample and run as defined in `splice-bundle-contracts`;
never call a workflow execution a run in the interface. Prefer the reviewed
`title` and `description` texts over keys in visible labels.
