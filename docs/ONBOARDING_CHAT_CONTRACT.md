# Native CLI onboarding and conversation

Kira connects the user's installed, unmodified Codex or Claude Code CLI. It does not collect account passwords, copy authentication, run an OAuth proxy, or add a hosted portfolio service. Installation and login happen through the vendor's CLI. A generic response test verifies the selected model before setup is saved. Subscription access and limits remain the vendor's responsibility.

The setup flow separates account readiness, model choice, context permission, and confirmation. The conversation composer remains visible. It shows the connected CLI, automatic context scope, response state, cancellation, and a new conversation action. Enter sends; Shift+Enter adds a line; composition events never send.

`kira setup` opens the existing Account, Permissions and Ready modal directly
after the local session and workspace are available. Opening setup does not run
a model response check, save permissions or start wallet research. Existing
settings are loaded when setup is reopened. Closing the modal consumes that
page's setup request, so background polling does not reopen it. Ordinary
`kira start` keeps the normal workspace entry behavior.

The 0.1.5 selector defaults to Use default model. Codex uses a bounded stdio
app-server handshake and model/list request; it never starts a thread or turn.
The subprocess has an eight-second metadata deadline and 256 KB output bound.
Metadata failures leave the default and Advanced identifier entry available.
Only installed supported CLI versions are queried. Claude uses its documented
Sonnet, Opus and Haiku aliases. Every chosen model still requires a deliberate
generic response test. Vendor account and managed policies may restrict access.
Workspace settings reuses this modal for both providers and all permissions.
Fresh setup preselects local history; existing false values remain false.
History permits reopening chats, without extending model memory or scope.
No wallet context permits general chat and manual wallet management while
wallet context and research tools remain unavailable. Any effective model or
permission change starts a fresh conversation.

Automatic context is none, one explicitly selected registered wallet, or the whole recorded portfolio. An allowlisted projection preserves exact balances, contract and chain identities, timestamps, unknown values, and coverage gaps. It excludes credentials, RPC endpoints, paths, raw errors, jobs, and provider payloads. User-entered text is also sent to the selected provider. Scope, wallet, provider, or model changes start a new conversation and never replay old messages. Only a bounded current conversation is replayed.

Approved wallet context can include validated historical full-balance Mint Club
burn outputs, with reserve contract, chain, block and timestamp. The context
explains that royalty is included, gas is excluded, and independent quotes must
not be summed or converted at spot prices into cash proceeds. No-context chat
receives none of these wallet facts.

Kira uses fixed executable argv, stdin for prompts, a private empty working directory, bounded output, a timeout, and process-group cancellation. Codex ignores user config and rules, uses read-only sandboxing and ephemeral sessions, and disables shell, apps, browser, computer, image, multi-agent, hooks, memories, goals and skill discovery features. The supported Codex adapter is gated to the verified 0.158 series. A local synthetic Responses fixture verified the outgoing catalog has no shell, file, network, MCP, app, or skill tools. Claude Code 2.1.259 through 2.1.x uses restricted and safe modes, no built-in tools, empty strict MCP configuration, no Chrome, no permission prompts and no session persistence. Unsupported versions fail closed.

Native CLI and administrator policy are a separate trust boundary. These settings are invocation controls, not an OS container. Claude managed policy can still apply. Setup requires explicit acknowledgement of the native CLI trust boundary. Kira-local retention controls Kira's conversation files only; vendor and managed CLI data policies are separate. History-off conversations stay in memory and the browser draft is not persisted. Previous saved conversations are preserved but never automatically attached to a new scope.

Chat cannot sign, trade, run arbitrary commands or change provider settings. With the separate wallet research capability enabled, a bounded host loop validates typed tool requests from the native response. It reads allowlisted current and historical facts inside the approved wallet scope and admits holdings or price jobs through the existing durable API. Legacy settings default this new capability off. New setup recommends portfolio context and research tools. No-context chat receives no wallet tools. Epoch, cancellation and configuration are rechecked under the store lock before job admission. Duplicate refreshes within a turn reuse their job. Queued or running work is never a completed publication. Research already admitted persists in Activity after chat cancellation. The tool loop is limited to eight calls, 150 KB of accumulated tool results, a 400 KB prompt and 420 seconds total. Native shell, arbitrary files, browser and MCP tools remain disabled. Responses and token metadata are untrusted text. Assistant responses use a bounded Markdown subset with escaped HTML, no active links or images, and scrollable tables. Token metadata and user messages remain escaped text.

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

## Chat workspace and sessions

Every desktop route shares a fixed right chat dock and bottom floating input.
The compact header opens new chats, history and a full-screen conversation.
Mobile switches between the portfolio and a full-height conversation.
Kira appears in working messages and above answers. Job stages remain recorded
in Activity and also appear in the chat tray. Unanalysed wallets show a sidebar
spinner and open Activity while their first holdings job is active.

History is capped at 100 memory sessions and reads up to 200 validated local
files. Saving is recommended for fresh setup and remains an editable choice. Memory sessions disappear when the process stops.
A previous session can continue only with exactly the same model and context
configuration. Reading history does not expand model access. Old saved files
remain readable. No missing memory-only conversations are reconstructed.

A guarded upgrade can import the current volatile conversation once through a
private, bounded receipt. Its permissions must equal the existing configuration.
The receipt is consumed only on success. This does not enable history retention.

The Kira system voice is concise, composed and practical. It leads with findings
and preserves evidence, unknown values and signing boundaries. Personality is
prompt guidance; response quality still depends on the selected model.

## 0.1.5 preparation evidence

The combined settings and model-selection tests cover catalog failures, stale
responses, custom identifiers, fresh retention defaults, saved opt-outs,
atomic provider changes, preference preservation, missing keys, cancellation
and ambiguous receipts. Desktop 1440 × 900 and mobile 390 × 844 checks used an
empty disposable workspace. Codex 0.158.0 and Claude Code 2.1.293 completed
native default-model response checks with no wallet data. The provider save
used a synthetic local key reference and made no provider research request.
Real extension approval, personal OWS passphrases and live holdings coverage
are separate operator acceptance. Published 0.1.4 snapshots are not rewritten.
