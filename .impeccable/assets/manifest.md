# Asset manifest — approved comp A

Inventory basis: `PRODUCT.md`, `DESIGN.md`, `.impeccable/surfaces/src-app-jsx.md`, the approved `.impeccable/mocks/comp-a-focused-source.png` plus its embedded prompt, the official root logo, and the Impeccable craft floor.

The approved comp contains one legitimate source-backed raster role: the official brand artwork. The ozone-in-water field is intentionally a Canvas fallback for a future Gemini video, and the remaining visual language is sharper, more responsive, and more honest as HTML/CSS/SVG. No product photos, cases, specifications, testimonials, medical outcomes, or quantitative claims were generated.

## Produce

### `brand_lockup_navy`

- `source_crop`: `b0fa1e44-25f2-499a-9005-1bb01b4af64d.png` (complete official logo)
- `output_path`: `public/assets/brand-lockup-navy.png`
- `strategy`: deterministic background extraction; near-white background converted to antialiased alpha; empty outer padding trimmed with an 8 px transparent safety inset; no generative model
- `prompt_used`: “Source-edit metadata. Preserve the supplied official Дары Синергии logo artwork exactly. Remove only the white/off-white background into clean anti-aliased alpha and trim empty outer padding while keeping 8 px transparent safety padding. Keep both emblem and Cyrillic wordmark. Add nothing: no redesign, recoloring, sharpening, effects, shadow, border, or claim.”
- `dimensions`: 1289 × 1043 px
- `format`: PNG
- `transparency`: RGBA; transparent corners; antialiased silhouette
- `deviations`: none; artwork and Cyrillic wordmark preserved from the official source
- `qa_status`: `accepted`

### `brand_mark_navy`

- `source_crop`: `b0fa1e44-25f2-499a-9005-1bb01b4af64d.png` (official emblem above the wordmark)
- `output_path`: `public/assets/brand-mark-navy.png`
- `strategy`: deterministic emblem isolation and background extraction; near-white background converted to antialiased alpha; empty outer padding trimmed with an 8 px transparent safety inset; no generative model
- `prompt_used`: “Source-edit metadata. Preserve the supplied official Дары Синергии emblem artwork exactly. Isolate only the emblem above the wordmark, remove only the white/off-white background into clean anti-aliased alpha, and trim empty outer padding while keeping 8 px transparent safety padding. Add nothing: no redesign, recoloring, sharpening, effects, shadow, border, wordmark, or claim.”
- `dimensions`: 848 × 848 px
- `format`: PNG
- `transparency`: RGBA; transparent corners; antialiased silhouette
- `deviations`: the wordmark is intentionally excluded so the visible brand name can remain semantic HTML
- `qa_status`: `accepted`

Prompt metadata is embedded in each produced PNG as the `impeccable:prompt` PNG text chunk and was read back successfully after embedding.

## Direct

No standalone raster is selected to ship unchanged. The root logo remains the authoritative source but its white background and large padding make it unsuitable for direct use on the approved dark surface.

`public/assets/logo-transparent.png` was observed as a concurrent project derivative during the pass and left untouched. It preserves the source canvas at 1427 × 1102 px; the two outputs above are the tighter build-oriented derivatives from this inventory.

## Semantic

### `hero_ozone_water_field`

- `implementation`: layer a future absolute `<video muted playsInline loop>` and an authored `<canvas aria-hidden="true">` fallback inside the same clipped hero-media wrapper. Canvas coordinates anchor the injector/source near `x ≈ 30%`, `y ≈ 52–58%`. Draw a dark moving water volume first, then a narrow plume of rim-lit microbubbles advected to the right by one directional flow field. The plume opens gradually through turbulence; individual bubbles become smaller, dimmer, and less numerous along their lifetime so the physical reading is ozone dissolving into water rather than stars flying through space. Add restrained refraction/caustic smearing downstream, not a laser beam. Keep the first frame complete. On `prefers-reduced-motion`, render a fixed frame and stop particle updates; later, the Gemini video replaces only the Canvas layer and keeps the same crop/source coordinate.
- `notes`: decorative only; semantic hero copy must communicate the offer. Avoid galaxies, constellations, sparks, orbiting particles, a vacuum-black backdrop, and evenly distributed bokeh. Text occupies the quiet lower-left zone and must not overlap the bright plume core.
- `qa_status`: `accepted`

