# Kira completion and companion proposal

Historical record. The operator subsequently removed the home exit report and
retired the companion proposal. See [the current UI refinement](KIRA_UI_REFINEMENT.md)
for the delivered token preview, question starters and restored showcase.

The operator rejected the first product redesign. The site and app visual base
were restored in `7ffe358`. The `kira-restored-20261004` tag preserves that point;
`kira-design-before-20261004` preserves the earlier release baseline at `cfa9165`.
The restored layout remains the default. Kira Wallet uses one wordmark line.
The published npm installation instructions remain in place.

## Home: what could you recover?

Largest holdings was removed because All tokens already serves that purpose.
The first replacement, price visibility / research coverage / concentration,
was also rejected by the operator. Those three metrics were removed.

The home report now separates displayed portfolio value from recorded exit
proceeds. It shows a full held balance, exact quoted output asset, receive
contract, network, wallet, block and observation time. Saved Mint Club burn
outputs are net of creator royalty and exclude gas. A quote is admitted only
when its balance block matches, its output is finite and nonnegative, and the
recorded backing covers the output. A price refresh does not freshen a burn
quote. Zero return and missing quote remain different states.

The report does not turn a reserve token's spot price into cash proceeds or sum
independent quotes that can share curve backing. DEX liquidity evidence does
not become a full-balance sale quote. Native assets also need a conversion
quote before a target-currency return can be established. The current report
cannot establish immediate execution or a portfolio-wide net cash total.
Further swaps, approvals, token restrictions and gas remain unverified.

“Talk through the exits” prepares a draft. It does not submit a model request,
change context permission, or start research. Validated quotes reach model
context only for an explicitly selected wallet or portfolio scope.

Primary mechanism: [Mint Club burning](https://docs.mint.club/mintburn/burning).

## First wallet and formatted answers

`kira setup` in the next source release opens a wallet-first checklist. Add a
public wallet, review token discovery, follow the explicit research job, then
optionally connect AI. The checklist distinguishes a configured indexer from
an available key. The authenticated readiness endpoint returns aggregate
booleans and provider/mode only. It returns no credentials, reference names
or wallet identities. Tracking does not require an AI connection.

Assistant replies support a bounded Markdown subset, including tables and code.
HTML is escaped. Links and images remain inert text. A genuine Claude reply
rendered a heading, two-column table and bullet with no wallet context.
Codex and Claude generic connection checks also passed during this onboarding
investigation. The npm 0.1.0 package still has its original account-first setup;
these changes need the next operator release.

## A companion with a job

[Lazyweb evidence](https://www.lazyweb.com/agentic-search/828d5e94-1b90-4bef-8934-584ab101e9e0)
informed three choices: task-linked roleplay gestures from Duolingo, a concrete
first step from Finch, and explicit input/receive amounts from Base wallet.
The new proposal uses one shared notebook stage. Selecting an exit, a missing
quote or permissions changes Kira's explanation, pose and report finding together.

Two original transparent full-body poses were generated from the existing Kira
character reference. Heads, hands, notebooks and shoes remain visible. Provenance
is in `docs/character/companion-motion-generation.json`. Motion pauses through a
user control, reduced-motion preference and hidden-page handling. This is a
sample interaction with synthetic data, not a live AI service or audio avatar.

Preview: https://kira-wallet-ccma9rk07-project7s-projects.vercel.app/proposal
The public landing page keeps the restored design. The proposal is a separate
route and preview, so rejecting it does not require another app redesign rollback.
Its local script is permitted only on the proposal document. The landing page
still blocks scripts; all site documents block network connections and forms.
Header configuration follows [Vercel's static configuration](https://vercel.com/docs/project-configuration/vercel-json).

## Verification and operator gates

The required automated suite passes 91 Python tests, 32 Watching/chat cases,
the 5,002-token catalog checks, Markdown boundaries and exit-report checks.
Clean package installation passes with 62 archive members. The public-history
scan and exact reviewed source are recorded before integration and packing. Browser checks cover first
wallet actions, genuine Markdown output, exit-report links,
one-line branding, desktop/mobile layout and companion scene/motion controls.
A 313-character exact positive output was checked at 390 pixels without horizontal
overflow. Readiness retries transient failures and shows unavailable state separately
from an unconfigured indexer. Token details use the same validated quote as home.
Public screenshots contain synthetic portfolios or generic no-context text.

The actual MetaMask address-sharing request is prepared in Chrome on the isolated
onboarding workspace at loopback port 8796. Approval, unlock and account changes
require the operator's device action under the existing gate. They have not been
claimed as passed. No real address was registered by this work.

The next package version is 0.1.1. Packing, verification and source integration
are agent work; npm authentication and publication remain operator-only.
No npm publish command was run.

Further full-balance DEX and settlement quoting is tracked in [issue #11](https://github.com/realproject7/kira-wallet/issues/11).
