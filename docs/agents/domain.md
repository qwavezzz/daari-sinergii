# Domain Docs

How engineering skills consume this repository's domain documentation.

## Before exploring, read these

- `CONTEXT.md` at the repository root; or
- `CONTEXT-MAP.md` if it exists, which points to one `CONTEXT.md` per context;
- relevant ADRs under `docs/adr/`.

If a file does not exist, proceed silently. Domain-modeling skills create it when terminology or decisions are resolved.

## Layout

This repository uses a single domain context:

```text
/
├── CONTEXT.md
├── docs/adr/
└── src/
```

## Vocabulary

Use terms exactly as defined in `CONTEXT.md`. Do not drift to synonyms the glossary explicitly avoids. If a required concept is absent, reconsider whether it is being invented or record a genuine domain gap.

## ADR conflicts

If proposed work contradicts an existing ADR, surface the conflict explicitly instead of silently overriding it.

