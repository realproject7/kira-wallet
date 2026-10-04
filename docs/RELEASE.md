# First release

The public source includes the workspace, Watching connection, native CLI setup
and chat. npm registry publication remains operator-only. No publish command is
run by the coding agent.

Required preparation:

```sh
npm test
python3 scripts/check-install.py
python3 scripts/check-public.py --history --ref HEAD
python3 scripts/prepare-release.py
```

`prepare-release.py` checks the public package boundary and creates
`dist/kira-wallet-0.1.0.tgz` with a SHA-256 manifest. It never publishes. From the
reviewed source checkout, the operator's final command is:

```sh
npm publish ./dist/kira-wallet-0.1.0.tgz --access public
```

Use the operator's npm account and complete any npm authentication or OTP prompt.
Version 0.1.0 was published by the operator and verified on 2026-10-04.
The downloaded registry archive has 58 members and SHA-256
`45c33d4e37bd45145c53afd05a234caa746146a47e2f729fec1087d841506858`,
matching the prepared release at `cfa9165`. Installation is
`npm install -g kira-wallet`, then `kira setup`. The public installation page
now uses the registry route. Changes after that commit require a new operator
release to reach npm users.

## Public website

Only `site/` is deployed to the Vercel `kira-wallet` project. It contains a static
introduction, synthetic product illustration, original character assets and
installation instructions. It has no wallet inputs, portfolio API, chat API,
analytics or third-party runtime scripts. The local viewer remains loopback-only.

`kirawallet.app` uses Vercel nameservers and managed HTTPS. Project domain settings
are managed in the operator's Vercel team. Keep `.vercel/` metadata out of Git.
Future site deployments must use `--cwd site`, never the private portfolio root.

Design evidence: [Lazyweb Coinbase and wallet installation references](https://www.lazyweb.com/agentic-search/32f91923-4607-4d3a-aa06-ac09828b9a66).

Native extension approval, lock and account-change behavior remains a device
acceptance check. Synthetic providers and manually supplied public addresses do
not establish that native extension approval passed. These limitations do not
grant signing, trading or custody capability.
