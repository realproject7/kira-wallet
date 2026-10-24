# Native HTML workflow simulations

The site illustrates a general agent using Kira's wallet tools alongside its own
analysis, web research and file tools. Both animations use native HTML text and
CSS at actual size. No video, canvas or transform-scaled app frame is used.
Balances, prices and sell-out records are fictional examples. These animations
do not run an agent, request provider data, create files or transfer funds.

## Hero restored from the earlier native version

The hero restores the visual sequence from commit `6daf3d7`: Kira's welcome
illustration, a typed question in the composer, the research illustration, an
answer and sequential token cards. Three 16-second chapters form a 48-second
cycle: overlooked token values, Blast holdings, then saved observation changes.
Completed turns remain above the current one until the full cycle restarts.

The authored transcript in `site/index.html` is the source for the animated
clones. Links in the clones become inert text. The original transcript retains
its links and is available through a native details element. Without JavaScript
it is open and readable. Chapter selection shows a completed chapter; Play
restarts that chapter. Pause freezes text, reveals and scrolling.

## One connected agent/browser conversation

The lower example has four 18-second turns, forming a 72-second cycle:

1. Calculate an indicative subtotal from saved Base sell-out records while
   separating missing quotes and shared liquidity.
2. Follow up on the difference between SIGNET's spot valuation and the saved
   independent full-position exit estimates.
3. Research current Blast-to-Ethereum availability and withdrawal steps.
4. Preserve the requested Blast gas reserve and prepare a sourced plan and CSV.

Every completed turn remains in the scroll container. The next question follows
it, rather than replacing the conversation. There is no repeated generic
"Shared local records" result card. Each turn has its own calculation, source
comparison or file result. A readable transcript includes the external sources.

The adjacent browser pane follows the conversation through Base network,
SIGNET details, Blast network and Blast ETH details. It mirrors the installed
app's hierarchy, palette and controls: wallet sidebar, connection control,
Overview/All tokens/Activity tabs, summary, token table and wallet positions.
The sidebar becomes the compact dark header at narrow container widths. This
is an authored reconstruction with example data, not a recording or working app.
Links to the actual installed 0.2.1 screenshots remain below it.

## Numerical and research boundaries

The lower fixture uses 650 SIGNET in Daily and 325 in Savings. At $0.061 each,
the combined saved spot value is $59.475, displayed as $59.48. Independent
full-position estimates are $37.80 and $18.65: an indicative sum of $56.45,
$3.03 (about 5.1%) below the rounded spot value. Base ETH ($6,804) and USDC
($4,400) have no saved sell-out quote in this fixture and are not included in
the estimate subtotal. Known Base spot value, including SIGNET, is $11,263.48.

The two SIGNET estimates may consume the same pool. The conversation explicitly
states that their arithmetic sum is not a combined executable quote. The app
continues to show estimates by wallet, consistent with `viewer/details.py`.
Gas is excluded. Missing estimates are never displayed as zero. No spot value
is relabeled as sale proceeds.

The Blast example holds 0.035 ETH. The user explicitly asks to reserve 0.003 ETH
for source gas, leaving 0.032 ETH to quote. This is an illustrative user choice,
not an estimated gas requirement or a live transfer recommendation.

