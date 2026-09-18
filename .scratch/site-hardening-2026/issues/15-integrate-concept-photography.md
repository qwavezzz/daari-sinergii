# Integrate concept photography

Status: resolved

Prepare the nine supplied source PNGs as responsive WebP assets and integrate them into the five stacked application panels, the three product chapters, and the manufacture/install process scene.

Preserve the current pinned/snap motion, prevent layout shift, retain source originals, disclose the conceptual nature once before the image series without adding anything to the cards, and verify desktop plus 390 × 844 and 320 × 700 layouts.

## Answer

All nine supplied PNGs remain in `public/assets/photos/source/`. Responsive WebP pairs were generated in `public/assets/photos/optimized/`: 480/900 px squares for the five application scenes, 720/1200 px 4:3 images for the three product chapters, and 720/1200 px wide images for installation. Individual outputs range from 20 KB to 101 KB.

The existing SVG placeholders were replaced by a shared responsive `ConceptPhoto` component with intrinsic dimensions, lazy loading and asynchronous decoding. The five application photos retain the same pinned overlay timeline and snap markers; only the obsolete per-SVG line/particle animation was removed. No captions, labels, badges or new decorative elements were added to the cards. A single disclosure appears in the products introduction.

QA evidence:

- `npm.cmd run build` succeeds and `git diff --check` reports no whitespace errors.
- Headless Edge at 1440 × 900, 390 × 844 and 320 × 700 loaded all nine photos with no failed requests, runtime exceptions, broken images or horizontal overflow.
- At 390 × 844 one 180 px scroll input advanced the application stack from panel one to panel two; no tested product, application or process section overflowed vertically.
- Reduced-motion mode renders all five application photos in the normal document flow.
- Screenshots: `qa/photos-product-desktop.png`, `qa/photos-oil-desktop.png`, `qa/photos-hydrolat-desktop.png`, `qa/photos-context-desktop.png`, `qa/photos-process-desktop.png`, `qa/photos-context-mobile-390.png`, `qa/photos-process-mobile-390.png`.
