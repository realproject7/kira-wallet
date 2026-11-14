# CLI and provider configuration

## Wallet folders

Folder tools are introduced in 1.8.0. Check the installed `describe` output
before calling them.

```sh
kira describe folders_list --json
kira describe folder_set_members --json
kira call folders_list --arguments '{}' --json
kira call folder_create --arguments '{"name":"Treasury","idempotency_key":"create-treasury-once"}' --json
kira call folder_overview --arguments '{"folder_id":"FOLDER_ID"}' --json
```

Replace `FOLDER_ID` with an ID returned by the tools. `unfiled` reads wallets
without a folder. `portfolio_read` also accepts an optional `folder_id`, and
keeps its existing bounded wallet pagination. `folder_overview` returns the
saved dashboard, compact wallets and network summaries without token payloads.
These reads use projected records and start no provider or worker activity.

Folder writes are immediate metadata operations with durable idempotent
receipts. `folder_assign` moves registered public addresses to one folder or
`unfiled`. `folder_set_members` replaces one named folder's membership with the
chosen addresses, removing unchecked wallets to Unfiled. It requires the
`revision` returned by `folders_list` as `expected_revision`. Other folder edits
can use the same optional guard. A conflict keeps the saved state unchanged.
Folder deletion preserves wallets, names and all research snapshots.

`portfolio_holdings_refresh` and `portfolio_sell_routes_analyze` accept an
optional `folder_id`. Omitting it retains the global behavior. Batch admission
captures folder membership, so a retry cannot include newly moved wallets.
Existing per-wallet job receipts, eligibility and sequential execution remain
in use. These explicit research actions can consume provider allowance.

## Discover tools and optional h402 capabilities

```sh
kira describe --json
kira describe wallet_read --json
kira integrations --json
kira integrations h402 --enable --json --idempotency-key h402-enable-once
kira jobs read JOB_ID --json
kira integrations h402 --disable --json --idempotency-key h402-disable-once
```

`describe` returns the installed CLI/MCP schemas without creating a workspace
or starting research. `info` includes the recorded-data scope and optional
integration status. These additions require the 1.1.0 or later;
older installed releases should use their own `skill` and help output.

h402 is disabled by default. Enabling or disabling it saves a preference through
the shared job queue; inspect the returned job before claiming success. This
neither installs nor uninstalls software and never edits h402's configuration.
Install separately with `npm install -g @h402/cli` when requested. The onboarding
checklist and Workspace settings offer installation guidance for your agent.

Discovery reports `disabled`, `not_installed`, `available`, or `unavailable`,
plus CLI version when verified. It checks PATH and, only when enabled, runs
`h402 --version` with a two-second timeout. It never queries a catalog, inspects
a signing wallet, or makes a paid call. `available` is local CLI availability,
not verified provider or payment readiness. A running viewer may need restarting
after installation if its inherited PATH does not include the new executable.

Use the returned official `skill_url` to learn h402's own discovery and invocation
contract. Enabling the preference does not authorize payments. The host agent
uses existing user permissions and h402 limits for any paid work.

Kira is a local wallet engine, CLI and web interface. Any capable agent
can use the CLI; MCP is optional. Your agent host supplies its own model,
conversation, general tools and approvals. Kira does not start a model process.

## Portfolio research actions

From Home, use **Refresh all holdings** or **Update sell estimates (N)**.
Both queue ordinary per-wallet jobs and preserve previous snapshots. Work runs
one wallet at a time. Active wallets are skipped. Sell analysis requires a
finished current holdings scan; interrupted analysis is resumed and completed
analysis is skipped. Unchanged recorded quantities retain the last completed
analysis across new holdings snapshots, including completed partial analyses
with unknown routes. Only changed or never-analyzed wallets need a sell update.
Missing/retained balances wait for verified holdings instead of implying sales.
Home, wallet and Activity show the last sell-analysis timestamp. Saved quotes
keep their original price and quote times; equal holdings do not imply current
market conditions or guaranteed execution. Native/stable market references use
their separately recorded price timestamps.

Agents use the same actions:

