# Kira identity and character direction

Status: adult webtoon direction approved by the operator on 2026-10-03. Chic Researcher is the current base character in the live viewer and concept studio. A consistent expression pack remains future work. The local brand icon and notebook favicon are delivered.

## Promise and voice

Kira helps you understand what your wallets hold and how much of the evidence
is known. She is a composed adult researcher with a small lavender notebook, a subtle smile and a quietly playful streak. She states the
result first, explains its source, and offers one useful next action.

Say: “I found three priced positions. Two others still need a reliable price.”
Say: “Base is checked at this block. Ethereum could not be reached.”
Say: “This is the curve's reserve, shared by all holders.”
Avoid fortune telling, profit celebrations, urgency, investment rankings,
streaks, casino imagery and a confident zero when coverage is missing.

The identity supports clear evidence. Financial figures, times, chain identity
and missing information remain readable without depending on the character.

## Concepts

| Concept | Invariant anchors | Strength | Review concern |
| --- | --- | --- | --- |
| Chic Researcher | Espresso hair in a loose low bun, calm gray-violet eyes, charcoal blazer, ivory shirt, lavender notebook | Adult, chic and approachable; current preferred direction | Expression consistency and small portrait crops still need review |
| Early Moon Researcher | Lavender bob and fantasy cape, 2D webtoon art | Demonstrated a 2D style | Superseded because the operator found it too youthful |
| Star Scout | Cream rounded star, lavender satchel, brass clasp, ink eyes | Simple silhouette and a compact companion at small sizes | Lower star points merge into feet; validate a flat icon later |
| Cloud Archivist | Ivory cloud lobes, lavender cape, apricot button, notebook | Calm tone suits incomplete evidence | Generated translucent halo is too broad for a small UI; remove through an image edit before production |
| Moon Librarian | Lavender bob, crescent clip, ivory hood, notebook pouch | Rich identity and expression vocabulary | Outfit details lose clarity below 96 px; generated halo also needs cleanup |

The operator preferred an adult woman with a chic, quietly cute presence, using two supplied style references. This supersedes the earlier mascot and youthful fantasy directions. The original references are not distributed.

See the [interactive comparison](../prototype/index.html#/characters) and
[original concept inputs](character/generation.json) and [webtoon inputs](character/webtoon-generation.json). Assets are original
built-in imagegen outputs. All generated PNGs carry alpha channels. The two original 3D
alternatives contain a visible semitransparent halo despite the request for
a clean silhouette. They remain concept outputs rather than production assets.

## Toony workflow applied

The local Toony implementation informed the workflow, without source copying
or changes to that project. Relevant references are `generate.ts`'s
`injectCharacterLockstrings` and `composePrompt`, the character reference lint,
and `docs/TOONY-WEBTOON-CRAFT.md`'s identity anchors.

1. Define a short character lockstring with shape, exact colors and one accessory.
2. Inject that description verbatim before the scene prompt.
3. Keep story context and palette separate from pose and expression.
4. Record the final submitted prompt, provider and asset path.
5. Inspect the generated silhouette, anchors, alpha edges and small-size read.
6. Reuse the selected image as an explicit reference for later expressions.

Toony can record seeds and ComfyUI workflow settings. Built-in imagegen exposes
neither here, so deterministic replay is not claimed. Character state artwork
is not yet a consistent multi-pose pack. No Toony code, model checkpoint or
existing character artwork is distributed in Kira.

## State rules

| State | Character behavior | Visible evidence and copy |
| --- | --- | --- |
| Empty | A quiet welcome | “Add a wallet when you're ready.” |
| Queued | Notebook closed | Job ID and queue state; no percentage |
| Discovering | Attentive | Named stage, chain and actual completed units |
| Checking contracts | Studying | Block number, RPC status and checked assets |
| Partial | Calm, never celebratory | Known totals plus unavailable chains and unknown prices |
| Complete | Small acknowledgement | Observation time, coverage and source links |
| Provider error | Neutral concern | Redacted failure, retry scope and saved prior analysis |

The prototype uses one neutral pose and explicitly simulated states. It has no
autonomous financial action or working chat connection. Production progress
must be driven by persisted jobs and measurements, never a decorative timer.

## Visual system

Warm paper `#FCFBF8`, card white, ink `#292536`, muted ink `#686174`, purple
`#6755CE`, soft purple `#F0EDF9` and apricot `#F3C89E`. Purple is the action
accent; apricot is decorative. Financial status must not rely on color alone.

Use the native system font stack. Body text is 14 to 16 px, primary figures
use tabular numerals, headings have restrained negative tracking, and a 4 px
spacing grid supports generous margins. Rounded cards are 18 to 24 px.
Keep one compact breadcrumb. Character art appears beside explanations,
outside financial table cells. Reduced motion disables decorative animation.

Design evidence: [selected Lazyweb references](https://www.lazyweb.com/agentic-search/d4bd1497-9716-4312-95b7-f3834ebf2481)
cover OpenSea token context, PostHog progress, Duolingo companion onboarding
and Monarch portfolio navigation. These are pattern references, not copied UI.

## Local brand assets

`viewer/static/kira-logo.png` is an original built-in imagegen icon based on the
approved adult character. It retains espresso hair, gray-violet eyes, ivory
shirt, charcoal blazer and lavender notebook. A second imagegen pass cleaned
the transparent exterior. Exact prompts are in
[brand-generation.json](character/brand-generation.json). The editable notebook
mark in `viewer/static/favicon.svg` supplies a clear tiny-size brand anchor.
The icon appears in brand/Home links, Kira notes, empty state, add dialog and
prototype navigation; browser and touch icon links are installed.
