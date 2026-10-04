# Native CLI onboarding and conversation

Kira connects the user's installed, unmodified Codex or Claude Code CLI. It does not collect account passwords, copy authentication, run an OAuth proxy, or add a hosted portfolio service. Installation and login happen through the vendor's CLI. A generic response test verifies the selected model before setup is saved. Subscription access and limits remain the vendor's responsibility.

The setup flow separates account readiness, model choice, context permission, and confirmation. The conversation composer remains visible. It shows the connected CLI, automatic context scope, response state, cancellation, and a new conversation action. Enter sends; Shift+Enter adds a line; composition events never send.

Automatic context is none, one explicitly selected registered wallet, or the whole recorded portfolio. An allowlisted projection preserves exact balances, contract and chain identities, timestamps, unknown values, and coverage gaps. It excludes credentials, RPC endpoints, paths, raw errors, jobs, and provider payloads. User-entered text is also sent to the selected provider. Scope, wallet, provider, or model changes start a new conversation and never replay old messages. Only a bounded current conversation is replayed.

Approved wallet context can include validated historical full-balance Mint Club
burn outputs, with reserve contract, chain, block and timestamp. The context
explains that royalty is included, gas is excluded, and independent quotes must
not be summed or converted at spot prices into cash proceeds. No-context chat
receives none of these wallet facts.

Kira uses fixed executable argv, stdin for prompts, a private empty working directory, bounded output, a timeout, and process-group cancellation. Codex ignores user config and rules, uses read-only sandboxing and ephemeral sessions, and disables shell, apps, browser, computer, image, multi-agent, hooks, memories, goals and skill discovery features. The supported Codex adapter is gated to the verified 0.158 series. A local synthetic Responses fixture verified the outgoing catalog has no shell, file, network, MCP, app, or skill tools. Claude Code 2.1.259 through 2.1.x uses restricted and safe modes, no built-in tools, empty strict MCP configuration, no Chrome, no permission prompts and no session persistence. Unsupported versions fail closed.

Native CLI and administrator policy are a separate trust boundary. These settings are invocation controls, not an OS container. Claude managed policy can still apply. Setup requires explicit acknowledgement of the native CLI trust boundary. Kira-local retention controls Kira's conversation files only; vendor and managed CLI data policies are separate. History-off conversations stay in memory and the browser draft is not persisted. Previous saved conversations are preserved but never automatically attached to a new scope.

Chat cannot sign, trade, run arbitrary commands, change settings, or automatically start research. Research remains in the existing explicit controls and protected durable job API. Responses and token metadata are untrusted text. Assistant responses use a bounded Markdown subset with escaped HTML, no active links or images, and scrollable tables. Token metadata and user messages remain escaped text.

All agent and chat endpoints require the existing same-origin local session, with bounded requests. Conversation jobs are separate from research jobs. Idempotent requests prevent duplicate sends. Cancellation, reset and configuration changes invalidate late responses. Tests cover disclosure projections, scope history isolation, retention, cancellation races, bounded output, unsupported CLIs, failures, duplicate sends and origin/session protection.

Design evidence: [Lazyweb onboarding and AI conversation references](https://www.lazyweb.com/agentic-search/593c1118-8ec0-46bf-a608-4b100271930e). Granola informs separate permissions and readiness; Raycast informs compact model choice; Copilot informs the composer surface and aligned controls. Kira uses its own typography, artwork and component system.

## Initial 0.1.0 verification evidence

`npm test` passes 83 Python tests, 31 Watching/chat UI and model cases, the
RPC outage checks and the 5,002-token catalog fixture. Clean installation covers
58 package members. Screenshots use a synthetic portfolio and fake model runner;
they are visual evidence, not live provider acceptance. Desktop, short desktop
and 390-pixel mobile views were checked in Chrome. Both supported native CLIs
also completed a separate generic response check without wallet context.

- [Conversation desktop](screenshots/kira-chat-desktop.png)
- [Conversation mobile](screenshots/kira-chat-mobile.png)
- [Account setup](screenshots/kira-onboarding-account.png)
- [Permissions](screenshots/kira-onboarding-permissions.png)

Private live read-only acceptance completed with recorded coverage gaps. Same-address
aliases retain one canonical wallet and one published research run. Repeating the
original request reuses its job. Portfolio identifiers and raw acceptance evidence
stay outside Git and are not included in public reports.

Current candidate verification and operator gates are in [the completion report](https://github.com/realproject7/kira-wallet/blob/codex/kira-release/docs/KIRA_COMPANION_COMPLETION.md).
