# Kira release status

Updated: 2026-11-13. The operator published Kira 1.5.0. This branch prepares
1.11.2 in PR #62: balance-aware sell-analysis reuse, immediate name edits,
bounded worker admission, wallet search and folders, and a consistent local
workspace design, including corrected main-pool sell quotes on Base bounded sell-route retries, PancakeSwap BNB quotes, upgraded Aero pools, recoverable bulk wallet removal, visible token markets, and saved protocol positions with exclusive platform allocation. Previous snapshots and frozen archives remain preserved.
Earlier plans and reports preserve historical evidence, not active release gates.

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

## Current release and candidate

Version 1.1.0 delivers installed tool schemas, revised agent guidance and optional
h402 setup. The operator published it on October 29. PR #59 merged, and a fresh
registry archive installation matched all 95 members. See the [published notes](RELEASE.md#published-110).

The 1.2.0 source adds portfolio-wide holdings refresh and sell analysis through
the existing per-wallet queue, indicative sums with quote coverage, and recorded
holders sorted largest first on token pages. Published 1.1.0 stays immutable.
Candidate registry publication remains an operator action. Review not selected.

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
