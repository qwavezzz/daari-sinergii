# Production hero-video

Status: resolved

## Answer

- Hero uses the production H.264 MP4 with a WebP poster and keeps the existing text composition.
- Playback is muted, looping, inline, paused outside the viewport or on a hidden tab, and resumed on return.
- Reduced-motion mode shows the poster without video playback.
- Verified at 1440×1000 and 390×844: readyState 4, playback advances, no horizontal overflow, and the watermark remains outside the visible crop.

Подключить пользовательский `IMG_5583.MP4` вместо Canvas, сохранить текущую hero-композицию и обеспечить poster, autoplay, mobile crop, reduced-motion и остановку воспроизведения вне viewport.

## Source

- H.264 MP4, 1280×720, 6.21 секунды, 2.4 МБ.
- Poster извлечён на 34% ролика: WebP, 54 КБ.
