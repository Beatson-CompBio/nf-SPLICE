# Working copy and Git

nf-splice never changes your original pipeline. It works on an *integration
copy*: a separate folder with its own local Git branch. You need Git, but no
GitHub or GitLab account.

## Create the integration copy

```bash
nf-splice source prepare ../my-pipeline
nf-splice source prepare https://github.com/example/my-pipeline.git --ref v1.2.0
nf-splice source prepare ./my-pipeline --into ~/work/my-pipeline-splice
```

| Your pipeline is | nf-splice |
| --- | --- |
| A local Git repository | Clones it and creates the branch `nf-splice/integration-<name>`. Uncommitted changes stay behind unless you add `--include-uncommitted`. |
| A plain folder | Copies it (without symbolic links, `work/`, `.nextflow/` or logs), creates a local Git repository and commits the import with your Git identity. |
| A Git URL | Clones it with your usual Git sign-in. Being able to read a repository does not mean you can push to it. |

The copy is created next to the original as `<name>-splice-integration`
unless you choose `--into`. An existing, non-empty folder is never used.
`nf-splice source info` shows where a copy came from.

In a terminal, `source prepare` then opens the workspace on the copy, at its
Welcome screen; `--no-open` (or `--json`, or output that is not a terminal)
only prints where the copy is. nf-splice remembers the copies you make, in
your own configuration folder: run `nf-splice` in a copy to resume it, in
the original pipeline to be offered the copy you made earlier, or anywhere
else to choose one. The Welcome screen of an original pipeline offers
**Prepare a safe working copy** as well.

If Git has no identity yet, set one, or pass it for this copy only:

```bash
nf-splice source prepare ./my-pipeline --git-name "Ada Lovelace" --git-email ada@example.org
```

## Working in place

nf-splice creates drafts only in a working copy. To work on the original
folder itself, which is riskier, authorise it explicitly, in any one of
these ways:

```bash
nf-splice source prepare ./my-pipeline --in-place --yes
nf-splice init --in-place
```

or choose **Work in this folder instead…** on the workspace's Welcome
screen. The consent is recorded in the folder's private
`.splice-local/integration.json`. Without it, `nf-splice init`, the
workspace and `nf-splice session start` refuse to create drafts in a
pipeline folder and say how to make a copy. A folder that already has
drafts (made in place by an earlier version) keeps working as before.

## What lives where

| Folder | Contents | In Git? |
| --- | --- | --- |
| `splice/` | The published bundle | Yes, when you commit it |
| `.splice-local/` | Your drafts, review history, AI sessions, checkpoints, exports | Never: nf-splice adds `/.splice-local/` to `.gitignore` |

Git records the finished bundle. Work in progress is protected by session
checkpoints in `.splice-local/`, not by Git, so keep the copy until you are
done.

```bash
nf-splice workspace check
```

reports anything unsafe: a tracked `.splice-local/`, a folder named
`SPLICE` that collides with `splice/` on macOS, or drafts in an older
layout (`nf-splice migrate --check` moves them).

## Review and commit

```bash
nf-splice git status
nf-splice git diff
nf-splice git commit --message "Publish the SPLICE bundle for v1.2.0"
```

`git commit` commits only `splice/` and `.gitignore`, and only when the
published bundle validates. It uses your Git identity. Add other pipeline
files explicitly with `--include PATH`. `.splice-local/` is never committed.

## Share the branch

Pushing is always your decision:

```bash
nf-splice git push --remote origin --yes
```

nf-splice checks with a dry run that the push is allowed before pushing.
It never pushes on its own, creates remote branches, forks or pull
requests; open a pull request with your Git host as usual.
