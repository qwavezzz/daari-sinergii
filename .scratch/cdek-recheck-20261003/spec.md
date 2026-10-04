# Recheck CDEK pricing from TLT3

Status: blocked

The owner reports failed checkout pricing and confirms the origin as TLT3,
Tolyatti, ul. 70 let Oktyabrya, 31a, 105. Acceptance requires an actual carrier
price in the checkout, not only passing mocked tests or a synthetic demo price.

## Findings

- Sender support already exists in HEAD `80ad082`. Local private settings already
  specify city 431, TLT3 and disabled demo quotes. No credentials were changed.
- The public store is still showing the CDEK test environment. Separate browser
  requests for MOS4, TLT2 and SPB1 return HTTP 422 with the sender-location error.
  Selecting TLT2 through the actual pickup list produces the same error. There
  are no JavaScript exceptions; submission remains disabled without a quote.
- Direct calls with the existing application client authenticate successfully and
  confirm TLT3 and its exact address. Pricing TLT3 → MOS4, TLT2 and SPB1 fails with
  upstream HTTP 500, `v2_internal_error`, `0xBC236B02` on all three routes.
- `GET /v2/calculator/alltariffs`, which has no origin, destination or packages,
  also returns the same HTTP 500. The configured public sandbox credentials match
  CDEK's current official integration:
  https://raw.githubusercontent.com/cdek-it/wordpress/main/src/Config.php
- 45 tests in `apps.orders.test_cdek`, `apps.orders.test_cdek_sender` and
  `apps.orders.test_cdek_errors` passed under `config.settings_test`.
- `.env.example` now includes the confirmed origin. This changes the configuration
  template only; the public server environment has not been inspected or changed.

## Evidence

Local artifacts (ignored by Git):

- `var/artifacts/cdek-recheck-20261003/provider.json`
- `var/artifacts/cdek-recheck-20261003/result.json`
- `var/artifacts/cdek-recheck-20261003/checkout.png`
- `var/artifacts/cdek-recheck-20261003/checkout-mobile.png`
- Reproducers: `var/cdek-provider-recheck.py`, `var/check-cdek-live.mjs`.

Browser checks created only a separate cart, with no order, payment, email or
shipment. API checks only read directories and request calculations.

## Remaining work

The owner confirmed that only test credentials are available. Keep the test
environment; do not ask for production keys again until this changes. Await a
working sandbox service or a supported alternative from CDEK. The exact failing
site and its server configuration still need confirmation. The support request is
`docs/CDEK-SANDBOX-SUPPORT.txt`; it has not been sent.

For the public site, the installed release and effective sender settings still
need checking through an authenticated server session. No usable server session
or SSH key was available in this workspace. Do not claim that TLT3 is set on the
VPS from the local settings alone. Do not enable a flat demo price as a fix.

## Follow-up

2026-10-03: The owner confirmed test-only access. Rechecked the current official
WordPress integration, SDK and widget documentation. The WordPress integration
still publishes the configured account and `api.edu.cdek.ru/v2`; the widget
requires an authenticated API backend rather than supplying an independent
calculator. No working alternative was established. The existing explicit
500 RUB rehearsal is a way to exercise checkout only, not a verified CDEK quote.
