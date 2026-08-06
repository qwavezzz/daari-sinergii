# 08 — Проверка и готовая презентационная сборка

**What to build:** A tested presentation build that lets stakeholders compare all four complete variants on desktop and mobile, with verified routes, placeholders, performance fallbacks, and clear run/replacement instructions.

**Blocked by:** 07 — Видео, формы и производительные анимации

**Status:** done

- [x] The full verification suite passes for every route and variant.
- [x] Desktop and mobile visual inspection covers all four home variants and representative inner routes.
- [x] Material defects found in the first review are fixed in one batch and confirmed once.
- [x] Replacement points for video, contacts, proof, and other placeholders are documented.
- [x] The final handoff includes exact run commands and names all unfinished factual inputs.

## Verification notes

- `npm test` and JavaScript syntax checks pass after the single repair batch.
- Headless Edge confirmation covers all four home variants at `1536 × 1024` and `390 × 844`, plus Contacts for Reactor/Water Column and direction routes for White Laboratory/Sectional Medium at both sizes.
- URL priority, local-storage persistence, keyboard-visible focus, demonstration-form error/success states, explicit missing-media fallback, reduced-motion zero-FPS mode, inactive rail isolation, and viewport-width containment were confirmed.
- The only material first-pass defect was the hidden missing-video explanation in Water Column on mobile; the confirmation pass shows the explicit message restored.
- Generated HTML and source assets contain no remote application resources. Endpoint-security software injected its own Kaspersky requests during Edge automation; these are not emitted by the build.
- The final Impeccable detector run returned no findings for the changed interface target.
