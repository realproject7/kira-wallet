# Release preparation

## GitHub and npm distribution

GitHub version releases and npm registry publication are separate. The GitHub
0.1.1 release provides the reviewed `kira-wallet-0.1.1.tgz`, its SHA-256 file and
release manifest. Its tag pins the source used to create those assets. Install
that archive using the GitHub URL in README.md while npm still serves 0.1.0.
The historical 0.1.0 GitHub release points to `cfa91659a92b14467c7458d27508157f5fd615a9`
and preserves the exact already-published npm archive.

The operator explicitly requested GitHub version releases. npm publication
remains operator-only. A GitHub tag or Release does not merge the open PR or
promote the website. README screenshots are freshly captured sample portfolios;
their invented wallet addresses, balances and seeded chat are documented in
`screenshots/kira-readme-sources.json`. No private portfolio image is uploaded.

## npm publication preparation

The published npm package is 0.1.0, verified again on 2026-10-05. Registry
0.1.1 remains unavailable. The current source candidate is **0.1.2**. It includes
the prior wallet setup, scoped native AI, token artwork, compact wallet/pool
layouts and README improvements, plus fixes found through real local testing.
See [local live acceptance](KIRA_LIVE_QA.md) for the test scope and findings.

Keep GitHub v0.1.1, its tag and its released archive immutable. The 0.1.2
candidate is a new artifact with a new source identity. Preparing it does not
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
`dist/kira-wallet-0.1.2.tgz`. The ignored `dist/release.json` records its source
commit, SHA-256 and member count. It never publishes. After reviewing that
manifest, the operator's final command from the project root is:

```sh
npm publish ./dist/kira-wallet-0.1.2.tgz --access public
```

Use the operator's npm account and complete authentication or OTP personally.
After publication, verify the registry archive and perform a fresh install
before marking the new onboarding flow as available to npm users.

## Verified 0.1.0 publication

The operator published 0.1.0, verified on 2026-10-04. The registry archive has
58 members and SHA-256
`45c33d4e37bd45145c53afd05a234caa746146a47e2f729fec1087d841506858`,
matching the prepared release at `cfa9165`. Installation is
`npm install -g kira-wallet`, then `kira setup`. The public installation page
uses this registry route. Changes after that commit require a new release to
reach npm users.

## Public website

Only `site/` is deployed to Vercel's `kira-wallet` project. It contains the
restored static landing page, synthetic product illustrations, character assets
and installation instructions. The companion proposal is retired; its URLs redirect
to the landing page. No wallet input, portfolio API, chat API or analytics service
is hosted. The site permits only its own small video controller and local media. External network requests and forms stay blocked. The local viewer
remains loopback-only.

`kirawallet.app` uses Vercel nameservers and managed HTTPS. Keep `.vercel/`
metadata out of Git. Site deployments use `--cwd site`, never the private
portfolio root. Preserve the restored design when refining typography and spacing.

Native extension approval, lock and account-change behavior remain a device
acceptance check. Synthetic providers and supplied public addresses do not
establish that native extension acceptance passed. Those actions still require
the operator's device handoff. Signing and trading remain outside Kira. Human-submitted OWS creation stores an encrypted wallet in the separate local OWS vault.

See [current UI evidence](https://github.com/realproject7/kira-wallet/blob/codex/kira-release/docs/KIRA_UI_REFINEMENT.md).
