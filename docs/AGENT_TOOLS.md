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

## Account connection gate

The browser's Kira notes remain deterministic. Connected chat, OAuth handling
and conversation reconnect are not delivered by this adapter.

Before connecting a Kira-owned model session, the operator must select the
account/authentication route and approve which portfolio facts may reach the
model. The current official ChatGPT-plan app-server guide describes an app-owned
OAuth access token, Responses provider configuration and token renewal. It does
not establish this account's eligibility. Client registration, consent and
login are operator actions. Do not copy desktop authentication files or use the
internal-only external ChatGPT-token schema variant. No billing claim follows
from a tool handshake or model catalog.

After the gate, implement the selected auth route and app-server session driver
with saved thread IDs, terminal turn states, reconnect and interruption. Keep
those states distinct from engine jobs. Pin the installed protocol again and
independently review permissions before connecting real private data.

Sources checked on 2026-10-03:

- [Official Codex app-server guidance](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server)
- [Official Codex MCP guidance](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)
- [MCP stdio transport contract](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)

Local verification uses synthetic portfolios and a stdin transcript only.
It does not verify a live Codex/MCP client connection or model access.
