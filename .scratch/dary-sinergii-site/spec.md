**Status:** ready-for-agent

## Problem Statement

«Дары Синергии» needs a fast, multi-page marketing website that explains three different business directions to organizational buyers first and private buyers second. The company has visual references and a seed design system, but no production media, verified proof, finalized contacts, prices, metrics, testimonials, or detailed specifications. Stakeholders also need to compare four genuinely different site concepts without rebuilding the content four times.

The site must feel cinematic and technically distinctive while remaining usable on modest phones and computers. It must avoid long homepage copy and excessive empty stretches, and it must never replace missing business facts with invented claims.

## Solution

Build a dependency-light static website with seven routes and one shared content source. Four complete presentation variants will reinterpret the same routes, facts, actions, and placeholders through different composition and motion systems. A removable presentation switcher will let stakeholders compare variants, preserve the current choice during navigation, and deep-link directly to any option.

The experience will use native browser capabilities rather than a heavy framework: semantic HTML, layered CSS, IntersectionObserver, requestAnimationFrame, Canvas 2D, and a progressive HTML5 video component. Desktop receives cinematic scroll-linked behavior; mobile and reduced-motion modes receive lighter, complete alternatives.

The homepage will use concise scenes rather than long copy: an immersive hero, the three directions, industry paths, a compact explanation of the selection process, proof placeholders, and a final demonstration request form. Inner routes expand one topic at a time without inventing facts.

## User Stories

1. As an organizational buyer, I want to understand what «Дары Синергии» does in the first viewport, so that I can decide whether the company is relevant.
2. As an organizational buyer, I want to distinguish ozone systems, ozonated oils, and hydrolats quickly, so that I can enter the right path.
3. As a sports or recovery organization, I want to find my industry context, so that I can see which direction may be relevant.
4. As a water-treatment organization, I want a clear path to ozone-system information, so that I do not need to interpret unrelated product copy.
5. As a veterinary or agricultural organization, I want my context represented without unsupported outcome claims, so that the site feels credible.
6. As a private buyer, I want a secondary personal-use path, so that the B2B emphasis does not block me.
7. As a visitor, I want short sections and visible next actions, so that I do not need to read long promotional paragraphs.
8. As a visitor, I want to open a dedicated page for each business direction, so that I can learn more without overloading the homepage.
9. As a visitor, I want an industry-solutions page, so that I can navigate by situation instead of product terminology.
10. As a visitor, I want an About page with honest placeholders for evidence, so that missing proof is not disguised as marketing.
11. As a visitor, I want a Contacts page with centralized editable details, so that current placeholders can later become real contacts.
12. As a visitor, I want a consultation form that validates my entries, so that the future submission experience is already represented.
13. As a visitor, I want the demonstration form to say that no data was sent, so that I am not misled.
14. As a stakeholder, I want four radically different visual variants, so that I can compare genuine design directions.
15. As a stakeholder, I want the selected variant to apply to every route, so that I can evaluate a complete system rather than four hero mockups.
16. As a stakeholder, I want a persistent presentation switcher, so that I can move between pages without losing the selected variant.
17. As a stakeholder, I want a URL-addressable variant state, so that I can share a specific option directly.
18. As a stakeholder, I want the switcher removable through one configuration decision, so that it does not need to remain on the final public site.
19. As a content editor, I want all contact values and factual placeholders centralized, so that a future admin interface has a clear integration boundary.
20. As a content editor, I want one factual content model shared by all variants, so that design comparisons do not drift into different claims.
21. As a content editor, I want missing photos, video, contacts, metrics, and proof visibly marked, so that replacement work is obvious.
22. As a future administrator, I want a stable content interface, so that an admin backend can replace static values without redesigning pages.
23. As a desktop visitor, I want the hero medium and explanatory labels to respond to scroll, so that the technology feels tangible.
24. As a desktop visitor, I want bubbles and products to cross only display typography, so that the composition gains depth without hiding essential content.
25. As a visitor, I want diagnostic overlays to explain real categories rather than decorative pseudo-data, so that the science-fiction treatment remains trustworthy.
26. As a mobile visitor, I want simplified motion and stable layouts, so that the experience remains smooth and readable.
27. As a visitor who prefers reduced motion, I want complete static compositions, so that no information depends on animation.
28. As a keyboard user, I want navigation, the variant switcher, and forms to be fully operable, so that the site is not pointer-only.
29. As a visitor, I want visible focus and sufficient contrast, so that interactive controls remain understandable.
30. As a visitor on a slow connection, I want the page to render before video or animation assets load, so that the offer is never hidden by media.
31. As a visitor whose browser cannot render Canvas, I want a designed poster fallback, so that the hero still feels intentional.
32. As a stakeholder, I want Variant 1 «Реактор O₃» to use a dark particle stream and diagnostic scan, so that the technical process becomes the central spectacle.
33. As a stakeholder, I want Variant 2 «Белая лаборатория» to use bright editorial typography and instrument-like diagrams, so that quality reads as clarity and control rather than glow.
34. As a stakeholder, I want Variant 3 «Водная колонна» to use full-viewport scroll-snap scenes, so that each direction owns one decisive moment.
35. As a stakeholder, I want Variant 4 «Сечение среды» to expose layers of water, product, and process like an engineering section, so that explanation becomes spatial.
36. As a stakeholder, I want the variants to share cyan and white brand anchors while differing in topology, rhythm, controls, and motion, so that they remain comparable but genuinely distinct.
37. As a visitor, I want the hero to contain a real video element ready for a future local file, so that adding the final media does not require structural rework.
38. As a visitor before the real video exists, I want a clearly synthetic ozone/water placeholder, so that I am not shown false product footage.
39. As an organization, I want the main action «Подобрать решение», so that I can move from orientation to a relevant inquiry.
40. As a visitor, I want the secondary action «Получить консультацию», so that I can contact the company without first selecting a product.

