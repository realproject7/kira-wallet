# Release preparation

## GitHub and npm distribution

GitHub version releases and npm registry publication are separate. The GitHub
0.1.2 release provides the reviewed `kira-wallet-0.1.2.tgz`, its SHA-256 file and
release manifest. Its tag pins the source used to create those assets. Install
that archive from GitHub. The operator published npm 0.1.3 on 2026-10-06;
its archive and installed bytes were verified separately. GitHub v0.1.3
remains a draft. GitHub and registry status must not be inferred from each other.
Version 0.1.2 was published to GitHub on 2026-10-05 from
`f994e99acb4e2d778fb4c95479f04355c88c00b3`. Its archive SHA-256 is
`866b7f1ad543bff1ff59d3bf840eca6313eb6e206e78b8611186e5a971153f28`.
The released archive and manifest stay immutable when installation guidance changes.
The historical 0.1.0 GitHub release points to `cfa91659a92b14467c7458d27508157f5fd615a9`
and preserves the exact already-published npm archive.

The operator explicitly requested GitHub version releases. npm publication
remains operator-only. A GitHub tag or Release does not merge the open PR or
promote the website. README screenshots are freshly captured sample portfolios;
their invented wallet addresses, balances and seeded chat are documented in
`screenshots/kira-readme-sources.json`. No private portfolio image is uploaded.

## npm publication preparation

Published **0.1.3** makes `kira start` open the full local
app by default. `--read-only` preserves the viewer-only mode, `--no-open`
supports terminal-only use, and `--controls` remains compatible with existing
scripts. A running instance never changes modes silently. Local session,
origin, AI-context and wallet-operation checks remain in place. New-wallet
creation now identifies Open Wallet Standard with its official locally served
logo and explains encrypted local storage and public-account research. The
OWS integration and wallet-operation permissions are unchanged.

Published **0.1.4** makes incomplete token discovery visible
before registration and beside wallet holdings, separates disabled discovery
from missing credentials and provider failures, and offers a connection or
holdings-refresh action. Registry failures retain bounded redacted examples
and RPC error codes. Oversized multicalls split into smaller batches while
transport outages remain bounded. Existing explorer preferences are preserved
when discovery settings are saved. Connecting an indexer and refreshing
holdings are still required to recover tokens absent from an older snapshot.
RPC failures show affected networks, retry guidance and a settings action.
Failed candidate balance reads keep the saved result and valuation partial
even when general token discovery succeeded.

Published **0.1.5** opens the existing setup modal directly, adds Codex and
Claude model choices, exposes model and permission changes in Workspace settings,
and provides one Alchemy connection save. Its registry version was confirmed on
2026-10-09. Published package bytes remain immutable.

Published **0.1.6** adds a paced local RPC pool, core-chain public
alternatives, public-first custom backup, fixed-block hash checks and a small
known-token catalog. Home and wallet pages display incomplete coverage with an
Alchemy setup action. The settings guide explains account setup, private local
key import and an explicit holdings refresh. Missing or malformed discovery data
cannot become a completed empty inventory.

Version 0.1.6 is published and immutable. The showcase remains a separate deployment. See
[free RPC behavior](FREE_RPC.md) and [Alchemy setup](ALCHEMY_SETUP.md).

The operator published npm **0.1.2** on 2026-10-05. Its registry archive was
downloaded and matched the reviewed GitHub archive above, including SHA-256,
the registry SHA-1 and SHA-512 integrity value. A fresh registry installation
matched all 71 archive members and passed local viewer startup and shutdown.
The installed OWS SDK is available. The three existing local viewers were
upgraded with their wallet records, model permissions and current messages
preserved. A generic native AI connection check succeeded without portfolio
context. Runtime evidence remains private.

Version **0.1.2** includes
the prior wallet setup, scoped native AI, token artwork, compact wallet/pool
layouts and README improvements, plus fixes found through real local testing.
See [local live acceptance](KIRA_LIVE_QA.md) for the test scope and findings.

The second local question round adds native observation and historical reference
evidence to the model context and explicit wallet identities to research jobs.
The earlier unpublished 0.1.2 candidate is preserved in the ignored
`dist/preserved-0.1.2-bad8f02/` directory. Use the current `dist/release.json`
and its matching archive for publication; do not mix manifests from candidates.

