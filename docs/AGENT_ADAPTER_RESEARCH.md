# Local agent adapter research

Checked on 2026-10-03 against the installed `codex-cli 0.158.0`.
This is a contract review. No agent process, login, account request or model
turn was started. Authentication and subscription eligibility remain untested.

## Inspected contract

The local CLI provides `codex app-server`, with stdio as its default transport.
It can generate JSON Schema with `generate-json-schema --out <directory>`.
The experimental schema is a separate opt-in generation.

| Operation | Contract observed | Proposed Kira use |
| --- | --- | --- |
| `initialize`, then `initialized` | Client identity and capabilities | Versioned adapter handshake |
| `thread/start` | Instructions, working directory, sandbox and approval policy | Start a Kira research conversation with explicit permissions |
| `thread/resume` | Resume a saved thread | Recover conversation after a disconnect |
| `turn/start` | Required thread ID and input | Send an entity-scoped user request |
| `turn/interrupt` | Turn cancellation | Stop the model turn without deleting an analysis result |
| `item/agentMessage/delta`, `turn/completed` | Message and completion events | Stream chat with a recorded terminal state |
| `account/read`, `account/rateLimits/read` | Read-only account and limits requests | Explain connection availability after user-authorized setup |
| `account/login/start` | Managed ChatGPT and device-code variants | Use the official login flow, subject to current product eligibility |

The generated login schema labels externally supplied `chatgptAuthTokens`
as internal-only and unstable. Kira should not implement that variant or copy
desktop authentication files. A schema variant alone does not establish
permission to use a subscription in a third-party product.

Dynamic tools appear in the experimental `thread/start` schema, not the
default schema. `item/tool/call` carries thread, turn, call ID, tool name and
arguments. An adapter must pin and validate a compatible protocol version.
The experimental raw event option is explicitly internal-only; avoid it.
The first supported prototype can use a separately configured local MCP
adapter if the chosen release does not provide a stable dynamic tool path.

## Engine contract before chat

Build a persisted job service first. CLI commands, future browser buttons and
the agent should call the same typed operations:

| Operation | Input | Durable result |
| --- | --- | --- |
| `wallet.add` | Address, exact tag, idempotency key | Registry identity and analysis job ID |
| `wallet.refresh` | Registry identity, idempotency key | New immutable snapshot and job ID |
| `prices.refresh` | Registry identity, idempotency key | Timestamped price overlay and job ID |
| `job.resume` / `job.cancel` | Job ID | Recorded state and preserved last good result |
| `snapshot.read` | Snapshot ID | Structured facts, timestamps, coverage and source links |

Each job needs recorded stages, endpoint identity without secrets, pinned
blocks, progress counts when known, partial errors and atomic publication.
Model turn interruption and engine job cancellation are distinct operations.
Reconnect must use persisted job IDs rather than repeat a wallet mutation.

The engine owns financial facts. Kira may explain structured evidence, but
cannot write invented balances, prices or completeness. Routine controls must
work while the model is disconnected. Read-only tools should be the first
agent milestone. Local write routes require explicit origin/session protection
before browser controls are added.

## Next implementation ticket

Design the versioned job envelope and operation schemas with synthetic fixture
cases for duplicate submission, interruption, restart and partial completion.
Review that contract before implementing browser writes or connecting a model.
Keep protocol experiments separate from the current read-only viewer.

## Continuation result

The version 1 [job envelope](JOB_CONTRACT.md), durable worker and local controls
are implemented in 0.1.0-dev.2. Synthetic tests cover duplicate submission,
process interruption, engine descendants, crash receipts and partial results.
The [read-only stdio adapter](AGENT_TOOLS.md) exposes recorded facts and saved
jobs without starting research. Its local protocol transcript is verified.
Live Codex/MCP-client attachment, account eligibility and connected chat remain
unverified and require the operator account setup gate.
