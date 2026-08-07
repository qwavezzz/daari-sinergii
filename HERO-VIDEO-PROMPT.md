# Hero video prompt — «Дары Синергии»

## Задача

Создать бесшовное фоновое видео для первого экрана сайта. Это не космос, не энергетический портал и не абстрактная магия. В кадре показан управляемый поток озона, который вводится в тёмную движущуюся воду и постепенно распределяется в ней в виде множества микропузырьков.

## Основной prompt для Gemini

```text
Create an 8-second seamless cinematic macro video for the hero section of a premium scientific water-technology website.

The scene takes place entirely underwater inside a deep, clean body of moving water. The background is very dark navy, almost black, with subtle volumetric depth and realistic liquid refraction. At roughly 30% of the frame width and 55% of the frame height, a narrow controlled stream of ozone enters the water through an unseen precision injector positioned just outside the left edge. The injection point is small, bright, and physically plausible — not an explosion and not a portal.

From this point, thousands of extremely fine ozone bubbles travel horizontally from left to right, carried by the water flow. The stream begins narrow and coherent, then gradually opens into a wide, soft plume across the central and right 65% of the frame. Bubble density increases toward the right, while individual bubbles remain visible at the edges of the plume. Add subtle fluid turbulence, micro-vortices, caustic light refraction, and a few thin pressure-wave curves created by the movement of water. The curves must feel like real hydrodynamic traces, never like planetary orbits.

The left third stays calm, dark, and visually quiet for white website typography. The brightest water and bubble activity stays in the center-right and never crosses the lower-left copy area. Camera is locked-off with only a very slow underwater drift. No visible people, animals, plants, containers, pipes, product bottles, labels, text, logos, UI, numbers, diagrams, or medical imagery.

Visual language: premium scientific cinematography, precise industrial water treatment, physically grounded, elegant, minimal, high dynamic range, deep navy water, ice-cyan highlights, natural white microbubbles. The motion should communicate controlled ozonation of water, not space, plasma, electricity, smoke, clouds, fantasy energy, spirituality, or cyberpunk neon.

Composition: 16:9 landscape, 4K, source point at x=30%, y=55%, empty negative space on the left, plume opening toward the right edge. Maintain safe crop for 1440×1000 desktop and 390×844 mobile; the injection point must remain meaningful when the right side is cropped.

Loop requirement: the final water velocity and bubble distribution must transition naturally into the first frame. Avoid a visible start, stop, flash, or camera cut.
```

## Negative prompt

```text
outer space, galaxy, stars, nebula, comet, laser beam, electricity, lightning, plasma, portal, explosion, smoke, dry particles, fantasy energy, spiritual aura, medical cross, hospital, human body, skin treatment, laboratory scientist, bottles, packaging, leaves, flowers, green eco aesthetic, typography, logo, watermark, UI overlay, oversaturated neon, aggressive flicker, rapid camera movement
```

## Технические требования к экспорту

- Основной мастер: `3840×2160`, 16:9, 8 секунд, 30 или 60 fps.
- Кодек для сайта: WebM/VP9 или AV1; запасной файл — MP4/H.264.
- Короткая сторона не ниже 1080 px после оптимизации.
- Без звука.
- Первый и последний кадры визуально совместимы для seamless loop.
- Держать нижнюю левую четверть темнее остального кадра.
- После получения видео проверить два crop: desktop `1440×1000` и mobile portrait `390×844`.

## Интеграция

При повторной генерации заменить `public/assets/hero-ozone-water.webm` и `public/assets/hero-ozone-water.mp4`, сохранив WebP-постер и существующий `<video>`-слой в `src/App.jsx`. Текстовую композицию hero не менять.
