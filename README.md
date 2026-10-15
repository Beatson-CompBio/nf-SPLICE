<div align="center">
  <picture>
    <source media="(prefers-color-scheme: light)" srcset="assets/splice_logo_acronym_black.png">
    <source media="(prefers-color-scheme: dark)" srcset="assets/splice_logo_acronym_white.png">
    <img src="assets/splice_logo_acronym_black.png" alt="SPLICE logo" width="180">
  </picture>

# nf-SPLICE

Prepare Nextflow pipelines for the SPLICE platform.

</div>

nf-splice reads a Nextflow pipeline repository, helps you review what it
finds, and publishes a validated **SPLICE workflow bundle**: a small set of
files in `splice/` that tells the platform what the pipeline is, which inputs
it accepts, which outputs it produces, which software it needs and how to run
it.

## Features

- **Guided review.** Work through each part of the bundle in a terminal
  wizard, with commands, or in your own editor. All three can be mixed.
- **Nothing is guessed.** Values found in your repository are suggestions
  until you confirm them; open questions are listed until resolved.
- **Safe publishing.** Only valid bundles are published, existing files are
  never replaced silently, and an interrupted publication can be recovered.
- **Standard formats.** Five versioned JSON contracts based on JSON Schema,
  plus an RO-Crate, documented key by key for tool developers.
- **Works offline.** No network, Nextflow installation or AI account is
  needed. AI assistance is optional and every suggestion needs approval.

## Install

Requires Python 3.10 to 3.14.

```bash
python -m pip install nf-splice
```

For optional AI assistance, install `'nf-splice[claude]'` instead; see
[AI assistance](docs/guide/ai-assistant.md).

## Quick start

From the root of your pipeline repository:

```bash
nf-splice init --accept-detected
nf-splice tui
```

`init` creates draft files from your repository. `tui` opens the wizard,
which takes you through every review step to a published bundle. To work
with commands instead:

```bash
nf-splice status
nf-splice plan
nf-splice build all
```

Follow the [Getting started guide](docs/guide/getting-started.md) for the
full walkthrough.

## Documentation

| | |
| --- | --- |
| [User guide](docs/USAGE.md) | Everything you need to publish and maintain a bundle |
| [Command reference](docs/reference/cli.md) | Every command and option |
| [Building on SPLICE bundles](docs/CONTRACTS.md) | File formats for platform and tool developers |
| [Schema reference](docs/schemas/README.md) | Every key of every file |
| [Glossary](docs/GLOSSARY.md) | Precise terms: bundle, job, sample, run |

## Privacy

nf-splice never publishes your Git e-mail address, never writes accounts,
credentials or private paths into a bundle, and never contacts the network
or an AI service unless you ask it to. See
[Attribution and privacy](docs/guide/provenance.md#attribution-and-privacy).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

MIT; see [`LICENSE`](LICENSE).
