<p align="center">
  <img src="https://raw.githubusercontent.com/realproject7/kira-wallet/v0.1.2/viewer/static/kira-explain.png" width="140" alt="Kira, your wallet research partner">
</p>

<h1 align="center">Kira Wallet</h1>
<p align="center"><strong>Manage your wallets. With your own AI.</strong></p>
<p align="center">
  <a href="https://kirawallet.app">Website</a> ·
  <a href="https://github.com/realproject7/kira-wallet/releases">Releases</a> ·
  <a href="docs/CLI.md">CLI guide</a>
</p>

Kira collects and explains public wallet holdings in a local workspace. Use its
web app to manage wallets, inspect token markets and follow research. Your
existing AI agent can use the same records and actions through the Kira CLI or
optional MCP connection, then open the web app beside your conversation.

**This branch prepares 0.2.1.** Kira now supplies wallet tools and a full-window
management app. Your agent host manages its own conversations, models, files and
approvals. Kira does not launch a model CLI or require a model login.

## Get started

**Requires Node.js 22+ and Python 3.11+. macOS is verified.** Research and
background processes require POSIX. Install Kira and open the local app:

```sh
npm install -g kira-wallet
kira setup
```

When installing a prepared release before publication, use its verified archive
instead of assuming the npm default already contains this branch.

1. **Connect Alchemy.** Follow the [setup guide](docs/ALCHEMY_SETUP.md). Run
   `kira connect alchemy` in your terminal and enter the app key at the hidden
   prompt. The key stays in a private local file. Existing environment or file
   references can also be configured through the CLI.
2. **Add a watching wallet.** Enter a public EVM address and an exact name.
   Kira checks configured networks and discovered candidates, including the
   reachable Mint Club registry. Balances appear as they are checked; prices
   and artwork follow. Follow, pause or resume the job in Activity.
3. **Use your agent session.** Ask a capable local agent to read `kira skill`,
   check `kira info --json`, and use Kira's CLI. It can open the URL returned by
   `kira start --no-open` using its own browser or app panel. A host that only
   supports MCP can connect to `kira tools`.

Human controls remain available without an agent. `kira start` opens the app;
`kira stop` closes its server. `kira start --read-only` disables browser actions.
Stopping the app or ending an agent session does not cancel accepted research.

## Work from any agent session

The CLI reads saved data even when the web server is stopped. The default
workspace is `~/.local/share/kira-wallet`, independent of the current folder or
agent session. Use `--data-dir` or `KIRA_DATA_DIR` to choose another workspace.

```sh
kira info --json
kira call holdings_query --arguments '{"mode":"rank","limit":5}' --json
kira refresh 'Daily wallet' --json --idempotency-key 'daily-refresh-001'
kira jobs wait JOB_ID --timeout 30 --json
kira start --no-open
```

`--json` makes add, holdings refresh and price refresh return an immediate job
receipt. A receipt is not completion: read or wait for its job, then inspect the
published result and coverage. Reuse the same idempotency key when retrying the
same request. [Agent tools and MCP](docs/AGENT_TOOLS.md) ·
[Packaged agent skill](skills/kira-wallet/SKILL.md).

Useful questions include:

- “Which chains have ETH worth at least $10 in my saved records?”
- “Show my top five recorded holdings across all wallets.”
- “Compare these saved analyses and explain what remains unknown.”
- “Refresh this wallet, then show the completed result in the web app.”

Names and symbols can match different assets. Kira identifies tokens by chain
and contract, retains unknown prices, and separates recorded spot value from
amount-specific sell estimates. Saved balances alone do not establish transfer
activity. Testnets, curve reserves and pool liquidity are excluded from USD
portfolio totals.

## Your wallets, your controls

- **Manage public addresses.** Add wallets, change names, review history and
  refresh holdings or prices in the app or through the CLI.
- **Refresh when needed.** Provider research starts with an explicit action.
  Opening a page or querying records does not refresh blockchain or price data.
  The app notices saved changes made by your agent and displays job progress.
- **Keep records locally.** Wallets, snapshots and provider references survive
  upgrades and agent sessions. Your agent host controls which facts it sends to
  its model service and how it stores conversations.
- **Create an optional OWS wallet.** The local form uses
  [Open Wallet Standard](https://openwallet.sh/) and follows its public EVM
  account. Enter the encryption passphrase yourself; keys stay in the local
  encrypted OWS vault. Kira has no signing or trading tool.

Alchemy remains required for new holdings and price research. Token indexes
provide candidates; on-chain reads verify balances. Unsupported indexes and
failed reads remain coverage gaps. **Analyze sell routes** is optional and uses
saved holdings; it does not discover additional tokens. Price refresh preserves
recorded balances and does not recover missing holdings.

DEX price references require at least $1,000 of reported pool liquidity and
exclude extremely one-sided pools. A displayed value is an estimate, not a
promise of sale proceeds. Observation timestamps remain attached to the facts.

## Upgrading from 0.1.20

Run `kira stop` before replacing the installed package, then restart the app
after installation. This closes the viewer and leaves research jobs intact.
Wallet names, provider references, jobs and snapshots retain their existing
format. The embedded chat interface and its model runtimes are removed. Saved
conversations and generated workspaces remain on disk and can be inspected with
`kira archive`; they are not automatically sent to your new agent session.
[Archive commands](docs/CLI.md#read-earlier-conversation-archives).

## Build and contribute

```sh
npm install --ignore-scripts
node bin/kira.cjs setup
npm test
python3 scripts/check-public.py
```

From source, replace `kira` with `node bin/kira.cjs`.
[Viewer guide](viewer/README.md) · [Release preparation](docs/RELEASE.md).
Original code and Kira character assets use the [MIT license](LICENSE).
See [third-party notices](THIRD_PARTY_NOTICES.md) for other assets and references.
