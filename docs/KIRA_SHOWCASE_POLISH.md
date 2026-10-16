# Showcase polish, 2026-10-05

Historical acceptance for PR 19. The operator subsequently clarified that the
automatic video must remain. The continuous-film correction supersedes the
manual-demo behavior below; see [motion acceptance](KIRA_SHOWCASE_MOTION.md).

The operator requested a clearer showcase demo, a character-led product pitch,
fewer annotations and deliberate headline wrapping. This change affects the
static website only. The published npm 0.1.2 archive and tag remain unchanged.

## Final behavior

- The demo uses responsive HTML instead of scaling text inside a video.
  Three manually selected questions cover token values, Blast holdings and
  saved-analysis changes. Token, price, quantity and venue have separate visual
  roles. Unknown prices remain unknown. Examples show recorded spot values,
  without implying executable sale quotes or transfer-history research.
- The Pause control, transcript disclosure and annotations below the demo are
  removed. A compact Demo badge identifies the example.
- The hero keeps each sentence together: “Manage your wallets.” and
  “With your own AI.”
- The product story uses the existing Kira character artwork and three concise
  capabilities. The ownership section describes public-address watching,
  local storage and the selected context sent to the chosen AI provider.
- CSS and JavaScript references include a content revision. This prevents the
  new HTML from loading an earlier cached stylesheet or script.

## Verification

Actual Chrome checks covered widths 320, 390, 768, 1000, 1001, 1024, 1180 and
1440. The headline remained two lines without horizontal page overflow.
All three examples rendered, and their local token and character images loaded.
Arrow keys and End changed the selected tab and keyboard focus together.
The installation control resolved its clipboard write and showed Copied with
an accessible success message. The browser bridge's separate clipboard read
returned an empty value, so it was not used as byte-level clipboard evidence.

A read-only source review found faint supporting text. Those colors were
corrected, including the final comparison-label finding. The corrected labels
have a calculated 4.93:1 ratio against their card background. A computed-style
check found no failing text contrast pairs in the default rendered page.
This is a targeted check, not a complete accessibility certification.
The reference threshold is documented by
[W3C](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html).

`node --check site/demo.js`, `git diff --check` and the repository public-file
privacy check passed. No wallet, native model or trading tests were repeated
for this static-only change.

## Design evidence and publication

The research considered Gorgias, Guru and Microsoft Copilot patterns for a
readable chat example, a character-led capability story and a calm composer.
[Design references](https://www.lazyweb.com/agentic-search/9bde7e00-d871-4aee-ac36-77aeffd6df08).

PR 19 was merged with explicit operator approval on 2026-10-05. Its merge commit
is `2ed52a24bc38ac4101aceff781cb7ff58941be57`. The default branch,
`codex/kira-release`, now includes the updated README. Production website
publication has separate existing authorization.
