# Kira release status

Updated: 2026-10-04. The operator authorized source completion, merges, native CLI
onboarding, a private read-only wallet acceptance run and Vercel domain setup.
Registry publication remains operator-only. This document records state, not new
authority.

| Outcome | State | Remaining action |
| --- | --- | --- |
| Workspace redesign, PR #2 | Independently reviewed, fixed and merged. | None for source. |
| Watching connection, PR #3 | Independently reviewed, fixed and merged. | Native extension approval/locking/account-change acceptance remains a device check. |
| Native model onboarding and chat | Codex and Claude Code adapters implemented. Both generic live response checks passed with native subscription accounts. Permissions and Kira-local retention are explicit. | Two independent reviews and package verification passed. |
| Private live wallet research | Private read-only acceptance passed with recorded coverage gaps. Same-address aliases and duplicate-request reuse were verified. | No private identifiers or portfolio evidence published. |
| Public installation site | Static introduction deployed on Vercel. HTTPS apex connected through the operator's browser. www permanently redirects to apex. | Deploy the final reviewed installation links. |
| npm release | Public 0.1.0 package and preparation script are ready. No registry publication performed. | Final operator publication of the verified tarball. |

The public release baseline is `origin/codex/kira-release`. It preserves the exact
independently reviewed workspace and Watching source. GitHub's earlier server
merge metadata used an account default author address. A clean branch/default
recovery preserves source content without a force push. Historical PR merge
records may remain; this is not a claim of erasure. Future GitHub merges explicitly
set the public noreply author, and release checks validate author and committer.

The public website contains no portfolio or model API. Personal research stays in
a loopback viewer. RPC/indexer reads use configured providers. Chat text and the
selected context go through the native CLI to its model service. No wallet
context is the initial default. Model permissions do not authorize signing,
trading, publication or automatic research.

See [the conversation contract](ONBOARDING_CHAT_CONTRACT.md),
[CLI setup](CLI.md), and [release preparation](RELEASE.md).