## Implementation Decisions

- Use a static multi-page architecture with no runtime framework and no mandatory third-party animation library.
- Use a small dependency-free Node.js build and development server so shared content and layouts generate real HTML routes.
- Keep one content model for company directions, audiences, navigation, contact placeholders, proof placeholders, and form labels.
- Treat the content model as the future admin integration seam. No admin interface or backend is built in this phase.
- Generate seven routes: Home, Ozone Systems, Ozonated Oils, Hydrolats, Industry Solutions, About, and Contacts.
- Apply four full variants across all routes through a stable variant state and variant-specific layout modules.
- Persist the variant in both the URL query and local browser storage. URL state wins when both are present.
- Make the presentation switcher keyboard accessible, labelled, and removable through configuration.
- Keep the homepage sequence factual and compact: hero; three directions; industry paths; selection process; evidence/case placeholder; final consultation action.
- Inner direction pages use: concise definition placeholder; tasks and applications; audience fit; product/equipment options placeholder; consultation action.
- The industry page uses organization-first navigation and a quieter secondary path for private buyers.
- The hero contains an HTML5 video element with poster/fallback layers. The source remains intentionally unset until real media is supplied.
- Use Canvas 2D only for bounded decorative fields. Cap pixel ratio and particle counts, pause offscreen work, and avoid continuous animation on hidden tabs.
- Use IntersectionObserver for entry states and a single requestAnimationFrame coordinator for scroll progress. Avoid independent scroll listeners per section.
- Use CSS transforms and opacity for most motion; avoid layout-thrashing animation properties.
- Implement reduced-motion as a first-class rendering mode, not as an afterthought.
- Use local system font stacks chosen to approximate the seed system without network font requests. Font assets may be added later.
- Keep diagnostic labels factual and categorical. Unknown values display `Уточняется` or another explicit placeholder.
- Forms validate client-side, never transmit or store data, and show a transparent demonstration-state message.
- Do not use analytics, cookies, external embeds, remote stock media, or third-party form endpoints.
- Use a short opening direction contract in emitted markup for each variant so its distinct composition survives implementation.
- Concept assignments are grounded in Impeccable surface seeds: Variant 1 uses the particle-process structure; Variant 2 the editorial index; Variant 3 the full-viewport vertical sequence; Variant 4 the layered sectional structure.

## Testing Decisions

- The primary test seam is the served website as a visitor experiences it: routes, variant switching, navigation persistence, forms, and responsive/reduced-motion states are verified at the browser boundary.
- A dependency-free verification script checks that every route is generated, every route includes all four variants, required landmarks and actions exist, factual placeholders remain explicit, and no remote media or form endpoint is introduced.
- Browser smoke checks cover each homepage variant, one representative inner route per variant, the presentation switcher, URL persistence, local-storage fallback, keyboard use, demonstration form behavior, and missing-video fallback.
- Visual inspection uses a bounded two-pass review at representative desktop and mobile widths. The first pass identifies material defects in all four variants together; fixes land as one batch; the second pass confirms them.
- Performance verification checks that offscreen Canvas work pauses, mobile particle budgets are reduced, layouts remain stable without video, and the site is usable with JavaScript-disabled content fallbacks where practical.
- Accessibility checks cover semantic headings and landmarks, focus visibility, keyboard ordering, contrast, reduced motion, labels, and non-animation access to all content.
- Tests assert external behavior and generated output, not internal helper structure.

## Out of Scope

- A production CMS or admin interface.
- Sending, storing, or processing contact-form submissions.
- Deployment or publication to an external host.
- Real hero video, product photography, product specifications, prices, certificates, customer logos, testimonials, case-study results, or contact details.
- Medical efficacy claims or any claim unsupported by supplied evidence.
- E-commerce, online payment, authentication, personal accounts, analytics, CRM integration, or database storage.
- Automatic selection of the final variant; stakeholders will choose after reviewing the presentation build.

## Further Notes

- The initial positioning word «quality» is a desired brand direction, not proven evidence. Copy should express care, clarity, and control through design without claiming superiority.
- The final hero video should be supplied as an optimized local MP4/WebM pair with a poster image. The current build exposes the replacement boundary and uses a synthetic placeholder.
- Unknown factual fields must remain visibly replaceable. Placeholder content is part of the handoff, not temporary copy disguised as final truth.
- `DESIGN.md` is a seed. After implementation, Impeccable documentation should be refreshed from the actual tokens and components.

