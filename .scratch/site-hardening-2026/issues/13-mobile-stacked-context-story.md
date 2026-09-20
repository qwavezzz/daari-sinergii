# Mobile stacked context story

Status: resolved

Replace the static mobile “Применение” list with the same pinned, bottom-up overlapping card story used on desktop. Bind the directional mobile snap controller to the five real progress stops in the pinned scene so one light gesture settles on the next or previous card.

Keep all content readable at 320 px widths, preserve the static sequential fallback for reduced motion, and do not alter the existing desktop behavior.

## Answer

Mobile and tablet layouts now use the same GSAP pinned stack timeline as desktop: the stage remains one viewport high while each following application card rises from the bottom over the previous card. The desktop media branch and its timing remain unchanged; a separate mobile media branch invokes the same authored timeline.

The 420svh context track exposes five 2 px progress markers across its scrollable range. These markers are now visible to the existing directional mobile snap controller, so a 180 px gesture at 390 × 844 settled 01 → 02, another settled 02 → 03, and an upward gesture returned 03 → 02. A quarter-progress capture confirmed the third card visibly overlaying the second during the transition.

At 320 × 700, every pinned card remained exactly 700 px high with `scrollHeight === clientHeight`; all content ended by 616 px and no horizontal overflow was detected. A short-viewport composition reduces only the card gaps, diagram size and type scale. Reduced motion still disables mobile snap and renders five relative, sequential 700 px cards in a 3500 px static stage. No runtime exceptions were found in the complete browser pass.

Production build, live dev-server response and `git diff --check` pass.