Bridge research checked on 2026-10-25 uses [Blast's bridge](https://blast.io/en/bridge),
[official withdrawal instructions](https://docs.blast.io/withdrawals/withdraw-to-ethereum)
and [Across's chain-support documentation](https://exclusive.docs.across.to/chains-and-contracts).
The example catches Blast's wind-down and Across's Blast deprecation. The
official exit indicates approximately one day plus proving and claiming steps.
It does not claim that a third-party route is fastest without a current,
exact-amount quote. Availability, fees and arrival estimates must be checked
again for a real transfer.

## Shared playback and accessible fallbacks

One requestAnimationFrame manager drives both roots with independent elapsed
time. Frame deltas are capped at 100ms and DOM paints occur at most every 50ms.
A root stops while offscreen, manually paused, or showing its transcript. A
hidden document stops both roots. The shared RAF is cancelled when neither can
run, and resumption resets the timestamp baseline.

Animated surfaces are aria-hidden and contain no working inputs or live
announcements. Their separate transcripts remain accessible. Reduced motion
shows completed static chapters and disables Play/Pause. Without JavaScript,
the hero transcript is open, the first lower scene remains visible, and all
lower conversation text and sources can be read in its transcript. Scenario
copy also remains available without scripted tab selection.

Native keyboard chapter and playback controls are provided. Scenario tabs have
Left/Right/Home/End navigation. Both install copy actions retain status messages.
The chat and app content scroll independently. Chat follows the newly revealed
content; app views reset at a new turn and move toward lower content after
11 seconds. At narrow widths the agent pane and browser pane stack, without
shrinking text or a desktop capture.

## Token artwork and typography

Every token row and token-specific result uses the existing contract-identified
local artwork. ETH, USDC, SIGNET, USDB, BLAST, CASHCAT and APE sources and hashes
are recorded in `site/assets/token-artwork-sources.json`. Letter, dollar-sign
and diamond substitutes are not used. The existing ETH image is the established
ETH/WETH artwork documented in that provenance file.

The surrounding page retains the system font hierarchy, restrained tracking
and consistent line heights. The compatibility strip simply explains that a
local Kira installation combines wallet tools with an agent's own abilities.
Local tool access and runtime requirements are explained in the setup section.

## Agent marks

The compatibility strip serves four local SVG assets from
`site/assets/agents/`. All four use the same mark box and name treatment:

| Label | Asset | Official source |
| --- | --- | --- |
| Codex | `openai.svg`, OpenAI Blossom | [Pinned OpenAI Cookbook asset](https://github.com/openai/openai-cookbook/blob/8495326b6f1b7cec94e7f5e393a4045e328a268e/examples/agents_sdk/deployment_manager/frontend/src/openai-logomark.svg) and [OpenAI brand guidance](https://openai.com/brand/) |
| Claude Code | `claude.svg`, Claude Spark in Clay | [Anthropic media kit](https://www.anthropic.com/press-kit) and [trademark guidance](https://www.anthropic.com/legal/trademark-guidelines) |
| Gemini CLI | `gemini.svg`, Gemini sparkle aurora | [Official product asset](https://www.gstatic.com/lamda/images/gemini_sparkle_aurora_33f86dc0c0257da337c63.svg) referenced by [Gemini](https://gemini.google.com/) |
| Grok | `grok.svg`, Grok Logomark Dark | [Official logo archive](https://data.x.ai/logos/SpaceXAI_Grok_Assets.zip) and [xAI brand guidance](https://x.ai/legal/brand-guidelines) |

The Codex label uses the OpenAI symbol rather than claiming a separate Codex
mark. Preserve supplied proportions and colors. The Gemini vendor SVG contains
a self-contained embedded gradient image; this does not rasterize page text or
make an external request. The marks identify hosts or models and do not imply
partnership or endorsement. Adjacent copy explains the requirement for a
terminal-capable host, including custom local tools for a Grok-powered agent.

## Local verification

Run separate loopback previews from the repository root:

```sh
python3 scripts/showcase-preview.py --port 8807 --qa-frames
python3 scripts/showcase-preview.py --port 8808 --reduced-motion
python3 scripts/showcase-preview.py --port 8810 --no-js
```

The preview applies production security headers and no-store caching. It never
loads wallet records. A normal URL uses the real clock. QA-only `?frame=0..71`
freezes the shared clock for geometry snapshots; it is not a production feature
and cannot prove real autoplay or duration. The reduced-motion option overrides
the product JavaScript's exact matchMedia query only, without OS changes. The
no-JavaScript option removes demo.js from the served HTML.

Check desktop, mobile and breakpoint boundaries, completed and early states,
page and internal horizontal overflow, control clipping, pane bounds, local
artwork loading and native text sizes. Confirm accumulated turn counts and
matching app views. Check real 48/72-second loops separately, pause/restart,
transcripts, offscreen behavior, keyboard controls, copy actions and fallbacks.
Do not claim a hidden-document browser pass unless that state was observed.
Run the repository gate and privacy checks before deployment.

This document describes the implementation and checks; actual pass evidence is
recorded separately. Deployment authority comes from the operator's current
request, not from this document. Independent review was not selected.
