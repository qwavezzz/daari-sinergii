# Light header and top anchor

Status: resolved

Make the fixed header readable above `.product-oil` and `.evidence` regardless of motion preference. Verify the «Наверх» anchor while Lenis Snap is active and prevent snap from intercepting explicit anchor navigation.

## Answer

Both light sections now drive the header state outside the motion-gated timeline. The `#top` target moved from the fixed header to the document shell; explicit Lenis anchors temporarily suspend Snap and resume it after navigation. Verified from the footer: `scrollY = 0`, hash `#top`.
