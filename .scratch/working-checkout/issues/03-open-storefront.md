# 03 — Describe an operating storefront
Status: done
Blocked by: None

What to build: customer pages and shared storefront messaging describe current purchasing steps rather than a future launch, while clearly identifying demo goods and trial payment and preserving unknown legal identity fields.

- [x] Remove blanket preparing-to-launch customer gates.
- [x] Public delivery copy describes Tolyatti, CDEK pickup selection, calculated delivery and final amount before payment.
- [x] Payment copy accounts for explicit simulation and eventual Alfa-Bank mode.
- [x] Refresh standard local seeded copy safely without overwriting edited owner content.
- [x] Relevant content tests pass.

## Comments

2026-10-01: Customer pages and catalog messaging now describe the current purchase flow. Trial payment is explicitly distinguished from bank payment, receipts and shipment; no seller details or preparation times are invented. Standard seed hashes retain every older baseline and include the immediately previous release; refresh preserves owner-edited pages, FAQ answers, order/publication flags and contact details. No application database was modified by this task.

Validation: `python manage.py test content --settings=config.settings_test --noinput` passes 36 tests; Ruff and `git diff --check` pass. Impeccable detector reports no findings for the four changed templates. Manual code review completed; the repository has no installed code-review or tdd skill. Full integrated checkout/browser verification is owned by the parent task.
