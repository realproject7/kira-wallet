# Native HTML workflow simulations

The public Kira site illustrates an external agent using Kira's local wallet
tools. Both simulations use authored HTML, browser text and CSS. They do not run
an agent, install software, query a wallet or provider, open a local app, or
create files. The dashboard pane is an illustrative HTML reconstruction.
Example balances and prices are fictional saved observations; missing prices
remain unknown and excluded from priced totals. Web search, calculations and
file creation belong to the agent host.

`site/index.html` owns the steps, result cards, dashboard views and readable
transcripts. `site/demo.js` owns playback, typing, reveals, scrolling and manual
controls. `site/site.css` owns native typography and responsive pane layouts.
There is no video, canvas, rasterized text or transform-scaled application frame.
Text reflows at its actual CSS size using the system font stack. Resizing does
not select a new movie source or restart a simulation.

## Two simulations, one clock

Each root has its own elapsed time, pause state, visibility, chapter selection
and scroll positions. One `requestAnimationFrame` manager serves both roots.
Each cycle lasts 48 seconds, calculated from the step count and step duration.
The `data-cycle` HTML attribute describes that duration; JavaScript calculates
it from `data-duration` and the actual steps.

| Simulation | Steps | Time per step | Content |
| --- | --- | --- | --- |
| Hero | 6 | 8 seconds | Install Kira; add public wallets; read holdings; check price gaps; add official web context; make a brief and CSV |
| Workspace | 4 | 12 seconds | Open Overview; review All tokens; compare USDC wallet allocation; check Activity |

Each step types its question for approximately 1.65 seconds. The tool line
appears at 1.8 seconds. The answer begins at 3.4 seconds and types over about
1.1 seconds. Hero result cards appear at 4.7 seconds; workspace context appears
at 5 seconds. The workspace switches the
dashboard view to match its active step; its first step shows a loading state
before revealing Overview. The browser address, breadcrumbs, tabs and app
contents are illustrative rather than working browser or wallet controls.

The clock uses a monotonic RAF timestamp. It caps a single elapsed-time
increment at 100ms and updates the DOM no more frequently than once per 50ms,
approximately 20 paints per second. This limits repeated text and scroll writes
without slowing the 48-second timeline. There is no separate playback-speed
selector. Animated text and scrolling share the same clock.

Only a running root advances or receives periodic DOM updates. A root stops
while it is offscreen, manually paused, showing its transcript, or subject to
reduced motion. A hidden document stops both roots. The shared RAF is cancelled
when neither root can run. On resumption, the timestamp baseline resets so time
spent paused is not added to the conversation. The other visible simulation
can continue while one root is stopped.

## Controls and readable content

JavaScript reveals the chapter and Play/Pause buttons. Pause freezes the current
step and text; Play resumes it. Selecting a chapter shows its completed state
and pauses. Playing after a chapter selection restarts that chapter so its
typing and reveals can be followed from the beginning.

The hero's three chapter buttons are Install, Add wallets and Ask. Ask begins
with Read holdings and remains the active chapter through the remaining wallet
questions. The workspace has one chapter button for each of its four steps.
Buttons use native keyboard interaction, descriptive labels and `aria-current`
for the active chapter. The separate Understand/Investigate/Create tabs support
Left/Right arrows, Home and End; those tabs do not control the simulation clock.

The animated surfaces are `aria-hidden`. They contain no live region or working
input, so typing does not repeatedly announce partial answers. Each root also
contains a native `details` transcript with its complete authored questions and
answers. Opening it pauses that root; closing it allows playback to resume if
the other playback conditions permit. Keep the transcript and animated example
copy consistent when editing content. These are separate HTML representations,
not a dynamically cloned transcript.

With `prefers-reduced-motion: reduce`, each root shows a completed static final
step. Its playback button reads Static and is disabled. Chapter selection still
provides static completed examples. Preference changes update the playback state.
The CSS preference also disables smooth document scrolling.

Without JavaScript, playback controls stay hidden. The hero's final report
example and the workspace's initial Overview example remain visible as full
HTML, and both transcripts can be opened with native summary controls. Scenario
descriptions also remain present. Copy buttons and scripted tab selection
require JavaScript.

## Responsive panes and typography

