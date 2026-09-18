# Section text emergence

Status: resolved

Add a scrubbed section-transition text treatment: key headings should rise character by character through a lower mask while the section enters the viewport, and reach their resting position exactly when the section reaches its snap position. Supporting copy follows as a quieter masked block.

Constraints:

- preserve the current Lenis snap behavior;
- do not interfere with the pinned application-card sequence;
- keep default content visible when JavaScript is unavailable;
- disable the effect for reduced-motion users;
- use transform and clipping only, with no layout animation.

## Answer

Implemented a GSAP SplitText entrance for ten primary section scenes. Heading characters rise through per-character lower masks with a short left-to-right trail, while supporting copy follows through a bottom-up block mask. Each timeline is scrubbed from `top bottom` to `top top`, so the final character transform and copy clip both reach their resting values exactly at the section's snap position.

The application-card pin sequence and Lenis snap configuration are unchanged. The effect also runs responsively without horizontal overflow and fully reverts under `prefers-reduced-motion`. Verified at 1440 × 900 and 390 × 844; no runtime exceptions, production build and targeted UI detector pass.

## Comments

- Desktop review: the first version reads too quietly during the short snap transition. Strengthen the authored motion without changing snap timing or neighboring section behavior.
- Resolution: desktop headings now travel as a single compressed text mass from up to 18vh below their resting point, resolve from a bounded 6px blur, and reveal their characters in an earlier, wider left-to-right wave. Supporting copy has a longer 14vh rise. The snap duration and mobile motion remain unchanged.
