# Mobile section snap and menu icons

Status: resolved

Add touch-safe directional section snapping below the desktop breakpoint. It should advance only in the user's scroll direction, align nearby section starts after momentum settles, and leave the interior of long sections freely scrollable. Disable it for reduced motion and while the mobile menu is open.

Replace the mobile header's “Меню” text with a three-line SVG icon and the menu overlay's “Закрыть” text with an SVG cross. Preserve accessible names, focus management, the 44 px targets and current color inheritance.

## Answer

Mobile and tablet layouts now use a directional proximity snap after native momentum settles. A downward gesture can only advance to a nearby section start; an upward gesture can only return to a previous start, so the behavior never reverses the user's direction. The threshold is capped at 560 px / 68svh. Long-section interiors remain free because snapping only occurs when the next directional boundary is within that range. The feature is disabled while the menu is open and under reduced motion.

The header control now renders a three-line authored SVG and the overlay close control renders an SVG cross. Both retain their 44 × 44 px targets, current-color contrast, focus restoration/trapping and explicit accessible names.

QA at 390 × 844 confirmed forward and backward alignment, no rollback after passing a section start, free scrolling 420 px inside the 1843 px system explainer, and no snapping at reduced motion. Menu focus and accessibility checks pass with no runtime exceptions. Production build, targeted detector and diff validation pass.
