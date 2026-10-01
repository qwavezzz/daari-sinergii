Status: ready-for-agent

## Problem Statement
The owner needs to exercise the complete purchase flow now. Previous readiness gates made the storefront appear closed and prevented trying delivery and payment.

## Solution
Keep the demo catalog but open the local purchase journey. Customers select a CDEK pickup point, receive a server-calculated delivery quote, submit the order and reach an explicitly simulated payment page. Public copy describes the purchase workflow in the present tense. Actual bank charges remain a separately configured integration.

## User Stories
1. As a shopper I can browse demo products and add them to the cart.
2. As a shopper I can open checkout without a preparing-for-launch gate.
3. As a shopper I can search for a CDEK pickup point by city and select it without knowing its code.
4. As a shopper I can select on the official map when its required credentials are configured.
5. As a shopper I see delivery price calculated by CDEK and an updated final total.
6. As a shopper I can recover from provider errors without losing my details.
7. As a shopper I reach a trial payment page showing the saved order and delivery amount.
8. As a tester I can exercise success, cancellation and retry without entering bank card data or charging money.
9. As an owner I can distinguish simulated payment from real money received.
10. As an owner I can switch to Alfa-Bank without replacing the checkout.
11. As an owner I have a repeatable local launch and clear remaining API setup.

## Implementation Decisions
- Preserve existing server-verified quotes, stock reservations, session ownership and Alfa-Bank validation.
- Add an explicit payment stub mode separate from Alfa-Bank and financial paid status.
- Open local checkout through explicit setup with demo packaging assumptions clearly documented, never fabricated measurements of real goods.
- User confirmed origin Tolyatti; assume hand-in at pickup point for trial tariff, configurable later. Waybills remain manual.
- Real CDEK API adapter remains the shipping source; no fabricated quotes in the runnable storefront. Investigate official sandbox access. Missing API access must be reported honestly and recoverably.
- Existing vendor map may need Yandex key; a searchable list using official CDEK data is a functional fallback, not manual code entry only.
- Legal identity and addresses remain the owner's facts to fill; do not invent them or undo unrelated user deletions.

## Testing Decisions
Verify the full browser cart-to-payment route, cancellation/retry and displayed amounts; server tests protect ownership, idempotence, CSRF, quote validity and separation of test payments from money. Exercise live/sandbox CDEK read-only requests if official access is available and report separately from mock tests.

## Out of Scope
Real charges, issuing waybills, deployment, legal identity invention and fiscal receipts for fictional sales.

## Further Notes
The owner says both provider accounts are being connected. No API keys were provided. Preserve previous user deletions, including other tracker directories.