```sh
kira call portfolio_holdings_refresh --arguments '{"idempotency_key":"portfolio-refresh-001"}' --json
kira call portfolio_sell_routes_analyze --arguments '{"idempotency_key":"portfolio-sell-001"}' --json
```

The response is a batch receipt with `jobs`, `skipped` and `errors`, not a job
completion. Read each returned `job_id`. Retry the same request key after a lost
response to recover the same wallet selection and admitted jobs. Different
requests skip wallets already queued or running. New wallets added later belong
to the next batch. These actions require an explicit request and never execute
trades. Sell analysis remains optional instead of starting on page loads.

Home, wallets, tokens and networks expose a **Sell-out estimate**. This sums
independent saved full-balance quotes and shows missing and limited-route
counts. It excludes testnets, archived networks, retained quantities and gas.
Shared pools, nested reserve tokens and different observation times mean this
is an indicative subtotal, not proceeds verified for a combined portfolio exit.
Missing estimates remain unknown. Token pages show recorded holders, largest
first; full coverage facts remain accessible through the CLI/MCP records.

## Install and choose a workspace

```sh
npm install -g kira-wallet
kira --version
kira info --json
kira skill
```

Node.js 22+, Python 3.11+ and a POSIX host are required; macOS is verified.
The package includes the engine, browser assets and declared dependencies.
It excludes wallet records, credentials, conversations and logs.

The supported CLI uses `~/.local/share/kira-wallet`, independently of the
current directory or agent session. `KIRA_DATA_DIR` selects another workspace;
the equivalent `--data-dir` option also works before or after the command:

```sh
kira --data-dir /absolute/private/workspace info --json
```

Keep this directory stable across sessions. `kira init` initializes it without
overwriting existing records. `KIRA_PYTHON` selects the Python executable.
Historical direct Python scripts retain their separate workspace defaults;
use the supported CLI for a consistent data root.

`--json` is accepted anywhere in the command. `info` returns the version,
data directory, capabilities, connection readiness, saved-data revision, job
status, UI availability and packaged skill path. Its `research_connection.status`
is `ready` when Alchemy is connected and `connection_required` before that.
`--data-dir` also works before or after the subcommand. Use `--help` for syntax.

## Open the local app

```sh
kira setup --no-open
kira start --no-open
kira status
kira stop
```

`setup` returns a `setup_url`; `start` returns a local URL. The agent host can
open it in its own browser or panel. Omit `--no-open` to use the default browser.
The default port is 8787; `--port` selects another. The loopback web app offers
wallet management, recorded analysis and explicit research controls. It has no
embedded agent chat or model-account setup.

`start --read-only` disables browser mutations. Changing modes requires an
explicit stop and restart. Starting the same workspace and mode reuses the
existing URL; a different workspace never silently reuses that server.
The old `--controls` option remains accepted but is unnecessary.
`stop` verifies the managed server identity. It does not cancel research jobs.
All saved-data queries and job commands work with the web app stopped.

## Connect providers

Alchemy is required for new wallet and price research. Saved results remain
readable without it. A human can connect it in **Workspace settings → Alchemy**
or enter the key at the hidden local terminal prompt:

```sh
kira connect alchemy
```

See [Alchemy setup](ALCHEMY_SETUP.md). Keep credentials out of agent messages
and command arguments. An agent can configure references to environment names
that the human has already prepared:

```sh
kira rpc set --chain 8453 --url-env KIRA_BASE_RPC
kira discovery alchemy --key-env ALCHEMY_API_KEY --explorers
kira config show
kira config import-env --file /absolute/private/rpc.env --key-env ALCHEMY_API_KEY
```

The environment file path above is a placeholder. Import references the file;
it does not copy keys or contact providers. It configures Alchemy RPC and
portfolio discovery while preserving custom chain overrides and explicit
fallback preferences. Environment values override the referenced file.
Reference names are case-sensitive. Missing or unreadable selected credentials
reject the import and preserve the configuration.

RPC, discovery and import commands apply synchronously when idle. If research
owns the writer, they return a queued receipt; `--json` always returns a queued
receipt without waiting. Inspect the resulting job before reporting the
configuration applied; its `result.provider_configuration` lists the applied
modes and reference names. Safe configuration output contains references, not values.

