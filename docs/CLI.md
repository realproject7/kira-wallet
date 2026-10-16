# CLI and provider configuration

The package carries the Python engine, browser assets and declared viem
dependency. It needs no Python packages and no sibling project. The package
file list excludes wallets, snapshots, conversations, caches, logs and private settings.
Install Kira from npm, then run `kira setup`:

```sh
npm install -g kira-wallet
kira setup
```

The operator published npm version 0.1.5. Version 0.1.6 is a preparation candidate. GitHub v0.1.3 remains
a draft; the previous archive and checksum are available from the
[0.1.2 GitHub release](https://github.com/realproject7/kira-wallet/releases/tag/v0.1.2).
Registry publication remains an operator action. The code and original character assets use the MIT license.

## Lifecycle

Use `kira setup` for your first setup. For everyday use, `kira start` starts
the local app with browser controls and opens it in your browser. The default
port is 8787. Use `--port` to choose another port, or `--no-open` to print the
URL without opening a browser. `kira status` identifies the managed instance.
`kira stop` checks its live instance ID and OS process identity before stopping it.

`kira init` prepares an empty private data directory. `kira start --read-only`
starts a loopback-only viewer without wallet or research actions.
Another portfolio never silently reuses that server.

`kira setup` starts the loopback viewer with local controls and opens its setup
screen. Use `--no-open` to print its URL instead. If a read-only viewer is already
running, stop it explicitly before setup or a normal start. Changing between
read-only and control modes requires an explicit stop and restart. Starting
an already-running app in the same mode reuses its URL. The old `--controls`
option remains accepted for existing scripts but is no longer needed.

These startup defaults apply from published 0.1.3. In the older 0.1.2 package, use
`kira setup` or `kira start --controls` for the full app.

The 0.1.2 GitHub release starts with a wallet checklist. Add a public EVM
address or use the browser wallet picker. Registration starts one explicit
research job; follow it in Activity and read the saved portfolio report.
No signature, seed phrase or private key is needed.

Published 0.1.4 explains limited discovery before wallet registration and beside
holdings. Missing coverage keeps the portfolio estimate partial. Existing snapshots require a holdings refresh after connecting
an indexer; a price refresh does not discover missing tokens.

Public RPC checks known assets and Mint Club. For broader ERC20 discovery,
open Custom RPC & token coverage, select Alchemy and follow its local key guide.
Published 0.1.5 uses one save for Alchemy RPC and discovery; chain overrides
remain under Advanced. Never paste the key into the browser. `kira doctor`
checks whether the configured key is available. Configuration alone does not
prove complete coverage; inspect the recorded results and gaps.

Connecting Codex or Claude is optional. Use Connect your AI when ready, verify
a generic response and explicitly choose context permissions. Assistant answers
render a safe Markdown subset; raw HTML, images and links remain inert text.
The wallet-first setup is included in published npm 0.1.3. The historical
0.1.0 package uses the earlier account-first setup.

## Your model account

Install and sign in to the official Codex CLI or Claude Code CLI first. Kira
detects the installed binary and native subscription login without copying its
authentication. Verified adapter versions are Codex 0.158.x and Claude Code
2.1.259 through 2.1.x. Other versions are blocked until their restrictions are
verified. This is a native CLI connection, with no Kira account, API-key proxy or
hosted portfolio backend.

From published 0.1.5, setup opens the existing Account / Permissions / Ready
modal directly. Choose Codex or Claude, then Use default model or a readable
model choice. Codex choices come from bounded native metadata; Claude offers
Sonnet, Opus and Haiku aliases. A catalog is not proof of account access.
Advanced accepts a custom identifier and preserves saved identifiers absent
from the catalog. Workspace settings reopens the same selector and permissions. Choose no automatic wallet context, one registered wallet,
or the whole recorded portfolio. A generic response check sends no wallet data
and must pass before these settings are saved.

Your entered message and approved context go through the CLI to its model
service. Context includes recorded balances, wallet names and addresses, chain
and contract identities, timestamps, unknown prices and coverage. Credentials,
RPC endpoints, raw provider errors and local paths are excluded. Changing the
provider, model, context or selected wallet creates a new conversation.

New setup in 0.1.5 recommends saving history and preselects it. Existing saved
true and false choices are restored exactly. Saving lets you reopen chats after
restart; it does not expand model memory or wallet access. The choice and
research permission remain editable in Workspace settings. Kira-local history uses private `conversations/` files. With history
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
RPC and portfolio discovery together, preserving existing custom chain overrides
and explicit fallback preferences. New configurations allow public fallback. Environment overrides the file. Missing files or keys
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

Start with `kira start` to use protected browser actions. Use `--read-only`
for a viewer without those actions. Stop an existing instance before switching
modes. Actions need the local session and same origin.
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

## Free reads and broader token coverage

Public RPC is preferred for ordinary reads, including when a custom backup is
configured. Advanced settings can select custom first or custom only. For CLI
configuration, use `kira rpc set --chain 8453 --url-env KIRA_BASE_RPC --priority
public_first`. Existing custom-only choices remain unchanged. Alchemy token
discovery uses the configured key directly. See [free RPC behavior](FREE_RPC.md)
and the [Alchemy setup guide](ALCHEMY_SETUP.md).
