# Run local rehearsal checks against their supported database

Status: in progress

The PostgreSQL GitHub job failed because local rehearsal commands intentionally reject non-SQLite databases. Preserve that restriction. Run the local-command suites in a separate SQLite CI step, and verify on PostgreSQL that both commands refuse before changing data.

## Verification

Local focused suite: 13 tests, 12 passed; the non-SQLite guard test is reserved for PostgreSQL. Ruff check/format passed. Pending the full GitHub workflow.