New configurations allow verified public RPC fallback. `--custom-only`
disables fallback; `--public-fallback` restores it. Existing opt-outs persist.
`--priority public_first` or `--priority custom_first` selects ordering for a
custom RPC. Plain HTTP is accepted only for loopback endpoints. Public RPC
alone does not establish complete ERC20 discovery.

```sh
kira rpc public
kira doctor
kira doctor --live --chains 1,8453,81457 --budget 30
```

`doctor` is local by default. `--live` explicitly makes bounded provider probes
for chain identity, blocks and known bytecode. The budget counts JSON-RPC
method calls. Exit code 2 means a sampled chain is unavailable or limited;
a successful sample does not prove complete archive or wallet coverage.

## Add, name and refresh wallets

Replace the address placeholder with the public EVM address supplied by the user.

```sh
kira add '<public-evm-address>' --tag 'Daily wallet' --idempotency-key add-daily-001 --json
kira wallets --json
kira wallets tags 'Daily wallet' --tag 'Daily wallet' --tag 'Savings' --idempotency-key tags-daily-001 --json
kira refresh 'Daily wallet' --idempotency-key refresh-daily-001 --json
kira prices 'Daily wallet' --idempotency-key prices-daily-001 --json
```

The first tag is the display name. Exact names and registered addresses select
wallets. `add` runs the first full holdings lookup itself; use `refresh` for
later updates. Reuse an idempotency key only when retrying the same intended request.

`add`, `refresh` and `prices` persist a durable job before doing research.
`--json` or `--enqueue` returns its receipt immediately and starts a separate
worker. Without either option, these commands wait and print the initial and
final job records. A receipt confirms admission, not successful research.

Holdings refresh checks configured networks and returned token candidates,
including the reachable Mint Club registry. There is no 128-candidate cap.
A price refresh updates saved holdings without discovering new tokens or
replacing recorded balances. Reads and page navigation never trigger either
operation. Manual refresh is the normal workflow; no real-time polling of
providers is required.

## Inspect and control jobs

```sh
kira jobs list --json
kira jobs read JOB_ID --json
kira jobs wait JOB_ID --timeout 30 --json
kira jobs cancel JOB_ID --json
kira jobs resume JOB_ID --idempotency-key resume-daily-001 --json
kira jobs deepen HOLDINGS_JOB_ID --idempotency-key sell-daily-001 --json
kira jobs run --json
```

Replace job IDs with values from real receipts. `wait` accepts 0–120 seconds.
Its `completed` flag means the job left queued/running state; inspect
`job.state`, result, errors and coverage. Failed, cancelled and interrupted
jobs are not successful. Partial results preserve unresolved checks.

`jobs deepen` runs optional sell-route analysis from an immutable saved
holdings source. It does not rediscover tokens or reread balances. A newer
holdings lookup supersedes earlier analysis. Older limited scans need a new
holdings refresh before this action. Work runs in bounded slices without an
overall completion deadline or exhaustive-market guarantee.

Interrupted jobs require explicit resume. `jobs run` starts queued work and
reconciles crash receipts, without replaying interrupted jobs. Failed or
cancelled jobs retain last good results and unpublished evidence. Price jobs
preserve immutable overlays before updating the current projection.
The legacy `--resume SNAPSHOT_DIRECTORY` on `add` or `refresh` is only for
unpublished snapshots; use job IDs for durable work.

## Query saved facts

```sh
kira call portfolio_read --arguments '{"offset":0,"limit":20}' --json
kira call holdings_query --arguments '{"mode":"rank","limit":10}' --json
kira call holdings_query --arguments '{"mode":"search","query":"ETH"}' --json
kira call wallet_read --arguments '{"wallet":"Daily wallet","offset":0,"limit":100}' --json
kira call token_read --arguments '{"chain_id":8453,"address":"native"}' --json
kira call snapshots_list --arguments '{"wallet":"Daily wallet","limit":20}' --json
kira call snapshots_list --arguments '{"wallet":"Daily wallet","kind":"prices","limit":20}' --json
kira call job_list --arguments '{"state":"active","offset":0,"limit":20}' --json
kira ui context --json
```

