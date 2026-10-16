# AI providers and accounts

nf-splice's agentic AI works with four real providers. This page explains
how each one signs in, where the model runs, who pays, and what to ask your
organisation's administrator for. You need a provider only for Ask AI and for
AI-assisted or autonomous sessions; manual work never needs one.

> **Verified on 15 October 2026** against the providers' own documentation,
> linked in each section. Plans, credit amounts and eligibility change; check
> the linked pages before you rely on them. nf-splice contains no prices,
> credit amounts or reset times.

| Provider | Sign-in | Where the model runs | Who pays |
| --- | --- | --- | --- |
| `claude` | Claude Platform (Console) API key | Anthropic (remote) | The Console organisation: Team or Max plan API credits, or paid credits |
| `openai` | Sign in with ChatGPT (Plus or Pro), or an API key you choose explicitly | OpenAI (remote) | Your ChatGPT plan's usage, or metered API billing in API-key mode |
| `codex` | The same as `openai` | OpenAI (remote) | The same as `openai` |
| `opencode` | Whatever you configured in OpenCode | Local (a model server on your computer) or remote, per model | The model provider you configured; nothing for local models |
| `scripted` | None | No model | Nothing (offline tests and demonstrations) |

## Choosing and checking a provider

```bash
nf-splice provider list
nf-splice provider doctor
nf-splice provider select openai --model MODEL_ID
```

`provider doctor` shows, for each provider, whether its parts are installed,
whether you are signed in, which account and model are selected, where the
model runs and who pays, and what to do next. Add `--online` to have it
contact the provider and check the credential. Nothing is selected for you:
a session uses `--provider`, or the provider you saved with
`nf-splice provider select`, and never switches provider, model or billing
route by itself. `MODEL_ID` in the examples stands for a model listed by
`nf-splice provider models PROVIDER`; `ollama/qwen3:8b` is an example of
OpenCode's `provider/model` naming.

Before a paid or remote session, run a one-tool connection test. It sends no
repository content:

```bash
nf-splice provider test openai --allow-remote-model
```

Every command that sends repository context to a remote model needs
`--allow-remote-model`. A local OpenCode model does not.

## Claude

Install the extra and use a Claude Platform API key:

```bash
python -m pip install "nf-splice[claude] @ git+https://github.com/Beatson-CompBio/nf-SPLICE.git"
nf-splice provider auth claude --api-key
```

