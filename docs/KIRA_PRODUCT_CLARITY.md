# Kira product clarity and onboarding audit

2026-10-04. Baseline source: `cfa9165`. Registry release: `kira-wallet@0.1.0`.

## Product copy

Headline: **Your wallets, together. Your own AI.**

Description: **Track assets across chains. Bring your own AI to understand them.
Keep your portfolio on your computer.**

Three concrete benefits guide the page: find assets on supported EVM chains,
connect the user's installed Codex or Claude Code, and keep the portfolio in a
local app. Broad ERC20 discovery depends on a configured, working indexer.
The page does not promise all chains or tokens, provider-free AI, or automatic
trading. Kira is read only. AI messages and approved context reach the chosen
model service; research queries reach configured RPC/indexer providers.

## Published package acceptance

The operator published 0.1.0. A fresh download from the registry matched the
prepared archive SHA-256:
`45c33d4e37bd45145c53afd05a234caa746146a47e2f729fec1087d841506858`.
It contained 58 archive members. Installation used a disposable global prefix
and empty data directory, with no imported portfolio or provider credentials.
Existing native CLI subscriptions were used for generic response checks only.

- Registry installation, `doctor`, `setup --no-open` and loopback viewer startup passed.
- Browser setup detected Codex 0.158.0 and Claude Code 2.1.284.
- Both CLIs returned a real generic response in the published package's connection check.
- Codex setup saved and a generic first conversation returned a real answer.
- Claude setup also saved. Automatic wallet context and Kira retention remained off.
- These tests sent no wallet holdings and did not perform wallet research or signing.
- Browser extension navigation was rejected by the existing cross-site guard;
  normal direct address-bar navigation opened setup. This is an automation
  transport limitation, not evidence of a normal onboarding failure.

The source install check also passed after the visual changes, with 59 archive
members including `clarity.css`. This does not change the already published
0.1.0 package. A later registry release remains operator-only.

## Findings and tickets

[#5](https://github.com/realproject7/kira-wallet/issues/5) records stale installation copy,
[#6](https://github.com/realproject7/kira-wallet/issues/6) covers no-context chat,
[#7](https://github.com/realproject7/kira-wallet/issues/7) tracks guided first-wallet
and discovery setup, and [#8](https://github.com/realproject7/kira-wallet/issues/8)
covers character clipping and scene copy.
[#9](https://github.com/realproject7/kira-wallet/issues/9) records literal Markdown
in real assistant answers and requests a safe, readable renderer.
Installation copy, no-context settings entry and artwork presentation are addressed
by this PR. Guided wallet/indexer onboarding and chat Markdown remain follow-up work.
Native extension approval, locking and account switching were not exercised.
No new operator address was supplied, so the audit did not repeat live research.

## Design evidence and decisions

[Selected Lazyweb references](https://www.lazyweb.com/agentic-search/02537558-e51b-4ec3-8ac7-e47b3898f5d0)
include Coinbase's direct portfolio benefits, Apple's simple product hierarchy,
and Raycast's explicit account/AI onboarding. The direct public pages checked
were [Coinbase DEX](https://www.coinbase.com/dex) and
[Apple financing](https://www.apple.com/shop/browse/financing).
This is design interpretation, not a claim to reproduce their exact fonts.

Use one local system sans stack, regular body spacing and 1.5–1.6 body line
height. Headlines use restrained negative tracking and 600 weight. The site
uses plain dark CTAs and neutral portfolio surfaces. Violet identifies Kira.
Decorative eyebrows, italic scene captions, edition labels and generic
perspective/clarity slogans have been removed from the main surfaces.
Existing line icons use an 18–20px canvas and a 1.75 stroke with rounded joins.

Kira is visible beside the task and beside the transcript. Contain sizing,
static placement and safe padding preserve the entire original bust artwork.
Research, explanation, saved review and missing-coverage poses describe actual
state. General chat explicitly says no wallet context is shared. The companion
never implies that viewing a wallet authorizes AI disclosure. With registered
wallets, Choose wallet context opens the existing verified permissions flow.
Recorded summaries retain their own label, separate from model conversation.
On mobile the site introduces Kira before the sample portfolio.

No new artwork was generated. The site's three additional poses are exact
copies of the original app assets; generation provenance is in
[workspace-generation.json](character/workspace-generation.json).

## Validation and screenshots

Synthetic portfolio screenshots and a generic no-context conversation are the
only visual evidence. No operator holdings, names, paths or private jobs appear.
Required `npm test`, clean install, public-boundary scan and responsive browser
checks are recorded with the PR. Browser checks cover the site installation
anchor, mobile layout, Kira pane, coverage shortcut, and connected chat state.
The required suite passed 83 Python tests, 32 Watching/chat cases and the
5002-token catalog checks. A real Claude response also passed against the
updated source with no wallet context shared. Independent source and evidence
review found no functional or privacy regressions. Its screenshot refresh and
whitespace corrections were completed before the commit.

- [Previous public site](screenshots/kira-site-before-20261004.png)
- [Site desktop](screenshots/kira-site-clarity-desktop.png)
- [Site mobile](screenshots/kira-site-clarity-mobile.png)
- [App mobile](screenshots/kira-app-clarity-mobile.png)
- [Connected chat, no wallet context](screenshots/kira-chat-clarity-desktop.png)

## Applied result

The reviewed design is live at [kirawallet.app](https://kirawallet.app).
Reviewed design deployment: `dpl_EDxXu898KrcLXvnUrS8M2QwEhaaF`.
The site setup guide is pinned to the updated public source so it remains
accurate while [PR #10](https://github.com/realproject7/kira-wallet/pull/10)
awaits source integration. The guide-link correction is deployed separately.

The existing local viewer was restarted with the reviewed source at port 8765.
All 1,029 guarded runtime files were byte-identical. Existing model settings
remained identical, with context scope none and Kira history off. Only lifecycle
metadata and the private viewer log changed. No active chat or research job was
interrupted. Temporary onboarding/demo viewers were stopped after verification.

## Rollback

The local tag `kira-design-before-20261004` preserves `cfa9165` before editing.
The public Git baseline is also available at that commit. Portfolio runtime
files are outside these commands. Keep the published installation correction
when reverting visual design.

To revert just the app interface:

```sh
git restore --source=cfa9165 -- viewer/static/index.html viewer/static/app.js viewer/static/agent.js viewer/static/workspace.js
```

The restored HTML does not load `clarity.css`; its server allowlist entry is
harmless. The extra static CSS can stay. Native account settings and portfolio
files are not changed. Restore those four files from this PR's commit to return
to this design.

For the site, restore the two baseline files, then retain the installation and
release corrections before deployment:

```sh
git restore --source=cfa9165 -- site/index.html site/site.css
python3 scripts/retain-published-install.py
```

That helper changes only the original pre-release npm instructions and labels.
It does not deploy. Run the site-only Vercel deployment after reviewing the
restored source. A Vercel deployment rollback alone restores the stale
pre-publication installation text too, so prefer this source-based rollback.