`snapshots_list` defaults to holdings analyses. Use `kind: "prices"` for saved
price observations or `kind: "all"` for both. Pass the returned IDs to
`snapshot_read` or `snapshots_compare`. Price observations reproduce their saved
overlay and keep the linked holdings unchanged, even after another refresh.
Comparisons include price/value changes and native positions; a price change
is not a token transfer. No provider request is made by these reads.

`job_list` accepts `state` groups `all` (default), `active` (queued or
running), `succeeded` (succeeded or partial), `attention` (interrupted or
failed) and `cancelled`, or one exact state: `queued`, `running`, `partial`,
`interrupted` or `failed`. Add `wallet` to limit results to one registered
wallet.

Follow returned `next_offset` values when complete pages are needed. Use
`holdings_query` for server-computed ranking, counts and aggregates across the
full inventory. Same-symbol tokens may differ by chain and contract; retain
that ambiguity until an exact asset is selected. `ui context` is the last
recorded browser selection, not a new user instruction.

`call TOOL --arguments JSON` exposes the complete shared read and mutation
catalogue. Mutation calls require `idempotency_key`. `kira tools` starts the
read-only stdio MCP adapter; `kira tools --allow-writes` explicitly exposes
mutations too. See [the tool contract](AGENT_TOOLS.md) and `kira skill`.

Keep unknown balances and prices distinct from zero. Preserve observation
timestamps and coverage. Spot value, pool TVL, curve backing and gas-excluded
sale estimates have different meanings. Equal recorded balances do not prove
that no transfers occurred between observations.

## Read earlier conversation archives

Upgrading preserves wallet records, settings, snapshots, jobs and historical
conversation/output files. Kira no longer resumes embedded model sessions.
Archives are local evidence and are not automatically sent to an agent.

```sh
kira archive list --json
kira archive read CONVERSATION_ID --json
kira archive workspaces --json
kira archive files WORKSPACE_ID --json
kira archive export WORKSPACE_ID --path report.csv --output ./recovered-report.csv --json
```

Use IDs and relative file paths returned by the preceding commands. Workspace
listing also finds generated files from sessions whose chat history was off.
Reads are bounded. Export accepts a regular file of at most 20 MB, rejects
symlinks and writes a new destination without overwriting an existing file.

## Browser wallets and optional local OWS

**Connect wallet** discovers EIP-6963 browser wallets and lets the human select
a public account. Disconnecting from Kira does not remove saved wallets or
revoke extension permissions. An embedded browser without an extension can
open the same local URL in a compatible browser on that computer.

**Local OWS wallet** lists public EVM descriptors from Open Wallet Standard.
Its optional SDK is `@open-wallet-standard/core` 1.4.3; the vault defaults to
`~/.ows`, with `KIRA_OWS_VAULT` as an override. Creation requires a human-entered
passphrase in the local interface. Kira does not return private keys or seed
phrases. Recovery keeps the original passphrase and interrupted requests retain
their identity to prevent duplicate creation. Use OWS owner tools for backup
and recovery. A newly created wallet is registered and linked without starting
asset research. Use **Refresh holdings** when you want to check its assets.
Linking an existing, unregistered OWS wallet still starts its initial research.
Agents must leave passphrase entry to the human. OWS absence
does not block ordinary public-address onboarding. Kira exposes no signing,
trading, key export or account deletion.

## Market references and sell-estimate ordering

Version 1.3.0 displays saved market references for recognized native coins and
stablecoin contract identities when a saved amount-specific quote is unavailable.
The UI marks these as `Spot ref.`. They use the recorded market value, including
any observed deviation from a dollar peg. Gas, fees, price impact and execution
are not verified by these references. Symbols alone never establish identity.
All-token, wallet and network tables offer sell-out ordering; paged local read
endpoints accept `sort=sell_out`, with unknowns last. This includes indicative
quote subtotals and eligible references, not guaranteed proceeds.