The key is typed at a hidden prompt and stored owner-only in your user
configuration folder (see [Where credentials are kept](#where-credentials-are-kept)).
You can instead set `ANTHROPIC_API_KEY`.

**Team and Max plans.** A Claude Team or Max subscription does not sign in
the Claude Agent SDK by itself, and nf-splice does not use Claude.ai login:
Anthropic does not allow third-party products to offer Claude.ai login or
subscription rate limits without its approval. Eligible plans can instead
claim monthly **Claude Platform API credits** and link them to a Claude
Console organisation. API usage then draws on those credits; unused credits
expire. This is separate from your Claude Code subscription limits.

What to ask your administrator (a Team Primary Owner or Owner who also has
Owner, Admin or Billing access in the Console organisation):

1. In the Team organisation's billing settings, link the correct Console
   organisation and accept the terms. The link is not casually changeable.
2. Check the promotional credit balance in the Console.
3. Create an API key in a workspace you may use, scoped as your organisation
   requires, and give it to you securely.

If `provider doctor --online` reports `usage_exhausted`, the organisation's
credit balance is used up: ask the billing administrator. If it reports
`permission_denied`, the key's workspace does not allow the request.

References: [API credits for subscribers](https://platform.claude.com/docs/en/about-claude/api-credits-for-subscribers),
[Agent SDK overview](https://code.claude.com/docs/en/agent-sdk/overview),
[authentication](https://platform.claude.com/docs/en/manage-claude/authentication).

## OpenAI with your ChatGPT plan

OpenAI's **Sign in with ChatGPT for open-source applications** (published
28 September 2026) lets eligible ChatGPT Plus and Pro users use their plan
for nf-splice without an API key. Eligibility, workspace rules and limits are
decided by OpenAI per account.

```bash
python -m pip install "nf-splice[openai] @ git+https://github.com/Beatson-CompBio/nf-SPLICE.git"
nf-splice provider auth openai --sign-in
nf-splice provider models openai
nf-splice provider select openai --model MODEL_ID
```

Your browser opens OpenAI's sign-in page. Allow nf-splice to use your plan;
if you decline, nf-splice cannot use your plan and says so instead of
charging anything. A browserless computer cannot complete this step; sign in
on a computer with a browser, or use another provider.

- Several accounts can be signed in; list them with
  `nf-splice provider auth openai` and choose one with
  `nf-splice provider auth openai --account CLIENT_ID`.
- `nf-splice provider auth openai --sign-out` revokes the sign-in.
- When your plan's usage limit is reached, the session pauses with
  `usage_exhausted`. See ChatGPT **Settings > Usage** for when it resets
  (nf-splice does not guess), then resume, or continue with another provider
  or manually.

**Metered API billing instead.** If you want to use an OpenAI Platform API
key, choose it explicitly; it is never a silent fallback:

```bash
nf-splice provider auth openai --api-key
nf-splice provider auth openai --use api-key --yes
```

References: [Sign in with ChatGPT](https://developers.openai.com/cookbook/articles/sign-in-with-chatgpt),
[open-source apps](https://developers.openai.com/siwc/token-sharing-open-source),
[models and inference](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference),
[errors and recovery](https://developers.openai.com/siwc/token-sharing-open-source/errors-and-recovery).

## Codex

The `codex` provider runs OpenAI's Codex agent through its app-server, locked
to nf-splice's tools: its shell, file editing, web search, plugins, skills
and subagents are switched off and tested to stay off. It uses the `openai`
provider's sign-in or chosen API key; Codex's own login is not used.

Install Codex yourself (nf-splice never installs it). Only Codex 0.162.x,
whose restrictions nf-splice has verified, is enabled:

```bash
npm install -g @openai/codex@0.162
nf-splice provider doctor codex
nf-splice provider select codex --model MODEL_ID
```

Set `NF_SPLICE_CODEX` to use a Codex binary that is not on your `PATH`.

Reference: [Codex app-server for open-source apps](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server).

## OpenCode, cloud and local models

OpenCode is an intermediary: you configure model providers and their
credentials in OpenCode, including local servers such as Ollama, LM Studio,
llama.cpp, MLX or SGLang. nf-splice starts a private OpenCode server on your
computer, with every native OpenCode tool denied, and uses only the model you
select. Only OpenCode 2.0.x is supported.

```bash
nf-splice provider models opencode
nf-splice provider select opencode --model ollama/qwen3:8b
nf-splice --actor "Ada Lovelace" session start --mode assisted --provider opencode
```

- A model whose endpoint is on your computer is **local**: no remote-model
  consent is needed and no cost is recorded. Any other model is **remote**
  and needs `--allow-remote-model`.
- A model that cannot call tools cannot run sessions; nf-splice refuses it
  rather than guessing.
- Provider keys kept in environment variables are passed to OpenCode only
  when you name them, for example `NF_SPLICE_OPENCODE_ENV=GROQ_API_KEY`.
  Keys stored by OpenCode itself are used as usual.
- To use an OpenCode server you already run, set `NF_SPLICE_OPENCODE_URL`
  (a loopback address only) and `NF_SPLICE_OPENCODE_PASSWORD`.

References: [providers](https://opencode.ai/docs/providers/),
[models](https://opencode.ai/docs/models/),
[permissions](https://dev.opencode.ai/v2/docs/permissions/).

## When a provider stops

A session is saved before every provider request. If a provider stops (a
rate limit, an exhausted plan or credit, an expired sign-in, a lost
connection), nf-splice retries only short, transient faults, at most twice,
and otherwise pauses the session with the reason. Nothing is lost. Continue
when the limit resets, with another provider, or manually:

```bash
nf-splice session status
nf-splice --actor "Ada Lovelace" session resume
nf-splice --actor "Ada Lovelace" session resume --provider opencode --model ollama/qwen3:8b
nf-splice --actor "Ada Lovelace" session resume --mode manual
```

The session report states which provider, model and billing route was used,
the token usage, and the cost only when the provider reported one
(otherwise `not_reported`).

## Where credentials are kept

API keys and sign-in tokens are stored in your user configuration folder,
never in a pipeline repository, `.splice-local/`, a commit or an archive:
`$NF_SPLICE_CONFIG_DIR`, otherwise `$XDG_CONFIG_HOME/nf-splice`, otherwise
`~/.config/nf-splice`. The folder is readable only by you. nf-splice never
prints a credential; `provider doctor` shows only whether one exists and a
non-secret account label. Remove a saved key with
`nf-splice provider auth claude --forget-key`.
