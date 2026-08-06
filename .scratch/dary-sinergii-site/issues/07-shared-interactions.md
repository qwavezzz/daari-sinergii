# 07 — Видео, формы и производительные анимации

**What to build:** Shared production-grade interaction behavior for all variants: a replaceable hero video boundary, procedural fallback, transparent demonstration forms, centralized contact placeholders, bounded scroll coordination, and accessibility/performance fallbacks.

**Blocked by:** 03 — «Реактор O₃»; 04 — «Белая лаборатория»; 05 — «Водная колонна»; 06 — «Сечение среды»

**Status:** done

- [x] The hero renders immediately without a real video and is ready for local MP4/WebM sources later.
- [x] Forms validate, never submit or store data, and clearly identify demonstration behavior.
- [x] Contact placeholders come from the shared content boundary.
- [x] One scroll coordinator pauses offscreen work and caps mobile/desktop animation budgets.
- [x] Keyboard, focus, contrast, reduced motion, and no-Canvas fallbacks work across all variants.