If SDK membership changes while configured deployment addresses remain valid,
portfolio refresh now preserves the configured network scope and verifies removed
entries against the reviewed immutable SDK source. A retry reuses current jobs
that failed this preflight. Contract-address mismatches still require correction.


## Asset exclusions and explicit risk checks (1.4.0)

Discover `token_policy` and `token_risk_check` with `kira describe TOOL --json`.
Pass the recorded `chain_id`, contract `address` (or `native` for preferences),
and an `idempotency_key` to `kira call`. Preferences also require `mode`:
`exclude`, `include`, or `auto`. These actions finish immediately and return
persisted receipts, rather than queued jobs. Risk lookup explicitly contacts
GoPlus, sending only the token identity; no wallet or credentials are sent.

Use `holdings_query` with `portfolio_status` set to `portfolio` (default),
`review`, `excluded`, or `all`. Browser lists offer the same selection. Excluded
and review assets retain balances and reported estimates, but do not contribute
to portfolio or sell-out totals. Restore automatic classification or explicitly
include an asset to reverse the preference. Warnings survive manual inclusion.


In 1.5.0 the browser calls manual exclusions **Hidden**. A trailing eye control
hides/restores directly. **Manage tokens** selects visible-page identities for
bulk hiding/restoration; page or filter changes clear selection. Hidden assets
still use `portfolio_status=excluded` in CLI/MCP. Existing financial semantics
and raw evidence are unchanged. Undo restores each confirmed item's prior mode.

Activity supports full-history wallet/task search and wallet/status filters.
The job-history response includes scoped `counts` and `last_updated_at` before
status filtering, independent of the requested page. `job_list` also accepts
`query` (up to 200 characters). Partial completed work counts as saved; only
failed/interrupted work counts as needing attention. The browser keeps stage
logs and technical identifiers in task details, with the existing recovery
operations and no automatic provider calls.


## Remove and restore registered wallets

Use Manage wallets in the web app to select multiple saved wallets, then Remove.
The confirmation reviews the exact selected addresses. Removed wallets leave
portfolio totals while their research and local keys stay intact. Open Removed
wallets in the manager to restore selected registrations without research.
Pause selected wallets' queued/running work in Activity before removal.

CLI and optional MCP use the same immediate local operations:

```sh
kira call wallets_removed --arguments '{}' --json
kira describe wallets_remove --json
kira describe wallets_restore --json
```

`wallets_remove` and `wallets_restore` take 1–1,000 unique public addresses in
`wallets`, the current `expected_revision` from `wallets_removed`, and an
`idempotency_key`. Recovery reads accept `offset`, `limit` (at most 100) and
`query`. These operations never delete snapshot files, modify keys, or start
provider work. An already removed address must be restored before adding or
refreshing it. This preserves its earlier names and research.


## Protocol positions and platform allocation

`positions_read` returns saved LP, vault, NFT-backed and staking claims. It accepts
optional `wallet`, `folder_id`, `chain_id`, `token_id`, `platform`, `offset` and
`limit` (at most 100). Allocation percentages use known, non-overlapping recorded
value in the selected wallet/folder/token/network, before the platform list filter.
Unknown amounts and incomplete discovery remain explicit. Position NAV, pending
rewards and executable sell estimates are separate concepts.

```sh
kira describe positions_read --json
kira call positions_read --arguments '{"wallet":"Savings","limit":25}' --json
kira call positions_refresh --arguments '{"wallet":"Savings","idempotency_key":"refresh-savings-platforms"}' --json
kira call portfolio_positions_refresh --arguments '{"folder_id":"FOLDER_ID","discover":true,"idempotency_key":"find-folder-platforms"}' --json
```

The first scan discovers positions. Later refreshes default to saved-claim and
wallet-inventory checks. `discover: true` additionally sweeps supported pool and
farm registries for new deposits. Legacy Aerodrome has over 30,000 pools; broad
initial discovery can be slow even with batched reads. Explicit full discovery
is kept separate from ordinary refresh. Jobs share the existing sequential writer,
short resumable slices, pause/resume, duplicate coalescing and bounded retries.
Opening any page or reading saved claims launches no provider work. Use Activity
to monitor source progress; financial unknowns never establish a zero holding.