Keep published GitHub tags, release assets and npm versions through 0.1.14
immutable. Do not rebuild them from later documentation commits. Future package
changes need a new version. Release preparation does not publish a GitHub
release, promote the website or publish to npm.
Registry publication remains operator-only. The coding agent never publishes.

Required preparation from a clean, validated source checkout:

```sh
npm test
python3 scripts/check-install.py
python3 scripts/check-public.py --history --ref HEAD
python3 scripts/prepare-release.py
```

`prepare-release.py` scans the package boundary and creates
`dist/kira-wallet-0.1.15.tgz`. The ignored `dist/release.json` records its source
commit, SHA-256 and member count. It never publishes. After reviewing that
manifest, the operator's final command from the project root is:

```sh
npm publish ./dist/kira-wallet-0.1.15.tgz --access public
```

Use the operator's npm account and complete authentication or OTP personally.
After publication, verify the registry archive and perform a fresh install
before marking the new onboarding flow as available to npm users.

## Published 0.1.7 behavior

Published 0.1.7 enables useful keyless research by default, expands the curated
contract inventory and separates first recorded balances from exhaustive
background research. Pending candidates, registry work and other networks stay
visible. Current wallet evidence cannot roll back when an older continuation
resumes. See [coverage and limits](FREE_RPC.md).

Codex uses the final native message rather than joined commentary. Mixed tool
protocol receives one bounded correction and is never rendered as a completed
answer. Claude retains its restricted native adapter. Tool receipts contain
names and outcomes, without raw arguments. Job checkpoints and normalized token
discovery flags have separate meanings. Imported connection references reconcile
with untouched settings fields while preserving edited drafts.

The operator published **0.1.7** on October 9, 2026. Its archive is immutable.

## Published 0.1.8 behavior

The operator published **0.1.8** on October 9, 2026. Its archive is immutable.
It queues local connection imports during research, lets settings and price
updates preempt enrichment, preserves explicit cancellation, and checkpoints
wallet balance batches and market verification at fixed blocks. A 180-second
market budget publishes immutable recorded balances with an explicit pending
market notice and Resume action. Agent inventories use bounded pages, context
errors have failed receipts, and curve comparisons require comparable state
rather than only a newer block or a different wallet-sized quote.
macOS process-group cleanup checks for live writers before dismissing an
already exited group, preserving short-operation yielding and explicit Stop.
Its historical acceptance included the repository suite, clean installation,
source and history privacy scans, independent review and the frozen archive
manifest. Current release gates follow the latest operator ruling below.
No live-extension or human passphrase acceptance is inferred from these checks.

## Verified 0.1.0 publication

The operator published 0.1.0, verified on 2026-10-04. The registry archive has
58 members and SHA-256
`45c33d4e37bd45145c53afd05a234caa746146a47e2f729fec1087d841506858`,
matching the prepared release at `cfa9165`. Installation is
`npm install -g kira-wallet`, then `kira setup`. The public installation page
now uses the published npm 0.1.2 package. Changes after a published source commit
require a new registry version to reach npm users.

## Public website

Only `site/` is deployed to Vercel's `kira-wallet` project. It contains the
landing page, native HTML conversation animation, character assets
and installation instructions. The companion proposal is retired; its URLs redirect
to the landing page. No wallet input, portfolio API, chat API or analytics service
is hosted. The site permits only its own small animation controller and local
artwork. External network requests and forms stay blocked. The local viewer
remains loopback-only.

`kirawallet.app` uses Vercel nameservers and managed HTTPS. Keep `.vercel/`
metadata out of Git. Site deployments use `--cwd site`, never the private
portfolio root. Preserve the restored design when refining typography and spacing.

Native extension approval, lock and account-change behavior remain a device
acceptance check. Synthetic providers and supplied public addresses do not
establish that native extension acceptance passed. Those actions still require
the operator's device handoff. Signing and trading remain outside Kira. Human-submitted OWS creation stores an encrypted wallet in the separate local OWS vault.

