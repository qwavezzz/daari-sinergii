# 01 — Make the official widget the primary pickup choice

Status: done (implementation; live map acceptance awaits owner's key)
Blocked by: owner's map key for live acceptance only

- [x] Map action precedes the collapsed city/office fallback.
- [x] Map open/close/reuse and failure/retry preserve the server quote rules.
- [x] Late callbacks cannot replace a newer selection.
- [x] Missing key and no-JavaScript states still allow choosing an office.
- [x] Browser checks and setup instructions are updated; live-map limits stated.

Verification: 25 targeted Django tests and 11 browser scenarios pass. Desktop/mobile screenshots reviewed for the checkout wrapper with a mocked SDK; they do not verify actual map rendering. Live key is absent, and the production SDK/map must be accepted after the owner configures it. JS syntax and Vite build pass. Existing server-calculated shipping and trial-payment amounts remain unchanged.
