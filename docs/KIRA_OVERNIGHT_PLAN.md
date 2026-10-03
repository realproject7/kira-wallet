# Kira Wallet overnight execution plan

Status: completed locally on 2026-10-03. The operator requested autonomous execution and later approved the adult webtoon character and live read-only redesign. The development foundation, identity, live theme, concept studio and agent contract research are delivered. Publication remains outside this run. See `KIRA_BUILD_REPORT.md` for evidence and limits.

## Target for one overnight run

Produce a portable, locally testable Kira foundation and, if the foundation is verified, a reviewable identity and interface concept. Use a planning window of six to eight hours, with the final hour reserved for verification and handoff. These are time allocations rather than delivery estimates.

The priority order is P0 portability and configuration, P0 verification, P1 identity and design, then P2 integration research. A failed P0 check takes priority over starting another milestone. The current wallet viewer remains the usable reference throughout the run.

## Execution conditions

The execution host must stay available throughout the run. Local execution cannot be relied on while the computer is asleep. Use an awake local host, or an explicitly selected remote environment with the necessary project access. This plan does not change power settings, transfer credentials, start an automation or select a remote host.

Use one implementer and serialize writers to registry, cache and configuration files. Inspect the applicable repository rules and Git state before implementation. Keep changes on a dedicated development branch; never push directly to main. If no Git repository exists, prepare a private local development repository with explicit exclusions for operator data before staging anything. Follow the independent review requirements that apply to that repository and runtime.

## Ordered work

| Priority and allocation | Work | Morning evidence |
| --- | --- | --- |
| P0: first 30 minutes | Record the baseline, map runtime dependencies, identify configuration reads and prepare the development branch and data exclusions. | Baseline verification results, dependency inventory and a scoped change record. |
| P0: next 2 to 3 hours | Package the existing Python and Node engine. Replace the external `h402-web` viem import with a declared dependency. Introduce a user data directory, explicit configuration paths and proposed `kira start` and `kira doctor` entry points. | Installation in a fresh directory works without the operator's RPC file or external node_modules. A sanitized sample viewer starts and stops cleanly. |
| P0: next 1 to 2 hours | Add public/custom RPC resolution, separate discovery settings, connection checks, explicit fallback policy and redacted diagnostics. Preserve the existing configuration through an explicit compatibility import. | Public-only, custom and missing-key scenarios produce usable or limited status. Wrong-chain endpoints are rejected. Missing indexer coverage stays incomplete. |
| P1: only after P0 passes | Write Kira's identity, voice and state rules. Produce three original character concepts and a provisional preferred direction. Prepare a small, isolated interface prototype using sanitized fixtures. | Identity document, character comparison sheet, state matrix and desktop/mobile prototype screenshots. The prototype is labeled as a demo wherever it simulates job states. |
| P2: only with remaining time | Inspect the current official agent-session integration contracts and outline a tool adapter. Resolve authentication and installation uncertainties in a small technical note. | Adapter contract, supported authentication assumptions, unresolved questions and the next implementation ticket. |
| Final hour | Run required checks, inspect artifacts, write the morning report and a resumption checkpoint. | Exact commands and results, changed files, screenshots, limitations, reproducible launch instructions and the first productive next action. |

## Portability and RPC acceptance

The current sources hardcode the operator RPC file and import viem from another local project. Remove these dependencies from the supported product path. Keep runtime consolidation and a broad language rewrite outside this first run. Establish actual supported versions from installation tests. Start with macOS verification; do not claim Linux or Windows support without checks. In particular, the current use of `fcntl` requires an explicit portability decision.

Non-secret configuration should name networks, modes and credential references. Secrets belong in explicit environment overrides or private local storage. An optional compatibility import must never become a required default. Test absent files, malformed settings, URLs with embedded keys and redaction of provider errors. Browser state and diagnostic exports must contain no credentialed endpoints or headers.

Public RPC and indexed discovery are separate capabilities. Public mode should read native balances, known assets and reachable Mint Club registries without claiming complete general ERC20 discovery. A missing Alchemy key must not crash public mode. Custom mode should use the user's configured endpoints; public fallback is an explicit preference.

Use fixture-based tests for rate limits, timeouts, wrong chain IDs, repeated pagination, partial provider responses and unavailable historical state. For live probes, start with a hard cap of 200 JSON-RPC method calls across the run, including retries and batch elements. Sample representative reads on Ethereum, Base and Blast before expanding probes. Stop an endpoint after repeated rate-limit or transport failures and report its limitation. This cap limits requests, not a guaranteed monetary charge. Do not conduct full registry scans, broad historical log scans or whole-wallet reanalysis during this foundation run.

## Kira concept scope

Use the existing product specification and selected design evidence. Kira should be warm, curious and careful with incomplete evidence. The initial rounded star and two alternatives were compared, then replaced by the operator-approved adult webtoon researcher. Apply the Toony character workflow: fixed identity anchors, verbatim lockstrings, scene palettes, stored generation inputs and visible quality review. Reference Toony without modifying it or copying its source or artwork. Preserve earlier concepts for comparison.

The prototype should show Home, token investigation and analysis progress or partial completion. Keep one compact breadcrumb, readable financial figures and the existing token identity rules. Use a desktop assistant panel and a mobile assistant view. Show sample data and simulated states explicitly. Actual analysis progress must eventually come from jobs rather than a decorative timer.

Keep the live viewer intact. Update on 2026-10-03: the operator approved the adult webtoon direction and requested the working web app to match. The read-only live viewer redesign is included in this run. Browser write operations and authenticated agent chat remain later milestones. A concept prototype is not evidence that these features work.

## Verification and completion

Run the checks required by AGENTS.md and README.md, plus meaningful tests for configuration, redaction and installation. Use a fresh temporary installation with sanitized fixtures and no operator configuration. Check the CLI launch lifecycle and exit codes. For any interface changes or prototype, inspect desktop and narrow mobile layouts, keyboard navigation and actual screenshots.

Preserve the two registered wallets, their exact tags, analysis snapshots and latest pointers. Do not publish their data as demo content. No new wallet, holdings refresh or price refresh is part of this run unless the operator adds it to the scope.

Do not publish packages, push a public repository, deploy kirawallet.xyz, perform transactions, change account permissions or send external messages. Prepare reviewable local artifacts. Registry publication remains operator-only.

If installation or configuration is still failing near the end of the window, repair or checkpoint that work and omit P1/P2. A login that requires the operator is an integration boundary; continue independent core work. Record every unfinished item without marking it complete. Repeated failures require bounded diagnosis, not an endless retry loop.

The morning handoff should state what works, what failed, what remains unknown and how to reproduce the result. Include a diff or patch, exact verification results, artifact links and the next ticket. Create a Session Glue checkpoint using its applicable skill if the operator requests a resumable overnight implementation run.
