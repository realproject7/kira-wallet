# Kira Wallet

A local EVM wallet research workspace with Kira and durable research jobs.
It records direct holdings, Mint Club bonding curves and DEX liquidity evidence.
Missing coverage and prices stay unknown.

Original code and character assets are open source under MIT. Third-party
references retain their own terms; see [notices](THIRD_PARTY_NOTICES.md). The npm
first npm publication is prepared for the operator. No signing, transfers or trades
are implemented.

## Local installation

Requirements: Node.js 22 or newer and Python 3.11 or newer. macOS is verified.
Analysis and daemon lifecycle currently require POSIX process and file-lock APIs.

```sh
npm install --ignore-scripts
node bin/kira.cjs init
node bin/kira.cjs doctor
node bin/kira.cjs setup
```

The viewer starts at http://127.0.0.1:8787. Data defaults to
`~/.local/share/kira-wallet`, separate from the installed package. Use
`--data-dir /absolute/private/directory` before the command for another portfolio.
The existing workspace viewer can still run at port 8765.

For an isolated sample with synthetic data:

```sh
node bin/kira.cjs --data-dir /tmp/kira-sample demo --port 8790
node bin/kira.cjs --data-dir /tmp/kira-sample stop
```

## Research

```sh
kira add <operator-supplied-address> --tag '<exact tag>'
kira refresh '<registered address or tag>'
kira prices '<registered address or tag>'
```

From source, substitute `node bin/kira.cjs` for `kira`. Commands create private
runtime data. The viewer detects local updates within five seconds; it does
not poll providers. Resume a failed analysis with the same command and
`--resume <relative snapshot directory>`.

The engine checks official Mint Club deployment scope, discovers indexed held
tokens when configured, pins chain reads to blocks, enumerates reachable bond
registries, queries ERC20 and registered ERC1155 token ID 0 balances, records
curve reserves and burn quotes, and verifies supported DEX pool contracts.
Shared caches contain asset identities, never another wallet's balances.
Registry publication is atomic and analysis writers are serialized.

Public RPC can read native balances, known tokens and reachable bond registries.
General ERC20 discovery requires an indexed provider and successful responses.
Testnets, pool TVL and shared curve backing are excluded from wallet USD totals.
Spot value is distinct from an executable redemption estimate.

See [CLI and provider configuration](docs/CLI.md) and
[viewer behavior](viewer/README.md). Development reports, design concepts and
generation records remain in the source checkout under `docs/` and `prototype/`.

## Verification

```sh
npm test
node --check pipeline-onchain.cjs
node --check onchain.cjs
```

UI changes also require responsive browser and keyboard checks. Installation
checks must use a fresh directory without operator credentials or data.

## Durable local workspace

Development build 0.1.0-dev.2 adds persisted research jobs and opt-in protected
browser controls. Start with `kira start --controls`; the usual start stays
read-only. CLI and browser use the same typed job service for research, exact
wallet names and connection references. Jobs preserve prior results, retain
partial evidence and require explicit interruption recovery. Price jobs keep
immutable overlays. Saved analyses can be compared with exact decimal balance
changes and missing records remain unknown.

`kira tools` is a read-only local MCP adapter, with no automatic account or
model connection. See [CLI usage](docs/CLI.md), [job contract](docs/JOB_CONTRACT.md),
[tool setup gate](docs/AGENT_TOOLS.md) and [continuation evidence](docs/KIRA_JOBS_BUILD_REPORT.md).

## Kira research workspace

The workspace places Kira's local briefing and connected conversation
beside the evidence. The brand link returns Home. Overview, All tokens
and Activity have distinct tabs; wallet controls stay together. On small
screens, switch directly between Portfolio and Kira.

All tokens uses existing recorded aggregates with chain-plus-contract identity,
search, network and pricing filters, and 50 rows per page. It does not query
providers. Activity separates active work from persisted job history and shows
state, elapsed time, last progress and recovery controls. Missing progress does
not silently turn a running job into a completed or failed job.

Run `kira setup` to connect your installed Codex or Claude Code CLI account.
Choose no wallet context, one registered wallet or the whole portfolio. A real
response check verifies the selected model before permissions are saved. Drafts
stay in memory. Kira-local conversation retention is opt-in; provider and native
CLI policies remain separate. Context or model changes start a fresh conversation.
Chat does not sign, trade or automatically start research. See the
[onboarding and conversation contract](docs/ONBOARDING_CHAT_CONTRACT.md), the
[redesign report](docs/KIRA_REDESIGN_REPORT.md) and
[agreed wallet capability direction](docs/WALLET_CAPABILITIES.md).

For a contribution, use synthetic data and run `python3 scripts/check-public.py`
before a push. Never attach a personal portfolio screenshot, registry, snapshot,
job, credential, local path or log to an issue or PR. Repository history uses a
public noreply identity. The `kira-workspace-v1` tag preserves the prior UI.
