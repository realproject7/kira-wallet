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
  two-pixel rendering scale and separate mobile composition preserve readable
  type and spacing. Mobile width responds to viewport height with a readable
  280px floor; short landscape screens retain normal page vertical scrolling.
- No scenario tabs, Pause button or notes appear below the film. The compact
  Demo badge remains. The existing character-led story and privacy copy stay.
- Focusing the named demo region pauses playback and reveals a scrollable HTML
  transcript. Tab enters that transcript, then its market links. Leaving the
  region resumes. A recovered video never hides a focused transcript link.
- Reduced motion, a failed media load or blocked autoplay use the same HTML
  transcript. Offscreen and hidden-document playback pauses. Responsive
  source switching preserves the current playback position.

## Generated assets

Both MP4 files use H.264, 24 fps, no audio and faststart. Desktop is
1040×1140 pixels (520×570 logical pixels), 1,495,495 bytes. Mobile is
640×1200 pixels (320×600 logical pixels), 1,523,135 bytes. Both run exactly
48 seconds. Source and poster URLs carry revision `b162f640e620`.

Reproduction on macOS requires Pillow, ffmpeg and the system SFNS font:
`python3 scripts/render-showcase.py`. Renderer assertions check card text
widths, coverage wrapping and composer/footer separation. It reads public
artwork and synthetic examples only. It never reads a portfolio. The JSON
manifest records the synthetic quantities, prices, timing and layouts.
Recorded spot values are not executable sale quotes.

## Verification

Actual Chrome checks covered widths 320, 390, 530, 667 (375px landscape
height), 700, 701, 768, 1000, 1001 and 1440. No horizontal page overflow or
header overflow occurred. The 700/701 breakpoint selected the correct movie
and aspect ratio; no question tabs remained. At 1440×900 the entire demo
was 637.8px tall and ended at y=779.8, including its composer.

The browser decoded both movies, played automatically with muted looping,
and showed successive conversation stages. Keyboard focus exposed the HTML
transcript, paused playback, made market links reachable and restored the
film on exit. Leaving the demo offscreen paused playback. A separate local
fixture with a missing desktop movie verified media-error fallback. Switching
to the valid mobile movie while a market link held focus preserved the visible
transcript and paused video, then recovered when focus left.

The current page produced no browser console errors. Independent read-only
source review found no remaining actionable issues after focus handling and
the minimum landscape width were corrected. Reduced-motion behavior was
source-reviewed; no operating-system motion preference was changed for QA.
This evidence does not claim native wallet or model testing for a site change.

Syntax, media metadata, local assets, ARIA references, diff formatting and
public-file privacy validation were checked. Functional wallet code and the
operator-published npm 0.1.2 archive/tag remain unchanged.

## Publication boundaries

PR 19 is merged and the repository default branch has the updated README.
This motion correction has its own reviewable PR. Website publication has
existing explicit operator authorization. Registry publication remains
operator-only, and the published npm 0.1.2 bytes remain immutable.
