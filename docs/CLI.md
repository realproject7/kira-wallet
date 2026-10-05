# CLI and provider configuration

The package carries the Python engine, browser assets and declared viem
dependency. It needs no Python packages and no sibling project. The package
file list excludes wallets, snapshots, conversations, caches, logs and private settings.
Install version 0.1.2 from its GitHub release, then run `kira setup`:

```sh
npm install -g https://github.com/realproject7/kira-wallet/releases/download/v0.1.2/kira-wallet-0.1.2.tgz
kira setup
```

The npm registry currently offers version 0.1.0 through `npm install -g kira-wallet`.
Registry publication remains an operator action. The code and original character assets use the MIT license.

## Lifecycle

`kira init` prepares an empty private data directory. `kira start --port 8787`
starts a loopback-only read-only viewer. `kira status` identifies the managed
instance. `kira stop` checks its live instance ID and OS process identity.
Another portfolio never silently reuses that server.

`kira setup` starts the loopback viewer with local controls and opens its setup
screen. Use `--no-open` to print its URL instead. If a read-only viewer is already
running, stop it explicitly before setup. The normal `kira start` remains read-only.

The 0.1.2 GitHub release starts with a wallet checklist. Add a public EVM
address or use the browser wallet picker. Registration starts one explicit
research job; follow it in Activity and read the saved portfolio report.
No signature, seed phrase or private key is needed.

Public RPC checks known assets and Mint Club. For broader ERC20 discovery,
open Research connections, select Alchemy and name the private environment
variable holding its key. Never paste the key into the browser. `kira doctor`
checks whether the configured key is available. Configuration alone does not
prove complete coverage; inspect the recorded results and gaps.

Connecting Codex or Claude is optional. Use Connect your AI when ready, verify
a generic response and explicitly choose context permissions. Assistant answers
render a safe Markdown subset; raw HTML, images and links remain inert text.
Install the 0.1.1 GitHub archive for this wallet-first setup. The npm registry's
0.1.0 package continues to use the earlier account-first setup.

## Your model account

Install and sign in to the official Codex CLI or Claude Code CLI first. Kira
detects the installed binary and native subscription login without copying its
authentication. Verified adapter versions are Codex 0.158.x and Claude Code
2.1.259 through 2.1.x. Other versions are blocked until their restrictions are
verified. This is a native CLI connection, with no Kira account, API-key proxy or
hosted portfolio backend.

In setup, choose the CLI account and an optional model ID. The blank model field
uses the CLI default. Choose no automatic wallet context, one registered wallet,
or the whole recorded portfolio. A generic response check sends no wallet data
and must pass before these settings are saved.

Your entered message and approved context go through the CLI to its model
service. Context includes recorded balances, wallet names and addresses, chain
and contract identities, timestamps, unknown prices and coverage. Credentials,
RPC endpoints, raw provider errors and local paths are excluded. Changing the
provider, model, context or selected wallet creates a new conversation.

Kira-local history is opt-in and uses private `conversations/` files. With history
off, conversations and drafts stay in memory. A new server process starts a fresh
conversation; saved files remain available locally and are not automatically
replayed. Native CLI, administrator policy and provider data policies remain a
separate trust boundary. With wallet research enabled, Kira can read saved analyses, compare history and queue holdings or price updates. Jobs appear in Activity and continue independently of chat. Signing and trading stay outside the agent.
See [the conversation contract](ONBOARDING_CHAT_CONTRACT.md).

Global `--data-dir` precedes the command. `KIRA_DATA_DIR` provides the same
override. `KIRA_PYTHON` selects Python. Direct historical scripts keep their
workspace default. The supported CLI uses the user data directory. Installed
assets and writable runtime files use separate roots.

## Public RPC

```sh
kira rpc public
kira discovery none
kira doctor
kira doctor --live --chains 1,8453,81457 --budget 30
```

No credential file is required. Live doctor performs bounded identity, block,
deployed bond bytecode, Multicall3 bytecode and historical bytecode probes.
It reports endpoint indexes. These samples do not guarantee broad archive
history, multicall execution or wallet coverage. Exit code 2 means at least one
sampled chain is unavailable or limited. Failed endpoints stop after their
first failure; at most three are tried per chain. There are no hidden retries.
The budget limits JSON-RPC method calls in that invocation. Full analysis has
no global request cap yet.

## Custom RPC and discovery

Set an endpoint in your shell or private environment file. Keep the value out
of command arguments. Configuration stores references only.

