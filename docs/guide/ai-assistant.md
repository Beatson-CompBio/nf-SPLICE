# AI assistance

nf-splice works completely without AI. You can optionally let an assistant
suggest reviews, such as output descriptions or parameter policies. An
assistant can only **propose** changes; nothing changes until a person
approves the proposal.

## Install

```bash
python -m pip install 'nf-splice[claude]'
```

This adds the Claude Agent SDK. Without it, no AI code is loaded at all.

## Ask for suggestions

```bash
nf-splice agent run "Suggest reviews for the output candidates" \
  --provider claude --mode suggest --allow-remote-model
```

- `--mode ask` only answers questions about the drafts.
- `--mode suggest` also creates proposals.
- `--allow-remote-model` is your consent to send repository context to the
  remote model. Without it, nothing is sent.

## Review proposals

```bash
nf-splice agent proposals
nf-splice --actor "Ada Lovelace" agent approve proposal-0123456789ab
nf-splice agent reject proposal-0123456789ab --reason "Platform decides"
```

Approving applies the proposal to the draft. The change is recorded as an
assistant suggestion with you as the approver. Approval needs an actor
label.

## In the wizard

```bash
nf-splice tui --agent claude --allow-remote-model
```

Press Ctrl+A on any step to open the assistant panel. Turning the assistant
on or off never changes your drafts or your progress.

## What an assistant cannot do

An assistant cannot run commands, read files outside the repository, access
the network, publish files, upload images or approve its own proposals. All
changes are validated by the same checks as manual edits.

## Accounts and billing

The Claude Agent SDK is billed through a Claude Platform (API) organisation.
A Claude Team or Enterprise subscription does not by itself authorise or pay
for SDK usage. Confirm your organisation's setup before use.

Developers building other assistant integrations: see the
[agent tool contract](../AGENTS.md).
