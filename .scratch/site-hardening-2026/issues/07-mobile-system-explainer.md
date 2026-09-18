# Mobile system explainer and light-header contrast

Status: resolved

Adapt the “Как формируется система озонирования” section for narrow touch screens as a legible vertical process rather than a scaled desktop grid. Preserve all technical copy and the desktop/tablet layout.

Also fix the mobile header menu control so it inherits the header's dark foreground while crossing light sections and returns to white on dark sections.

Acceptance:

- 320–767 px uses a connected four-stage vertical process spine;
- stage numbers, titles and descriptions remain readable without horizontal overflow;
- selection inputs read as a separate compact register;
- the fixed header logo, brand name and Menu control switch contrast together;
- 44 px mobile control target and reduced-motion behavior are preserved.

## Answer

At 320–767 px the four stages now form a connected vertical process spine with 36 px numbered nodes, a continuous technical line and a dedicated content column. The heading scale and section spacing were tuned for narrow screens, and the selection inputs now form a compact ruled register instead of a wrapped inline list. All technical copy remains present.

The Menu control now inherits the fixed header foreground instead of forcing white. Mobile ScrollTrigger initialization also refreshes after Lenis is disabled, keeping light-section contrast correct across initial load and breakpoint changes.

Verified at 390 × 844 and 320 × 700: no horizontal overflow, 44 px Menu target, four 40 px/remaining-width step grids. On both light sections the header and Menu resolve to `rgb(4, 16, 31)`; on dark sections both resolve to `rgb(247, 251, 253)`. Production build and targeted UI detector pass with no runtime exceptions.
