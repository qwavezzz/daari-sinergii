# Header logo geometry

Status: resolved

Remove the cropped, absolutely positioned treatment that makes the official square mark read as a narrow vertical fragment. Preserve its intrinsic aspect ratio at desktop and mobile sizes.

Answer: the mark now uses its complete square artwork with `object-fit: contain`: 42 × 42 px on desktop and 36 × 36 px on narrow mobile screens. The conflicting 38 × 30 px mobile override was removed. Verified visually at 1440 × 900 and 390 × 844, with no horizontal overflow; production build and targeted UI detector pass.
