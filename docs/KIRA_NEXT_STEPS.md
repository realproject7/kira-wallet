# Kira release status

Updated: 2026-10-29. Kira 1.0.2 is published and its scoped implementation and
installed-package acceptance are complete. Version 1.1.0 is a prepared candidate
in [PR #59](https://github.com/realproject7/kira-wallet/pull/59), not an npm release.
It adds installed tool schemas, revised agent guidance and optional h402 setup
without an embedded analysis engine. This page records current status;
earlier plans and reports preserve historical evidence, not active release gates.

## Completed release scope

| Outcome | State and evidence |
| --- | --- |
| Local research and wallet management | Holdings and price refresh, saved analyses and comparisons, durable jobs, progress, pause/resume and human browser controls are delivered. Reads do not start research. |
| External agent access | CLI and optional MCP share the local application service. The agent host owns conversations, models and approvals. Embedded model runtimes were removed in 0.2.1. |
| Watching and OWS wallets | Public-address connections and human-submitted OWS creation are delivered. New OWS wallets wait for an explicit holdings refresh. Kira has no signing or trading tools. |
| Continuation performance | Published 1.0.1 fixes repeated completed-review work and excessive local checkpoint writes. Real continuation and restart acceptance passed. |
| 1.0.2 corrections | Home uses mainnet asset scope, saved analyses favor final records, and price refresh exposes actual phases and completed request counts. |
| npm publication and installation | The operator published 1.0.2 on October 27. Registry hashes and all 93 installed members match the frozen archive. Clean reinstall, desktop/mobile, history preservation, restart and CLI/MCP checks passed. |
| Repository integration | [PR #56](https://github.com/realproject7/kira-wallet/pull/56) merged into `codex/kira-release` on October 28. The landed tree matches the tested 1.0.2 source. |
| Public website | [kirawallet.app](https://kirawallet.app) presents the external-agent workflow. Its setup guide follows the maintained release branch. The site hosts no wallet or model API. |

The [release notes](RELEASE.md#published-102) retain source identity, checksums
and acceptance details. Published archives remain immutable. Later documentation
or website changes do not rebuild 1.0.2 or require another npm publication.
Review not selected for the 1.0.2 implementation and this release closeout.

## 1.1.0 candidate

The implementation and release preparation share PR #59. `kira describe --json`
exposes the installed schemas; the skill separates recorded wallet facts from
external analysis. Onboarding, Workspace settings and CLI support optional h402
installation guidance, a durable preference and local version checks. No h402
dependency, payment configuration or paid request is added to Kira.

The prepared archive and source identity are in `dist/release-1.1.0.json`.
PR merge and operator publication remain outstanding. Installing npm `latest`
still selects 1.0.2 until publication. See the [candidate release notes](RELEASE.md#candidate-110)
for verification and the operator publication command. Review not selected.

## Remaining verification and optional work

| Item | Current boundary |
| --- | --- |
| Gemini and Grok host acceptance | No pass is recorded. The last attempts on October 25 were blocked by account eligibility or signed-out access. Retry after the operator makes a usable host available. Codex and Claude acceptance does not establish other-host compatibility. |
| Additional operating systems | macOS is verified. Research and background processes require POSIX. Linux and Windows acceptance is not established. |
| Full-route net recovery | [Issue #11](https://github.com/realproject7/kira-wallet/issues/11) remains optional research. Supported amount-specific quotes already exist; full settlement conversion, gas, nested exits and shared-liquidity portfolio aggregation are not a completed net-recovery capability. |
| Imported wallets and execution | Deferred to post-MVP under the [wallet capability decision](WALLET_CAPABILITIES.md#post-mvp-decision-imported-wallets-and-execution-2026-10-19). Automatic signing, transfers and trading are not implemented. |
| External pilot and a separate product video | Proposed in earlier plans; completed pilot results and an accepted product-video deliverable are not recorded. The website's fictional HTML demonstration is already delivered. |

These items are not unfinished 1.0.2 fixes. Schedule a concrete follow-up before
expanding the product or claiming additional compatibility. Provider gaps remain
explicit unknowns; a terminal partial research result is not an active job or a
reason to retry automatically.

## Current setup and architecture

Use the [README](../README.md), [CLI guide](CLI.md),
[agent tool contract](AGENT_TOOLS.md) and [Alchemy setup](ALCHEMY_SETUP.md).
Alchemy is required for new holdings and price research. Saved records remain
readable without provider access. The local app stays on loopback; wallet
records and provider references remain in the user's private workspace.

The [original product proposal](KIRA_PRODUCT_SPEC.md),
[implementation plan](KIRA_IMPLEMENTATION_PLAN.md) and
[overnight plan](KIRA_OVERNIGHT_PLAN.md) are historical documents. Their embedded
chat milestones, early publication gates and old domain do not describe the
current product or authorize new work.
