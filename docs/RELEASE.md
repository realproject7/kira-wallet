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

Keep GitHub v0.1.1, its tag and its released archive immutable. Versions 0.1.2, 0.1.3, 0.1.4, 0.1.5 and 0.1.6 are also published and immutable. Do not rebuild them from later documentation
commits. Future package changes need a new version. Release preparation does not
publish a GitHub release, merge PR 19, promote the website or publish to npm.
Registry publication remains operator-only. The coding agent never publishes.

Required preparation from a clean, reviewed source checkout:

```sh
npm test
python3 scripts/check-install.py
python3 scripts/check-public.py --history --ref HEAD
python3 scripts/prepare-release.py
```

`prepare-release.py` scans the package boundary and creates
`dist/kira-wallet-0.1.7.tgz`. The ignored `dist/release.json` records its source
commit, SHA-256 and member count. It never publishes. After reviewing that
manifest, the operator's final command from the project root is:

```sh
npm publish ./dist/kira-wallet-0.1.7.tgz --access public
```

Use the operator's npm account and complete authentication or OTP personally.
After publication, verify the registry archive and perform a fresh install
before marking the new onboarding flow as available to npm users.

## Proposed 0.1.7 behavior

The candidate enables useful keyless research by default, expands the curated
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

The next archive is **0.1.7**, unpublished until the operator runs the command.
Release readiness requires the repository suite, clean installation, source and
history privacy scans, independent review and the frozen archive manifest.
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
