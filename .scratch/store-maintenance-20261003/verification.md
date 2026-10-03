# Verification

- Production failure reproduced on shop.dari-sinergii.ru without creating an order/payment/shipment.
- CDEK sandbox API checked directly: city directory empty; sender location rejected (HTTP 400). Follow-up check remained unavailable.
- Full browser suite: 42 passed, including shop, checkout, CDEK, payments, admin, cookie notice, email and legal documents.
- Pages build: 60 pages, 16 products. Pages verification: desktop 1440, mobile 390 and embedded Android passed.
- Ruff check/format, JavaScript syntax and four JS unit tests passed. No model migrations required.
- Full Django suite: 353 tests, 352 passed and one PostgreSQL row-lock test skipped on SQLite. Final rerun passed after updating the assertion for the single persistent trial notice.
- Screenshots and tool logs: ignored `var/maintenance/`.
- Cleanup evidence: each of 792 browser-media files matched assets/public by SHA256; both release snapshots matched recorded Git commits plus disposable caches/build outputs. Clean Pages worktree removed via Git without force.
- GitHub initially exposed an existing test-environment mismatch: SQLite-only rehearsal commands were exercised against PostgreSQL. Fixed in `4dfd81d` by separating the suites and testing the non-SQLite refusal on PostgreSQL. Both database steps and production configuration passed in run 37108897456.
- The GitHub `test` job completed successfully: PostgreSQL 347 tests (335 passed, 12 SQLite-only tests skipped); SQLite 13 tests (12 passed, PostgreSQL guard skipped); all 42 browser tests passed on Linux Chromium.
- Full GitHub run 37108897456 completed successfully, including the Pages build, browser checks and publication. Verified application revision: `4dfd81dd4ac747f3a17fc8db1667b94053e5cd4b`.

User explicitly requested leaving seller/return addresses empty. Remaining: recovery of external CDEK sandbox; deployment of source changes to VPS. Local preview is running on port 8000.
