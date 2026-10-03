# Explicit sandbox delivery rehearsal

Status: done

The owner approved a temporary, clearly labeled synthetic delivery price because the CDEK sandbox calculator fails with independently verified requests. Use 500 RUB for the entire order, without an invented delivery period. Keep the sandbox pickup directory, server validation, measured packing and signed quotes. This is an explicit opt-in mode, never an automatic fallback.

Require CDEK_TEST_MODE=true, PAYMENT_STUB_ENABLED=true and ALFABANK_ENABLED=false. Persist the synthetic price source so these orders can never enter bank payment even after configuration changes. Label checkout, trial payment, order and administration. Cover normal carrier mode and the rehearsal with regression tests and browser verification. Document VPS activation; do not change production settings remotely.

## Verification

46 focused server tests passed. Full local suite: 362 discovered, 360 passed, two environment-specific skips (includes existing untracked rehearsal tests). Browser suites: 42 normal-mode tests plus two demo checkout/trial scenarios at 1440 and 390 px passed. Screenshots inspected; no horizontal overflow or JavaScript exceptions. Ruff, JS syntax checks, four JS unit tests and Vite build passed; no migrations required. Local real-sandbox-directory check for TLT2 returned HTTP 200 with price 500.00 and price_source=demo, without creating an order. Local development mode enabled; VPS activation remains an operator step.
