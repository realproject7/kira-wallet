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

The in-app conversation uses a supported installed Codex or Claude CLI account.
A generic response check is required before saving a selected provider, model,
wallet scope and research permission. It sends no wallet facts. Authentication
stays with the installed CLI. No desktop tokens or authentication files are copied.

With research enabled, a bounded host-mediated loop provides portfolio_read,
wallet_read, token_read, snapshots_list, snapshot_read, snapshots_compare,
job_list, job_read, holdings_refresh and prices_refresh. Every operation is
scoped to registered wallets allowed by the conversation. Historical reads use
normalized financial projections. Unknown values and historical quote times
remain explicit. Native shell, file, browser and MCP execution stay disabled.

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
