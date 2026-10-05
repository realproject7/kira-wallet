# Continuous showcase film, 2026-10-05

The operator wanted the existing automatic chat video with clearer design.
The manually switched HTML demo in PR 19 misinterpreted that request. This
correction restores automatic motion, removes the question tabs, and appends
all three questions and answers into one conversation.

## Behavior

- A silent 48-second film plays inline and loops. Each 16-second conversation
  types a question, shows Kira researching, reveals its answer and adds three
  result cards. Earlier messages remain above as the conversation scrolls.
- The composer stays inside the bottom of the frame. A shorter movie viewport,
  two-pixel rendering scale and separate mobile compositions preserve readable
  type and spacing. One white result panel aligns token identities, values and
  prices. All three rows and their subtotal fit above the composer. Mobile width responds to viewport height with a readable
  280px floor; short landscape screens retain normal page vertical scrolling.
- No scenario tabs, Pause button, Demo badge or notes appear around the film.
  The existing character-led story and privacy copy stay.
- Token cards identify Balance and Unit price separately, with the token symbol
  beside each quantity. Comparison cards identify Previous price and Current
  price. The numbers are illustrative balances, not model usage counts.
- The film has no pointer target, controls or keyboard stop. Clicking the
  frame leaves automatic playback running. Its wrapper is not focusable.
  The equivalent HTML transcript stays available to assistive readers.
  A recovered source never hides a focused link in a visible fallback.
- Reduced motion, a failed media load or blocked autoplay use the same HTML
  transcript. Offscreen and hidden-document playback pauses. Responsive
  source switching preserves the current playback position.

## Generated assets

All three MP4 files use H.264, 24 fps, no audio and faststart. Each runs exactly
48 seconds. Source and poster URLs carry revision `88ddc35ce6ff`.

| Profile | Viewport width | Pixel dimensions | Logical dimensions | Bytes |
| --- | --- | --- | --- | ---: |
| Desktop | Above 700px | 1040×1140 | 520×570 | 1,627,539 |
| Mobile | 421–700px | 880×1040 | 440×520 | 1,908,035 |
| Compact | Up to 420px | 720×1040 | 360×520 | 1,754,113 |

The new mobile layouts replace the old 320×600 composition that enlarged type
and the entire frame on wider phones. At a 494px viewport, the film body text is
14.9px and the complete demo is 587.6px tall. At 390px, body text is 14.5px.
A single framed panel, 100px result rows and a 92px composer leave space for
all three assets and their subtotal at the end of each answer.

Reproduction on macOS requires Pillow, ffmpeg and the system SFNS font:
`python3 scripts/render-showcase.py`. Renderer assertions check card text
widths, coverage wrapping and composer/footer separation. It reads public
artwork and synthetic examples only. It never reads a portfolio. The JSON
manifest records the synthetic quantities, prices, timing and layouts.
Recorded spot values are not executable sale quotes.

## Verification

Actual Chrome checks for the final layouts covered widths 320, 390, 420, 421,
494, 530, 667 (375px landscape height), 700, 701, 768, 1001 and 1440. No
horizontal page overflow or header overflow occurred. Both the 420/421 and
700/701 breakpoints selected the correct movie and aspect ratio. At 1440×900
the entire demo was 637.8px tall, including its composer. All twelve widths
confirmed a non-focusable wrapper, no movie controls and no pointer target.
Three mobile clicks advanced from 10.233s to 11.524s while playback stayed
active; two desktop clicks also left playback active and visible, with body
focus. No browser console errors were reported.

The preceding browser acceptance decoded all three movies, played automatically
with muted looping and showed successive conversation stages. The latest change
removes the old focus-to-pause behavior that also fired on pointer clicks.
Fallback links remain reachable when reduced motion or media failure exposes
the transcript. Leaving the demo offscreen pauses playback. The preceding correction used a separate local
fixture with a missing desktop movie to verify media-error fallback. Switching
to the valid mobile movie while a market link held focus preserved the visible
transcript and paused video, then recovered when focus left.

The current page produced no browser console errors. Independent read-only
review of the final source and decoded media found no actionable execution
issues. Its stale font-size documentation finding was corrected. Review VM
checks covered normal interaction, responsive source transitions and focused
error/reduced-motion recovery. The preceding README capture review remains
valid because those images and their fixture are unchanged. Reduced-motion behavior was
source-reviewed; no operating-system motion preference was changed for QA.
This evidence does not claim native wallet or model testing for a site change.

Syntax, media metadata, local assets, ARIA references, diff formatting and
public-file privacy validation were checked. Functional wallet code and the
operator-published npm 0.1.2 archive/tag remain unchanged.

## SIGNET pricing

SIGNET on Base is the Mint Club token
`0xDF2B673Ec06d210C8A8Be89441F8de60B5C679c9`, backed by HUNT. The
[official token page](https://mint.club/token/base/SIGNET), checked on 2026-10-05,
showed a curve price of 0.613 HUNT and an approximately $0.061 USD reference.
The film now shows a fictional balance of 650 SIGNET, $0.0610 per token and
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

PR 19 is merged and the repository default branch has the updated README.
This motion correction and the new screenshots are in PR 20. The operator
explicitly authorized immediate website publication without another approval
question. Registry publication remains operator-only, and these site/docs
changes do not require another npm publication. The published npm 0.1.2 bytes
remain immutable.