```sh
export KIRA_BASE_RPC='<your HTTPS endpoint>'
kira rpc set --chain 8453 --url-env KIRA_BASE_RPC
export ALCHEMY_API_KEY='<your key>'
kira discovery alchemy --key-env ALCHEMY_API_KEY --explorers
kira config show
```

Public fallback is automatic for new configurations. A missing or failing custom endpoint uses verified public endpoints, including failures after the initial connection. Reads keep the selected block. `--custom-only` explicitly disables fallback; an existing opt-out is preserved. `--public-fallback` restores it. Plain HTTP is accepted only for loopback endpoints. Public RPC does not provide complete ERC20 discovery.

Discovery is independent. Without an indexer, native and reachable Mint Club
reads still run and general discovery stays incomplete. Configuring an RPC
does not prove ERC20 discovery completeness.

## Explicit compatibility import

```sh
kira config import-env --file /absolute/private/rpc.env --key-env ALCHEMY_API_KEY
```

The import references the file instead of copying keys. It configures Alchemy
RPC and portfolio discovery separately, with public fallback enabled to match
the historical engine. Environment overrides the file. Missing files or keys
produce limited coverage; malformed configuration fails with safe errors.
The import does not contact providers. Private settings are never served.

Analysis output contains wallet addresses and tags. Keep runtime directories
outside repositories or ignored. Never publish operator holdings as demos.
The demo command uses synthetic addresses and sample prices only.

## Durable research and local controls

Normal `kira add`, `kira refresh` and `kira prices` now save a version 1 job
before running the existing engine. Use `--idempotency-key <stable-key>` to
retry a submission without duplicating work. Add `--enqueue` to return after
queuing the job and start a separate worker. `--resume <snapshot-directory>`
remains the legacy unpublished-snapshot interface. New durable jobs resume by
job ID:

```sh
kira jobs list
kira jobs read <job-id>
kira jobs cancel <job-id>
kira jobs resume <job-id> --idempotency-key <stable-resume-key>
kira jobs run
```

An interrupted job needs an explicit resume. Published partial results retain
coverage gaps and require a new refresh to investigate again. Failed and
cancelled jobs retain their last good result and unpublished evidence.
`jobs run` starts queued work and reconciles crash receipts; it does not replay
interrupted jobs. Price jobs retain immutable overlays before updating the
viewer projection. A viewer stop does not cancel research jobs.

Start with `kira start --controls` to enable protected browser actions. The
usual start remains read-only. Stop an existing read-only instance before
starting one with controls. Actions need the local session and same origin.
The supported URL uses 127.0.0.1. Browser controls offer wallet registration,
exact names, holdings/price refresh, cancel/resume, saved analysis comparison,
RPC references and discovery references. The synthetic demo cannot start
provider research. Enter endpoint credential references in Connections;
secrets and URLs remain outside the browser.

Use `kira --data-dir <private-portfolio> tools` for the read-only stdio adapter.
See [the tool guide](AGENT_TOOLS.md) and [job contract](JOB_CONTRACT.md).
Connected chat uses the native CLI account and approved context from setup.
The published package and original Kira assets are MIT licensed.

## Browser and local OWS wallets

Use **Connect wallet** to choose an EIP-6963 browser wallet such as MetaMask.
The app shows the provider and public accounts, lets you review the account
before registering it, and provides **Disconnect from Kira**. Disconnecting does
not remove recorded wallets or revoke extension permissions. Without a browser
wallet, the chooser explains how to open this same local URL in a compatible
browser. A phone cannot reach another computer's loopback URL.

**Local OWS wallet** lists public EVM descriptors from Open Wallet Standard.
The optional pinned SDK is `@open-wallet-standard/core` 1.4.3. The vault defaults
to `~/.ows`; `KIRA_OWS_VAULT` selects another local vault. Creating a new wallet
requires a human-entered encryption passphrase and uses OWS's encrypted local
storage. Kira never returns the mnemonic or private key. Back up and recover
with OWS owner tools. Existing keys and tags are preserved.

A private owner receipt serializes creation across apps using the same vault.
Retrying an interrupted creation recovers its request identity instead of
creating a second wallet. The browser keeps only the public request identity
in session storage. It clears password fields immediately. Recovery keeps the
original encryption passphrase. No signing, key export or account deletion
endpoint is exposed. OWS absence does not block ordinary address or browser
wallet onboarding.