See [current UI evidence](https://github.com/realproject7/kira-wallet/blob/codex/kira-release/docs/KIRA_UI_REFINEMENT.md).

## Proposed 0.1.9 behavior

Version 0.1.9 permits a saved report's price update during detailed research,
with duplicate queued/running price feedback and existing automatic continuation.
Network empty states distinguish pending coverage, incomplete checks, completed
empty records and actual filter exclusion. Native facts include full-inventory
category valuation and explicit unknown activity causes. Public RPC configuration
updates verified Shib/Cyber routes and removes a failed Base reserve. Sanitized
route outcomes distinguish public-only acceptance from custom fallback. Bounded
route telemetry retains aggregate outcomes when detailed records reach their cap.
Compact agent facts retain historical quote presence even when outputs are deferred.
Snapshot comparisons provide exact full-comparison and per-chain counts before
pagination so native agents do not need to tally large position pages manually.

Publication remains an operator action. Post-publication acceptance uses two
clean installations of the same verified registry bytes: public/free only first,
then a clean reinstall with authorized Alchemy discovery and public-first backup.
Each lane begins without previous holdings, identity caches or RPC health.
Compare exact chain/contract identities, observations, coverage, route classes,
failures and runtime. Separate changed observation times from discovery effects.
The procedure does not treat partial free discovery as exhaustive or stale spot
sums as wealth floors. Private wallets, financial screenshots and local tickets
stay outside the package and public review.


## Published 0.1.10

Published 0.1.10 adds saved keyless ERC20 transfer discovery on six core chains,
canonical RPC balance verification and explicit unfinished-history feedback.
It fixes public-first cold qualification budgeting, exposes sanitized saved
provider routes and authoritative coverage counts to native tools, and adds
bounded read plans with individual completion receipts. Failed account probes
are distinct from unsupported versions. Reviewed lifecycle notices and targeted
suspicious-zero checks preserve unknown and historical observations.

Publication is operator-only. Preserve the published 0.1.10 app and archive.
The next release uses its own clean source commit, exact installation and
manifest. Registry and GitHub publication are separate operations.

## Published 0.1.11

Registry publication was verified on October 16, 2026. The published archive
matches the prepared source at `61205e03cf369d46109fb010f4544326838c558b`,
including SHA-256 `f18c3b00c97231951bddcf43a4406e741d5124c2ed0cb3564032cb08667e8464`,
registry SHA-1 and SHA-512 integrity. A clean registry installation matched all
87 package members and passed empty local viewer startup and shutdown.

This branch adds durable, segmented discovery frontiers, block-range splitting
past provider page limits, source-specific cursor and quota recovery, and a
union of admitted free candidate sources. Pinned registry and balance batches
receive bounded scheduling turns. Resumes accept added market candidates while
rejecting changed quantities or blocks, preserve saved positive observations
through failed registry rereads, and continue normal slice boundaries with
bounded no-progress detection. The non-default key import guide selects the
saved key reference explicitly. General NFT IDs and DeFi positions are outside
this release scope.

The operator revised the target to USD 1 amount-specific liquidation candidates,
including funded Mint Club burns, and removed 48-hour stability from this task.
Fresh research uses wallet history and prior positive identities rather than
blanket registry balances. It retains full inventory as an explicit mode and
records unsupported discovery and liquidation paths as unknown. Same-block
quotes compose supported DEX and nested funded-burn outputs into terminal assets;
spot reserve prices alone do not establish cash proceeds.

Basic scans save usable balances first. Users explicitly select a deep scan,
which finishes after representative asset checks with quoted or unknown
outcomes. Cumulative progress survives pause, restart and bounded engine slices.
Available prices, representative estimates and unresolved checks remain separate.
Missing rereads retain earlier dated evidence without marking it fresh.

Quote fallback preserves all sampled input sizes and their order. A successful
full-input quote returns immediately; smaller V3 and Aerodrome inputs use bounded
read-only batches with the existing provider pacing and payload-limit splitting.
Upgrades recover previously positive token identities from that wallet's own
saved publications. They never reuse the old quantities as new balances or
establish exhaustive new-wallet discovery.

The behavior acceptance requires the full suite, a clean exact-package installation,
tracked and history privacy scans, a default public-only basic-scan check and
focused same-block quote equivalence. Existing discovery configuration and
auxiliary-provider regressions remain in the suite. No credential changes or
paid-provider acceptance are part of this release preparation. Earlier actual
natural completion and protected desktop/mobile pause and resume evidence are
retained; rerun affected behavior on the final package. Review not selected under
the operator's current ruling. No additional independent review is implied.

The operator delegated resolution of the legacy author-metadata finding on
October 16, 2026. The privacy checker accepts only the existing author identity
of immutable merge commit `2ed52a24bc38ac4101aceff781cb7ff58941be57` and reports
the exception separately. New identities, commit contents and secrets retain
their checks. No history rewrite or broad email exemption is required.

Use only the archive matching the final `dist/release.json` source commit,
SHA-256 and installed member hashes. A registry dry run does not publish or
establish registry credentials. Registry publication remains operator-only.

## Published 0.1.12

This release consolidates the completed PR20 through PR29 stack into the default
release branch. It includes the native HTML showcase, simpler local startup and
OWS attribution, setup and connection improvements, free-source discovery and
RPC recovery, truthful native research evidence, and optional deep scans with
saved progress, pause and resume. Published 0.1.11 already contains this product
code. Version 0.1.12 changes package metadata and release documentation so that
the next npm archive is prepared from the merged source.

The operator selected normal authenticated GitHub CLI merges for this
consolidation. The strict history check can flag the same already-public author
metadata. Retain its raw output and separately record each accepted merge SHA,
its expected parents and tree, and the matching existing author. These
acceptances cover only the authorized PR merges. Content and secret findings
still block preparation. Checker defaults and account settings stay unchanged.

Verify the landed source tree and preserve the original PR commits and published
archives. Run the full suite, clean installation and source/history privacy
checks. Confirm every archive member against that source and the installed
package, then run npm publish in dry-run mode. Reuse the existing cold basic,
same-block quote, price-retention and desktop/mobile deep-scan evidence only
where the relevant source bytes match. No new exhaustive wallet benchmark is
required for version and documentation changes. Review not selected.

Prepare the final archive only after the release source has landed. Its exact
commit and hashes belong in `dist/release.json`. Actual npm publication remains
operator-only. Personal installations and paused automation are separate from
release preparation.

## Published 0.1.13

Version 0.1.13 requires a locally available Alchemy key reference before wallet
research. `kira connect alchemy` accepts the key privately in an interactive
terminal. Onboarding has two steps, connecting Alchemy and adding a wallet,
with an included guide using a public blank Alchemy example. AI connection is
optional and its dialog opens only after an explicit connection action. Chat
research status is a collapsible single line.

Default holdings research attempts all 18 configured mainnets and six testnets.
It checks every discovered, prior or known candidate and the available Mint Club
registry. There is no 128-token candidate limit; 128 remains an RPC payload batch
size. Failed network access and unavailable indexers remain explicit unknowns.
This is not a guarantee of complete discovery on arbitrary EVM networks. Testnet
values never enter portfolio USD totals. Existing limited snapshots need a new
holdings refresh to gain the restored inventory coverage.

Default holdings, prices and artwork do not require a deep scan. Optional
`Analyze sell routes` reuses the same wallet's immutable saved balances, blocks
and observation times. It researches liquidation paths without rediscovering
tokens or refreshing balances. Bounded engine slices, provider pacing, pause,
resume and no-progress protection remain. It has no overall time limit.

Prices from DEX pools below USD 1,000 liquidity, or explicitly one-sided pools,
cannot contribute to portfolio totals. Rejected reserve prices cannot reappear
through cached indexer or dependent curve estimates. Balances remain visible
with unknown USD values. Valid spot estimates still do not establish executable
sale proceeds. Price-only updates preserve immutable holdings and prior market
records, reuse fresh batched curve facts and publish explicit partial results
when a bounded lookup cannot finish.

Artwork uses chain and contract identity with Mint Club and Alchemy sources,
including allowed Alchemy and CoinMarketCap hosts. The Mint Club image fallback
retries once before initials. No original image is promised for an unknown token.
Failed Mint Club detail batches receive one smaller retry, and remaining errors
keep coverage partial rather than silently becoming completed records.

The source in PR31 passed the full suite, clean installation and actual-wallet
holdings, price, artwork and sell-only pause/resume checks. Release preparation
reruns the required suite and clean installation, scans tracked source and
history, and compares every final archive member with the landed source and
its isolated installation. Product acceptance may be reused only for identical
product bytes. Preserve raw history findings and apply only the exact normal
CLI merge-metadata acceptance described above. Review not selected.

Prepare the final archive from the landed version PR. Freeze its source commit,
SHA-256 and member hashes, then dry-run that exact archive. npm publication is
operator-only. Do not upgrade the personal app, resume paused automation,
publish a GitHub release or deploy the website during preparation.

The operator published 0.1.13 on October 17, 2026. Its registry archive matched
the frozen manifest and all 90 installed package members. The published archive
remains immutable.

## Published 0.1.14

Version 0.1.14 includes merged PR33. Private Alchemy RPC requests use a shared
250 ms lane across hosts, with cooldown after HTTP or JSON-RPC rate limits.
Public RPC pacing, canonical-block checks, retries and fallback order remain.
This removes the inherited two-second public-provider delay from private
Alchemy reads without promising a fixed completion time.

Artwork refreshes reuse safe chain-and-contract metadata already returned by
DEX discovery. A separate provider failure preserves successful artwork, and
canonical Base and Unichain USDC receive verified fallback images. Unknown
tokens can still display initials when no supported image is available.

Reserve pricing focuses on funded curves with missing USD quotes. Bounded
lookups retain completed price paths and leave time to publish their partial
graph before the parent deadline. Unfinished paths remain unknown. Existing
thin-pool exclusions and portfolio total rules remain. Metadata passes preserve
saved token quantities, blocks and observation times.

PR33 acceptance compared 47 important token balances and eight native balances
with explorer pages, including direct token-holder pages. A cold holdings run
with the revised RPC pacing saved first evidence in 19.9 seconds and completed
in 475.7 seconds. A separate live pass using the final metadata changes completed
in 45.6 seconds over that wallet's own captured holdings, saved a partial reserve
graph and preserved every quantity. These are individual observations under
differing provider conditions. Exhaustive spam-token pricing or artwork coverage
is outside this acceptance scope.

Release preparation requires the full suite, a clean installation, tracked and
history privacy scans, and comparison of every archive member with the landed
source and isolated installation. Preserve strict history findings and assess
only the exact authorized normal CLI merge metadata under the ruling above.
Review not selected. The version PR changes only package metadata and release
documentation; existing product acceptance applies to identical product bytes.

Prepare and freeze the final archive from the landed version PR, then dry-run
that exact archive. npm publication remains operator-only. Keep the personal
0.1.13 installation, published archives and paused automation unchanged. This
preparation does not publish a GitHub release or deploy the website.

The operator published 0.1.14 on October 18, 2026. Its registry archive matched
the frozen manifest, including SHA-256
`c9802e76f05ae7e560fd29051beea3855e7006e99670f131de2a6322f4b1e8b8`
and all 90 installed members. Actual acceptance checked important explorer
balances, prices, artwork and sell-only pause/resume. A subsequent pass completed
the sell analysis naturally and exposed the two issues addressed below.

## Release candidate: 0.1.15

Scoped AI research declares its complete read plan before answering. A plan
can contain up to 32 read-only requests, so a nine-chain question is not cut
off by the former eight-read batch bound. Host receipts cover declared plans
in natural-language conversations as well as literal tool requests. Missing
reads receive one bounded continuation attempt and unresolved requests stay
partial. An empty plan supports greetings and action-only requests. Planning
cannot enqueue research; scope, cancellation, context and time limits remain.
Token-specific reads cover all approved wallets without unrelated inventory
pagination. Optional USD thresholds and distinct matched-position counts are
computed from saved values by the host; unknown and testnet values stay separate.
This checks the declared plan, not every possible semantic interpretation of
a question. Unknown values and recorded valuation timestamps remain explicit.

Completed sell summaries use final saved per-token classifications rather than
intermediate progress counters. Older completed jobs also show corrected totals
without rewriting snapshots or original events. Paused/running progress remains
resumable, and testnet values stay outside USD classifications. This changes
neither balances nor quote execution, gas or best-route guarantees.

Required gates are the full repository suite, clean installation, actual native
AI nine-source and research-action checks, completed-summary browser checks,
tracked/history privacy scans and an exact final archive installation. Preserve
raw strict history findings and assess only the authorized normal CLI merge
metadata under the ruling above. Review not selected.

Prepare and freeze the final archive only from the landed release source, then
dry-run that exact archive. npm publication remains operator-only. Preserve the
personal 0.1.14 installation, credentials, paused history and published archives.
Use a separate private workspace for candidate acceptance. No GitHub release,
website deployment or personal app upgrade is part of this preparation.