### `engineering_flow_guides`

- `implementation`: use one absolute inline SVG above Canvas and below text. Author crisp 1 px paths in `--color-line` at low opacity: one source ring/crosshair, two or three Bézier streamlines following the water current, and a few measurement nodes. Scale through the SVG `viewBox`; reduce or omit guides on mobile instead of raster-cropping them.
- `notes`: guides explain source and direction only. They must follow the plume; do not recreate cosmic orbital ellipses as the primary metaphor.
- `qa_status`: `accepted`

### `brand_in_navigation_and_footer`

- `implementation`: use `brand-mark-navy.png` as an `<img>` on light surfaces or as a CSS mask filled with `--color-text` / `--color-energy-bright` on the navy hero. Keep “Дары Синергии” as real HTML text beside it. The full lockup is available for light-background placements where a single official raster is preferable. CSS owns size, color treatment, alignment, focus state, and responsive crop; do not bake those into another bitmap.
- `notes`: preserve the official silhouette and accessible brand name. Do not rasterize navigation labels with the logo.
- `qa_status`: `accepted`

### `navigation_hero_copy_and_cta`

- `implementation`: semantic `<header>`, `<nav>`, `<h1>`, supporting paragraph, and text-link CTA. CSS owns the 12/6-column grid, typography, underlines, dividers, focus rings, mobile menu, quiet lower-left anchor, and contrast overlay.
- `notes`: the approved current headline is “Озон — сила природы.”; no UI copy from the mock should be baked into an image.
- `qa_status`: `accepted`

### `product_teaser_and_chapters`

- `implementation`: use semantic section headings and lists with CSS tonal fields. When a visual is needed, use exact inline SVG geometry for the water loop, oil vessel, or hydrolat distillation relationship; CSS owns clipping and responsive layout. Keep diagrams explicitly illustrative and omit numerical readings or pseudo-specifications.
- `notes`: no fake product photography, packaging, installation scene, shaded pseudo-product render, or technical claim until real source material is supplied.
- `qa_status`: `accepted`

### `audience_rail`

- `implementation`: semantic text items in a scroll-snap list/rail with keyboard controls and visible focus. CSS owns scale changes, partial neighboring-item affordance, drag cursor, and responsive stacking.
- `notes`: audience names are content, not artwork; no background photos are required.
- `qa_status`: `accepted`

### `manufacture_install_story`

- `implementation`: two semantic stages connected by a precise inline SVG process line: manufacturing → on-site installation. Use rectangles, connection lines, directional arrows, and text labels; CSS owns spacing and breakpoint changes.
- `notes`: keep this a diagram of confirmed capability, not a faux factory or customer-site image.
- `qa_status`: `accepted`

### `contact_terminal`

- `implementation`: semantic heading, explicit placeholder phone/email text, and accessible links only when real contacts are supplied. Compose with the transparent emblem; CSS owns the oversized muted type, terminal spacing, and divider.
- `notes`: keep placeholders visibly labelled; do not encode contact details into raster.
- `qa_status`: `accepted`

## Execution order

1. Use `brand-mark-navy.png` for the navigation/footer composition, with semantic brand text.
2. Use `brand-lockup-navy.png` only where the official combined lockup is needed on a light field.
3. Build the hero water/ozone field in Canvas with the SVG guide overlay; reserve the same wrapper for the future Gemini video.
4. Keep all remaining roles semantic or code-native until verified real media is supplied.

## Blockers

None for the current fallback implementation. Final hero video, real product/installation imagery, verified specifications/certificates/cases, and real contact details remain unavailable by design and were not fabricated.

## Assumptions

- The logo’s official navy artwork may be used as a CSS mask to obtain a high-contrast light rendering on the approved navy surface without producing a recolored raster.
- Canvas is a temporary authored fallback, not a still-image asset and not evidence of a specific machine or installation.
- SVG illustrations remain strictly geometric diagrams; anything pictorial waits for supplied real media.
