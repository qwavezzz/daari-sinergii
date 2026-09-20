# Delay text-emergence start

Status: resolved

Move the text-emergence ScrollTrigger start later into each section while preserving the final `top top` resting point. Use a stronger delay on desktop snap transitions and a lighter delay on free-scrolling mobile layouts.

## Answer

The emergence range now begins at `top 76%` on desktop instead of `top bottom`, delaying activation until roughly the first quarter of the section transition has passed and making the remaining reveal approximately 32% faster. Mobile uses `top 88%` for a lighter delay. The final `top top` state, scrub relationship, reduced-motion behavior and Lenis snap settings are unchanged. Production build, detector and diff validation pass.
