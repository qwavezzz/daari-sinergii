# Mobile context snap and section heights

Status: resolved

Extend the touch-safe directional mobile snap to every “Применение” context card without changing the pinned desktop story. Keep long-card interiors freely scrollable and preserve reduced-motion behavior.

Make the mobile “Гидролаты” and “Одна технология. Разные контексты.” sections fill at least one viewport so the following section does not peek through. Compact “От производства — к вашему объекту.” so its diagram and two production steps fit the mobile rhythm without excessive vertical space.

## Answer

Each “Применение” panel now exposes a mobile-only snap marker. The native mobile snap controller includes those markers, while the desktop Lenis selector remains limited to the existing section markers, so the pinned desktop story is unchanged. Directional proximity behavior is preserved: at 390 × 844 the first and second panels both settled at `top: 0`, and a 110 px scroll inside the second panel stayed at `-110` rather than rolling back.

“Гидролаты”, the contexts introduction and every application panel now occupy at least one small viewport on mobile. The production section was compacted through smaller viewport-aware heading type, diagram geometry, gaps and paddings; at 390 × 844 it is exactly 844 px high with its final content ending at 745 px, while at 320 × 700 content expands naturally to 789 px without clipping.

Browser QA at 390 × 844 and 320 × 700 found no horizontal overflow or runtime exceptions. The production build and `git diff --check` pass.

## Comments

The user clarified that the five application cards should share a pinned overlapping scene instead of behaving as five static sections. Issue 13 supersedes the panel-level mobile markers from this implementation; the viewport-height and production-section fixes remain current.
