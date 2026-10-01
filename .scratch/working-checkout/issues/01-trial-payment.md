# 01 — Finish checkout with trial payment
Status: done
Blocked by: None

What to build: a session-owned simulated payment page that displays the immutable goods, delivery and final amount, supports explicit success/cancel/retry, and clearly distinguishes the result from actual Alfa-Bank money.

- [x] No bank card data requested or real charge issued.
- [x] Test completion does not claim actual financial paid status or send real paid notifications.
- [x] Simulation only works when explicit configuration is enabled; real bank remains isolated.
- [x] Repeat submission and foreign sessions are safe.
- [x] Tests verify the customer-visible full path and amounts.

## Verification
15 trial payment Django tests; browser success/cancel/retry with and without JavaScript; unmocked CDEK sandbox checkout to trial total 1542 RUB passed. A saved trial marker permanently blocks Alfa-Bank registration and reconciliation.
