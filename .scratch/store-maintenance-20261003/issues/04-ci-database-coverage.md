# Run local rehearsal checks against their supported database

Status: resolved

The PostgreSQL GitHub job failed because local rehearsal commands intentionally reject non-SQLite databases. Preserve that restriction. Run the local-command suites in a separate SQLite CI step, and verify on PostgreSQL that both commands refuse before changing data.

## Verification

Local focused suite: 13 tests, 12 passed; the non-SQLite guard test is reserved for PostgreSQL. Ruff check/format passed. GitHub run 37108897456 completed the test job successfully: PostgreSQL 335 passed / 12 SQLite-only skips, SQLite 12 passed / one PostgreSQL-only skip, 42 browser tests passed. Production configuration passed. Runtime restrictions remain unchanged.
