# Checkout and delivery

Status: in progress

Implement requested phone examples and email blur validation; diagnose actual delivery failure and add regression coverage for its cause.

## Result

Phone and email corrections are implemented and browser-verified. Public checkout failure reproduced; sandbox API returns `v2_sender_location_not_recognized` and an empty city directory, including Moscow and Tolyatti. Confirmed independently with the public sandbox account, both with and without insurance. Added precise error classification and CLI diagnosis. User explicitly chose to retain sandbox (no live credentials). External recovery remains unverified; do not label delivery fixed.

## Follow-up: sender configuration and working reference

The owner confirmed `CDEK_FROM_CITY_CODE=431` in the actual VPS environment.

Current soft-wear.ru checkout was inspected in a clean browser session through a normal product/cart/PVZ flow, without placing an order. Its server returned 504 Moscow pickup points and a quote of 470 RUB / 1–2 days for one cap, with no fallback flag. Browser-visible requests go to its own `/api/cdek/*`; its upstream environment and credentials cannot be established from those responses. Its existing demo fallback code was not the path used in this check. Do not describe this reference as a fake integration or claim its production mode is proven.

Additional direct sandbox checks:

- `location/suggest/cities` successfully finds Tolyatti (431) and Moscow (44), while `location/cities` returns an empty list. The earlier general description of an entirely unavailable city directory was too broad.
- Numeric city codes: sender location not recognized.
- Add `shipment_point=TLT1`: recipient location not recognized.
- Add both `shipment_point=TLT1` and `delivery_point=MOS4`: HTTP 500, `v2_internal_error` / `0xBC236B02`.
- `calculator/tarifflist` (used by the official widget) and `calculator/tariffAndService` fail the same way.
- `city_uuid` alone is rejected because `code` is required; UUID together with code does not resolve the failure. Names/coordinates without code also fail validation.

Read-only diagnostic results and reference screenshots are in ignored `var/maintenance/`. A ready-to-send report is in `docs/CDEK-SANDBOX-SUPPORT.txt`; no message was sent. Exact upstream root cause remains unconfirmed. Retain the sandbox as requested; do not switch endpoints to production or invent shipping prices.
