# Reorder water-system sections

Status: resolved

Place “Как формируется система озонирования” before “Системы озонирования воды” within the products sequence. Preserve markup, copy, scroll-snap targets and motion hooks inside both sections.

## Answer

The explanatory system sequence now precedes the water-ozonation product section in DOM and visual reading order. Both sections retain their existing `data-scroll-snap`, `data-text-emergence`, content, styling and responsive behavior. Production build, layout detector and diff validation pass.