The hero and workspace are independent animation viewports. In addition, the
workspace has separate agent-chat and dashboard-content scroll containers.
The chat scrolls toward its latest revealed content. Dashboard content starts
at the top of each step and scrolls toward its bottom after seven seconds.
Neither pane scrolls the page or the other simulation. Changing steps resets
that root's content scroll positions.

The workspace places the agent pane beside the browser pane on wide screens,
then stacks them at its responsive breakpoint. Its sidebar and secondary chrome
adapt at smaller widths. The page uses wrapping, pane dimensions and normal
document scrolling instead of shrinking a desktop capture. Supporting text,
including tool code and dashboard rows, uses explicit CSS font sizes. Check
rendered text, clipping and controls at narrow widths rather than inferring
readability from a source image's pixel dimensions.

The page uses a small system-sans type scale: 17/26px body, 21/30px desktop
intro, 19/28px mobile intro and 13/19px routine captions. Section titles use
48/52px, 40/44px and 32/36px across the main breakpoints. The two-column hero
uses 64/68px with restrained -0.015em tracking, adapting to its available width.
Dense illustrative app and conversation text uses explicit component sizes.
The hierarchy and rhythm reference [Apple's typography guidance](https://developer.apple.com/design/human-interface-guidelines/typography)
and [the iPhone page](https://www.apple.com/iphone/).
The site uses installed system fonts; it does not download or bundle Apple's
proprietary webfonts or claim identical rendering across operating systems.

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

## Local preview and acceptance contract

Run these commands from the repository root. Use separate available loopback
ports where previews need to coexist:

```sh
python3 scripts/showcase-preview.py --port 8807
python3 scripts/showcase-preview.py --port 8808 --qa-frames
python3 scripts/showcase-preview.py --port 8809 --reduced-motion
python3 scripts/showcase-preview.py --port 8810 --no-js
```

The server binds to `127.0.0.1`, serves `site/`, applies the headers from
`site/vercel.json`, and adds `Cache-Control: no-store`. It never loads wallet
records. Its mutually exclusive QA modes are:

- `--frame 44.5`: inject an external same-origin QA clock and freeze a simulated
  frame between 0 and 47 seconds.
- `--qa-frames`: enable loopback URLs such as
  `http://127.0.0.1:8808/?frame=44.5` to select frozen frames without restarting
  the preview. The frame parameter is ignored in ordinary preview mode and is
  not a production animation feature.
- `--reduced-motion`: replace JavaScript's exact reduced-motion `matchMedia`
  response in this preview. It does not change the OS preference or emulate
  every CSS media feature.
- `--no-js`: remove the site's `/demo.js` script tag to exercise the authored
  fallback. This is not a browser-wide script blocker.

The frozen clock queues the single RAF manager and advances it in 1/60-second
increments during `DOMContentLoaded`. Use it for geometry and content snapshots.
It does not establish real autoplay, elapsed duration, visibility handling,
controls or loop behavior. Keep future RAF work inside the shared manager so
the one-callback QA clock remains representative.

For frozen geometry, inspect every step's full results and early typing/tool
states at desktop and narrow widths, including 320px, 390px and responsive
breakpoint boundaries. Verify the actual viewport dimensions for each capture.
Require no horizontal page overflow, no overlapping labels or values, readable
native text, reachable chapter and playback controls, and independent scrolling
that keeps result content available. Confirm local assets load under production
CSP and no video or canvas is introduced.

Use the ordinary preview's real clock for the full 48-second cycles. Check
ordered typing and reveals, all six hero and four workspace steps, looping,
manual Pause/Play, chapter completion and restart, transcript pause/resume,
offscreen pause/resume, hidden-document behavior and responsive state retention.
Check both roots independently, including one paused while the other runs.
Exercise keyboard access, reduced-motion static chapters and no-JavaScript
transcripts in their dedicated previews. Check installation copy controls and
the separate scenario tabs. Syntax checks include `node --check site/demo.js`
and Python compilation of the preview helper.

This document defines implementation and acceptance procedures. It does not
claim a new validation pass or independent review. The current request is for a
new preview; production deployment is not authorized by this document.

## Historical reference

Commit `09e0c0a` replaced encoded showcase movies with native HTML after small
text remained blurred even with 3x rendering. Commit `6daf3d7` retained that
engine while clarifying the external-agent boundary. The current simulations
reuse the native-text approach with new content and controls. Older MP4 exports
and scenario manifests are historical artifacts, not the current page's content
source or acceptance evidence.
