# Native HTML showcase animation, 2026-10-05

The showcase now renders the conversation as browser text, HTML and CSS.
Encoded video cannot preserve small text at every responsive size. Native
layout removes that compression and scaling step without adding a video or
React runtime. The three examples still play automatically in one conversation.

## Behavior

A 48-second loop gives each example 16 seconds. The question types into the
composer, Kira researches, the answer types, and result rows appear in order.
Earlier messages stay above as the conversation scrolls. The composer stays
at the bottom of the frame. There are no scenario tabs, Pause button, Demo
badge or click-to-pause behavior.

The animated copy has no interactive targets and is hidden from assistive
technology. The original complete HTML transcript is the single content
source. Screen readers can read it without repeated live announcements.
Reduced motion or JavaScript being unavailable exposes the readable transcript
with its source links. A focused fallback link is never hidden on recovery.

The animation pauses while offscreen or while the document is hidden. It
resumes at the same elapsed time. Responsive resizing reflows the same HTML
without choosing a new media source or restarting the conversation. CSS uses
native font sizes and actual scrolling, with no scaled canvas or video texture.
Only small opacity reveals and research dots use CSS animation.

## Layout

| Viewport | Maximum frame width | Conversation height | Result panel height |
| --- | --- | --- | --- |
| Above 700px | 520px | 570px | 392–394px |
| 421–700px | 440px | 520px | 392–394px |
| Up to 420px | 360px | 520px | 392–394px |

The available result viewport is 450px on desktop and 402px on mobile.
Token names and values use 14px text. Balances use 12px, market references
11px, and subordinate labels 10px. All three rows and the subtotal fit above
the composer even at a 320px page width. Normal page scrolling handles short
screens rather than shrinking the text to fit the screen height.

`site/index.html` owns the example contents. `site/demo.js` clones that
transcript into a pointer-free animated stream and schedules its phases.
`site/site.css` owns both responsive layouts and the readable fallback.
The older renderer and MP4 exports remain available as offline exports;
the public page no longer loads or plays them. Their scenario manifest is
historical export provenance, not the animation's content source.

## Verification

`python3 scripts/showcase-preview.py --port 8807 --frame 44.5` serves the
public site with production security headers and freezes the QA clock at the
last example's complete results. This is a test fixture, not the live page.
The `--reduced-motion` and `--no-js` modes exercise the readable fallback
without changing the operator's OS settings or accessing a wallet.

Actual Chrome geometry checks covered 320, 390, 494, 700, 701 and 1440px.
All three result panels fit the viewport, with zero horizontal page overflow.
The last subtotal has at least 6px of space before the viewport edge. The
production CSP permits the animation; the page contains no video or canvas.
The reduced-motion preview stops playback and preserves keyboard access to
market links. The JavaScript-free preview renders the full transcript.

Live autoplay, click behavior, continuous scrolling and looping were checked
separately from the frozen geometry fixture. Syntax, local asset references,
ARIA IDs, diff formatting and the public-file privacy guard were also checked.
This follow-up has implementer verification. The preceding independent review
covered the older movie implementation and is not a review of this rewrite.
No operator wallet, model provider or key vault was used for site QA.

## SIGNET pricing

SIGNET on Base is the Mint Club token
`0xDF2B673Ec06d210C8A8Be89441F8de60B5C679c9`, backed by HUNT. The
[official token page](https://mint.club/token/base/SIGNET), checked on 2026-10-05,
showed a curve price of 0.613 HUNT and an approximately $0.061 USD reference.
The animation shows a fictional balance of 650 SIGNET, $0.0610 per token and
$39.65 spot value, alongside its HUNT curve price. The first subtotal is $272.65.
These rounded references do not claim an executable burn output or a live price
feed. The curve relationship and source are recorded in the scenario manifest.

## README captures

The two screenshots now use separate conversations relevant to each main view.
Overview explains the $14,253.50 portfolio, network allocation and missing
coverage. USDC Markets explains the 4,400 USDC balance, its two wallets and four
recorded pools, with two initially visible. Pool liquidity remains separate
from wallet value and executable proceeds.

`python3 scripts/readme-preview.py --port 8806` reproduces a disposable local
capture workspace with fictional public wallet identities and handwritten
answers. The unchanged production viewer and snapshot projection render the
images. The fixture cannot queue research, invoke a model CLI or create keys.
No operator portfolio or chat is read. Chrome captures are 1728×1120; their
provenance and hashes are in `docs/screenshots/kira-readme-sources.json`.
README uses repository-relative image paths so each branch shows its own
screenshots. These captures demonstrate the UI, not live model accuracy.

Design evidence for balance and price separation:
[Coinbase and Gemini portfolio screens](https://www.lazyweb.com/agentic-search/9bde7e00-d871-4aee-ac36-77aeffd6df08).

## Publication boundaries

PR 19 is merged. This animation and the distinct README screenshots remain
in PR 20 until authorized merge. The operator explicitly authorized immediate
showcase publication without another approval question. The HTML animation
itself needs no npm release. The separately requested CLI startup change has
its own package release boundary. Published npm 0.1.2 bytes and its tag remain
immutable, and registry publication remains operator-only.
