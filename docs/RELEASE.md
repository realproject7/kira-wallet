# Release preparation

The published npm package is 0.1.0. The next source candidate is 0.1.1, with
wallet-first setup, safe Markdown answers and the recorded exit-proceeds report.
Registry publication remains operator-only. The coding agent never publishes.

Required preparation from a clean, reviewed source checkout:

```sh
npm test
python3 scripts/check-install.py
python3 scripts/check-public.py --history --ref HEAD
python3 scripts/prepare-release.py
```

`prepare-release.py` scans the package boundary and creates
`dist/kira-wallet-0.1.1.tgz`. The ignored `dist/release.json` records its source
commit, SHA-256 and member count. It never publishes. After reviewing that
manifest, the operator's final command from the project root is:

```sh
npm publish ./dist/kira-wallet-0.1.1.tgz --access public
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
restored static landing page, synthetic product illustrations, character assets,
installation instructions and a separate companion proposal. No wallet input,
portfolio API, chat API or analytics service is hosted. The proposal's local
script updates sample scenes; the landing page blocks scripts. Both block
network requests and forms. The local viewer remains loopback-only.

`kirawallet.app` uses Vercel nameservers and managed HTTPS. Keep `.vercel/`
metadata out of Git. Site deployments use `--cwd site`, never the private
portfolio root. A new companion proposal is reviewed on its preview URL before
changing the public landing page's design.

Native extension approval, lock and account-change behavior remain a device
acceptance check. Synthetic providers and supplied public addresses do not
establish that native extension acceptance passed. Those actions still require
the operator's device handoff. No signing, trading or custody capability was added.

See [completion evidence and limits](KIRA_COMPANION_COMPLETION.md).
