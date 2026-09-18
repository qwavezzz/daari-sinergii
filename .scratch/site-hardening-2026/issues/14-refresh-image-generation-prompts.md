# Refresh image-generation prompts

Status: resolved

Rewrite the image-generation brief to match the current site: five full-screen stacked application contexts in their actual order, three product chapters, the navy/cyan “controlled flow” art direction, and the absence of verified project photography.

Define realistic composition and crop requirements for the current visual slots, add the missing private-home scenario, remove implications that generated equipment represents a real company model, and give a safe integration priority.

## Answer

`PHOTO-PROMPTS.md` is now a production-oriented image brief for the current interface. It prioritizes the five application contexts in their actual order, adds the missing private-home scenario, and supplies three product and three process scenes with stable filenames.

The shared visual contract now matches the implemented “controlled flow” world: low-key navy photography, ice-cyan reflections, quiet edges, physically plausible water and engineering, no neon/CGI, and no implication that a generated device is a verified company model. Context masters use a 4:5 central composition that survives the current square visual crop and preserves quiet mobile title/copy zones; product/process masters use 4:3 or 3:2 central-safe crops.

The brief explicitly keeps generated imagery out of the document-evidence section, preserves the existing hero video, requires a single section-level “Концептуальные визуализации” disclosure without labels on the cards, and explains integration into `.context-panel-visual` without turning images into rounded cards or text backgrounds. A shared negative prompt, pre-export checklist and WebP guidance are included. README now links the prompt package. UTF-8 content, all five context names, eleven prompt placeholders and `git diff --check` were verified.
