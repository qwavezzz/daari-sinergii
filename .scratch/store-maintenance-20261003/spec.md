# Checkout, customer documents and repository maintenance

Status: in progress

## Scope

- Replace both phone examples with +7 (999) 123 45 67, preserving country selection and national digit limits.
- Reproduce and fix the reported delivery calculation failure; distinguish application defects from carrier/configuration failures.
- Show an accessible email format error after leaving the field, retaining server validation.
- Rewrite customer documents in a formal numbered structure inspired by https://soft-wear.ru/#/info/, using this shop's actual seller, payments, delivery and data processing.
- Remove retired payment configuration and demonstrably unused code/files, preserving data, source assets and migration compatibility.
- Verify affected flows and record the remaining production dependencies honestly.

## Evidence and constraints

The worktree already contained cookie changes, local rehearsal files and many documentation deletions at the start. Do not overwrite them. The reference website is accessible through HTTPS from Python; the web extraction tool cannot read it. Production shop HTTPS currently times out from this workstation; investigate before attributing delivery failure to a specific cause.
