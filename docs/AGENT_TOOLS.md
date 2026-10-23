# Recorded research tools

`kira --data-dir <private-portfolio> tools` serves a read-only MCP adapter over
newline-delimited JSON on stdin/stdout. Protocol version is pinned to
2025-06-18. It performs no login, model turn, provider request or research
mutation. Diagnostics stay out of stdout. The process exits on EOF.

Tools: portfolio_read, wallet_read, token_read, network_read, job_list,
job_read, snapshot_read and snapshots_compare. Arguments reject extra fields.
Tokens use chain ID and exact contract, or `native`. Missing records remain
unknown. Snapshots expose facts and safe source links, with fixed provider
errors. No arbitrary files, shell commands, credentials or mutation tools are
available. Local access to this process grants access to the selected portfolio.
Only connect it to an explicitly chosen client and data directory.

Example client-side stdio configuration, after operator approval:

```toml
[mcp_servers.kira]
command = "kira"
args = ["--data-dir", "<private-portfolio>", "tools"]
```

Replace the placeholder locally. Do not commit portfolio paths or credentials.
Kira does not edit the operator's Codex configuration automatically.

## Connected Kira chat

The 0.1.20 candidate offers explicitly selected native Codex and Claude work modes.
It exposes the existing `ResearchTools` catalog through a private per-session
MCP bridge, with the same wallet scope and durable research-job implementation.
The native agent chooses its own reads and general tools; it does not use the
recorded chat's forced read plan or eight-call loop. Each tool request is checked
against the live turn and current permissions. Refresh retries within a turn
reuse the durable request identity. No model or native child receives provider
credentials or portfolio-directory configuration through the bridge.

The bridge accepts only authenticated loopback requests without an Origin
header and is disabled between turns. It is distinct from the public read-only
`kira tools` adapter above. Native sessions preserve configured user integrations
and use a separate output workspace. Wallet scope controls Kira tools; it is not
an OS restriction on the native CLI. See [work modes](CLI.md#native-agent-workspaces-0120-candidate).

The following describes recorded wallet chat, retained for existing connections
and available when native work mode is not selected.

The in-app conversation uses a supported installed Codex or Claude CLI account.
A generic response check is required before saving a selected provider, model,
wallet scope and research permission. It sends no wallet facts. Authentication
stays with the installed CLI. No desktop tokens or authentication files are copied.

With research enabled, a bounded host-mediated loop provides portfolio_read,
wallet_read, token_read, holdings_query, snapshots_list, snapshot_read, snapshots_compare,
job_list, job_read, holdings_refresh and prices_refresh. Every operation is
scoped to registered wallets allowed by the conversation. Historical reads use
normalized financial projections. Unknown values and historical quote times
remain explicit. Native shell, file, browser and MCP execution stay disabled.

Automatic context and portfolio_read include every approved wallet with a
bounded first page of up to 12 holdings. asset_count and assets_omitted retain
the recorded inventory size. wallet_read returns a compact page of up to 100
holdings; offset and limit are optional. Follow next_offset until null before
claiming a complete inventory. snapshot_read and snapshots_compare also accept
offset and limit. token_read supplies detailed curve, pool and exit evidence.
Context-limit errors have failed tool receipts, rather than completed receipts.

Chain evidence includes explicit native balances, including observed zero,
their observation times and blocks, and registry scan blocks. Empty positive
holding inventories do not remove these observations. Saved-analysis reads
also retain snapshot price-reference values and times without provider URLs
or debug fields. A comparison flag can reflect observation or reference changes
without proving a balance change or a different set of checked networks.
Research job reads include the approved wallet identity directly.

Refresh tools admit typed durable engine jobs. Current scope and cancellation
are checked immediately before admission. Queued work is visible in Activity;
chat cancellation does not cancel engine work already accepted. Duplicate
refresh requests within one turn reuse the same job. At most eight tool calls,
420 seconds and bounded context are permitted per turn. Existing configurations
keep their research permission off until explicitly enabled.

OWS create/list and browser wallet connection are human interfaces, not model
tools. The agent never receives passphrases, mnemonics, private keys or provider
credentials. Messages and approved wallet facts reach the selected model service
through the user's CLI; local storage does not imply an offline model.

See [the conversation contract](ONBOARDING_CHAT_CONTRACT.md).
The standalone stdio MCP adapter above remains read-only and separate.

Native responses select the final Codex agent message. Older verified event
streams without a phase use their last agent message. Commentary cannot become
a tool request by concatenation. A mixed or malformed request gets one bounded
correction; no tool executes from it and repeated malformed protocol fails
without adding raw JSON to conversation history. Turn receipts expose only
bounded tool names and completed/failed outcomes.

Job reads include analysis phase, parent/continuation IDs and real progress
events. Normalized chain discovery completeness is separate from a job's
on-chain checkpoint status. Deferred candidates and pending networks are not
failed reads or zero holdings. Historical observations cannot establish current
execution, transfers or realized profit.

Before answering, scoped research chat must declare a `records_read` plan
containing every requested source, up to 32 declared read tools. An empty plan
is for greetings or action-only requests. Planning cannot start a refresh.
Each child has its own host receipt. The declared plan and literal JSON read
requests are matched against actual arguments, including chain and contract.
An incomplete delivered plan receives one bounded continuation attempt before
the turn is marked partial. Full inventory
requests require contiguous delivered pages through `next_offset: null`.
Failed or undelivered pages remain unread, with retry arguments in the turn's
`read_completion`. Automatic context is not a requested tool receipt. This
bounded check does not verify every semantic requirement in natural prose.

Token-specific queries read all approved wallets with `token_read`, without
enumerating unrelated inventory pages. Its optional `minimum_value_usd` filters
recorded mainnet values. Unknown and outside-USD positions have separate counts.
`position_count` is computed by the host; a read-plan count deduplicates returned
wallet/chain/asset identities rather than asking the model to tally its table.

rpc_status pending means a network has not yet been researched. It does not
prove an RPC outage. For a curve comparison, match chain and contract and
compare reserve, supply, next-mint price and royalty observations. A newer
block or a different wallet-sized burn quote alone cannot prove curve movement.

## Bounded full-inventory queries

Connected chat uses `holdings_query` for names, rankings and aggregates. Its
`mode` is `search`, `rank` or `aggregate`. It scans every approved saved position
on the host and returns at most 25 results per page. This response bound never
limits holdings discovery. Optional filters include wallet, chain, environment
and minimum recorded USD value. Exact symbols, names and contracts take
precedence over substring matches; multiple chain/contract identities remain
explicitly ambiguous. `group_by: asset` combines the priced subset by identity,
while `position` keeps each wallet position separate. Unknown and excluded
positions have independent counts. Ranking cannot create a price for them.

Top-N completion requires a delivered full-inventory ranking receipt, including
natural requests such as “top five.” Search pages must be delivered through the
last match before claiming that all matches were read. A host count or sum does
not require sending every position to the model. These reads never queue jobs.
The existing 32-read plan, eight-round, prompt/context and time limits remain.
Detailed internal receipts are kept locally; partial-result messages use plain
language. Safe absolute HTTP(S) Markdown links are clickable; raw HTML remains
escaped and images, credential URLs and active URL schemes stay disabled.
