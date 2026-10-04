# Kira UI refinement

The operator removed the home recovery report and asked for a simple preview of
All tokens, editable question starters, and polish of the restored showcase.
This supersedes the companion proposal and recovery-home work in PR #10.

## Home and conversation

Home shows at most five mainnet tokens in the default All tokens value order.
Both views share the same catalog filter and row renderer. View all tokens opens
the catalog with its default filters and first page. Token links still open the
network-and-contract detail. Unpriced balances stay unknown; testnets are excluded.
The recovery report, exit actions and exit-specific home briefing are removed.
Existing validated evidence remains in token details.

Three question starters cover liquidity-pool swaps over $100, missing prices and
coverage gaps. Clicking a starter fills an editable draft. It sends no model
request, starts no research, and changes no context permission. A typed draft is
never overwritten. A starter added during a pending send survives its receipt.
The liquidity question asks for evidence and unknowns, not an assumed sellability
result. The existing native CLI and context gates still apply.

## Sidebar and showcase

The old full-page image made the fixed sidebar appear to end halfway down the
document. In a live browser its top remained at 0 and bottom at the 941-pixel
viewport edge before and after scrolling. No runtime sidebar clipping defect was
reproduced. Desktop evidence now uses viewport captures. The mobile sidebar is a
normal full-width header.

The showcase keeps its original hero, portfolio preview, character and installation
sections. Typography, spacing and one-line branding are refined. Decorative
taglines are removed. The portfolio and small chat cards no longer overlap at the
tested desktop and mobile widths. The character proposal documents and script are
retired; /proposal and /proposal.html redirect to the restored landing page.
All site paths again have a script-free, connection-free static CSP.

Reference evidence: [Coinbase portfolio and Copilot question starters](https://www.lazyweb.com/agentic-search/e856b0bd-5a3d-4de3-98c0-7ef07b54b79d).

## Verification

- `npm test`: 91 Python tests, 34 Watching/chat cases, RPC, 5,002-token catalog,
  safe Markdown and readiness recovery pass.
- Clean synthetic package installation and lifecycle pass with 62 archive members.
- Browser checks compare the five home rows to the first five of seven All tokens
  rows. A large testnet holding is excluded; an unpriced token remains unknown.
- A real question-button click at 390 pixels fills the draft, leaves zero messages,
  keeps no wallet context, and leaves the composer fully inside its panel.
- Desktop and 390-pixel mobile layout, sidebar scrolling, card overlap and the
  retired proposal redirect are checked with CUA.

Screenshots in `docs/screenshots/kira-ui-*.png` contain synthetic portfolios only.
The original generated character files remain preserved. The prior integrated
source at `d9adfe4` remains the rollback baseline. No npm publication or actual
MetaMask device acceptance is performed by this refinement.
