# Desktop scroll and text speed

Status: resolved

Slow the desktop section snap transition by 2× while making the text-emergence motion cover half its previous desktop scroll distance. Keep mobile values unchanged.

## Answer

Desktop LenisSnap duration is now `1.04s` instead of `0.52s`. Desktop text emergence starts at `top 38%` instead of `top 76%`, halving its scroll distance while preserving the `top top` final state. Mobile remains at `top 88%` and receives no snap-duration change because LenisSnap is desktop-only. Production build, detector and diff validation pass.
