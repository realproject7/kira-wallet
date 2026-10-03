# Kira Wallet implementation plan

This plan turns the existing research viewer into the local Kira Wallet application defined in [the product specification](KIRA_PRODUCT_SPEC.md). Deliver the requested viewer improvements first, then build portable configuration, Kira's identity and character, the redesigned workspace and optional agent management. Later milestones describe planned work, not completed features.

The [overnight execution plan](KIRA_OVERNIGHT_PLAN.md) defines a bounded first run, ordered priorities, completion evidence and execution conditions. The operator authorized the overnight run on 2026-10-03, then approved the adult webtoon character and the live read-only viewer redesign. The portable development build, approved base portrait, working viewer theme and isolated concept studio are delivered locally. Publication is not authorized.

## Completed viewer foundation

Chain artwork now follows Mint Club's live asset mapping, with fallback for missing artwork. Token pages show cross-wallet balances, known value, recorded prices, source links, shared curve reserves and recorded burn quotes. Network pages show aggregate value, per-wallet coverage and allocations, and searchable combined tokens. Hash routes support direct links, reload and browser navigation. Existing snapshots and registry entries remain the data source.

Acceptance requires valuation and aggregation tests, Node syntax validation, responsive checks and meaningful browser navigation. Current verification has passed 18 viewer tests and 14 pipeline, pricing and configuration tests, Node checks and a fresh package installation. The viewer remains read-only; this milestone does not create the later product's write API or agent session.

## Delivery sequence

| Milestone | Concrete work | Completion evidence | Dependency |
| --- | --- | --- | --- |
| Portable engine and provider settings | Remove local project dependency paths; package runtime requirements; add user configuration, public/custom RPC, discovery adapters, credential references and capability checks. | A clean installation works without operator files. Public-only and custom modes both produce honest coverage. Wrong-chain and limited endpoints fail predictably. | Viewer foundation |
| Kira identity and character | Write role and voice rules; compare three original visual concepts; choose a character; produce master art, small avatar, key poses and state mapping. | Character remains recognizable at small sizes. Every displayed state maps to a real system event. Identity examples explain uncertainty and recovery clearly. | Product specification |
| Kira design system and workspace | Create design tokens and components; redesign Home, wallet, token and network pages; add onboarding, progress, empty/error states and the contextual assistant surface. | Desktop and mobile flows are readable, keyboard usable and coherent. Financial figures retain hierarchy. Reduced-motion mode is complete. | Provider UX decisions and character |
| Local jobs and direct controls | Implement authenticated local operations for add wallet, tags, full refresh, price refresh, resume, cancel and snapshot read/compare. Stream real progress and retain results across restarts. | Buttons work with no model connected. Duplicate requests are idempotent. Interrupted jobs resume safely. Failed jobs preserve the last good snapshot. | Portable engine and core workspace |
| Kira agent session | Add Codex app-server, supported authentication, identity instructions, scoped research tools, chat events, reconnect and conversation persistence. | Chat operates on the selected entity, cites recorded evidence and cannot alter financial facts. Model disconnection does not disable direct controls. Reconnect does not duplicate work. | Typed operations and job service |
| Research improvements and pilot | Separate balance/price/coverage changes; improve unsupported price paths; add and validate selected wallet-sized DEX quotes; compare workflows with external users. | Reproducible cases demonstrate useful findings. Quote freshness and limitations are visible. Pilot results determine the launch scope. | Usable local beta |
| Open-source launch preparation | Add an empty default registry, opt-in demo fixtures, documentation, adapter guide, contribution policy, license, packaged release candidate and kirawallet.xyz demo assets. | A release candidate passes clean-machine installation and required checks. No operator dataset or secret is included. | Pilot findings and completed launch scope |

Keep analysis engine and UI changes within one coherent product repository. Split review units only when a dependency or rollback boundary benefits from it. Registry publication remains operator-only. Preparing a release candidate does not itself publish a package, create a public repository or deploy the website.

## RPC research tasks

First inventory the current provider-specific discovery calls and contract reads. Identify what can run with standard RPC, what needs an indexer and what requires a historic log range. Produce a capability matrix per current Mint Club network instead of equating a configured URL with full discovery.

Benchmark a representative small and large registry scan using reviewed public endpoints and the existing custom configuration. Measure successful batches, timeouts, rate limits, total calls, resume behavior and time to first usable result. Do not run every large scan automatically during onboarding. Check chain identity and supported reads with a bounded probe first.

Prototype ordered failover, pinned blocks, adaptive batching and backoff. Simulate 429s, timeouts, unavailable archive state, partial provider errors, invalid pagination and wrong chain IDs. Confirm that all failure modes preserve a useful partial result and keep unsupported areas unknown.

Design separate RPC and discovery controls. Public setup should work without a key, with its coverage limitation visible. Custom setup should support multiple named endpoints and explicit fallback preferences. Indexed discovery should accept the user's own provider credential. Produce a redacted diagnostic export for support.

## Identity and design deliverables

The operator selected an adult webtoon researcher with espresso hair, an ivory shirt, a charcoal blazer and a lavender notebook. The base portrait, provenance records, identity rules and state matrix are delivered. The star and clay alternatives remain comparison concepts. Additional consistent expressions and poses remain a later asset milestone.

Prepare end-to-end prototypes for first launch, add wallet, partial analysis, refresh, token investigation, network exploration, RPC recovery and a contextual chat request. Prototype both a desktop assistant panel and a mobile assistant view. Keep actions visible as buttons so users do not need to learn prompting for routine tasks.

Kira's progress should name the current stage and show genuine counts when available. Completion may be a quiet acknowledgment. Partial coverage and errors should explain the missing scope and offer retry or connection settings. Preserve useful results on screen throughout recovery.

## Verification and release criteria

Financial checks cover exact balances, chain/contract identity, reserve price paths, unknown values, testnet exclusion, backing overlap, shared tokens across wallets and snapshot differences. Adapter checks cover capability detection, rate limits, pagination and credentials redaction. Service checks cover loopback binding, session/origin protection, idempotency, cancellations and restart recovery.

Browser checks cover Home to wallet to token/network navigation, direct routes, Back/Forward, file-update continuity, filtering and search, offline/missing images, assistant context, keyboard focus, narrow layouts and reduced motion. Validate actual job completion rather than a success message alone.

Before broad launch, run the external pilot described in the specification. Record install failures and useful findings alongside repeat use. Choose subsequent protocol and model support from those results. Calendar estimates should follow the RPC benchmark and agent authentication prototype because both can change the work needed.

## Next implementation action

The portable engine and provider settings are verified as a macOS development build. Home, wallet, token and network views use the approved Kira theme. The versioned [job contract](JOB_CONTRACT.md) and [read-only tool adapter](AGENT_TOOLS.md) are implemented and verified with synthetic cases. The durable job service, protected local browser controls, first-wallet form, connection references and saved analysis comparison are delivered in development build 0.1.0-dev.2. Connected chat and release preparation remain gated. The existing CLI and read-only viewer stay usable throughout that work.

## Account setup boundary

The autonomous continuation delivered local jobs, direct controls, saved
analysis comparison and Kira brand assets. The next connected-chat milestone
requires the operator to choose and complete account/authentication setup and
approve selected portfolio disclosure. No account login, model turn or external
publication was performed. Independent security/release review and an external
pilot remain outstanding. See [the continuation report](KIRA_JOBS_BUILD_REPORT.md).
