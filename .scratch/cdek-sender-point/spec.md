# Explicit CDEK sender PVZ

Status: done

The owner specified TLT3 in Tolyatti, ul. 70 let Oktyabrya 31a, 105 and requested a real API recheck before launch. Add CDEK_FROM_PVZ_CODE, validate reception availability and its city against CDEK_FROM_CITY_CODE, send shipment_point and sender address alongside the recipient delivery_point. Preserve the origin in signed quotes/orders and invalidate quotes on origin changes. Respect weight restrictions at both ends. Activate TLT3 locally and disable the synthetic quote mode for real verification. Do not enable live credentials or banking.

Initial direct sandbox evidence: TLT3 is ACTIVE and accepts shipments at the specified address. Explicit shipment_point changes sender-not-recognized to recipient-not-recognized; both point codes cause HTTP 500 v2_internal_error / 0xBC236B02. These are diagnostic findings, not a successful tariff quote.

## Result

Implemented and enabled locally with demo pricing disabled. Verified full application CdekClient against MOS4, TLT2 and SPB1: all return HTTP 500 v2_internal_error / 0xBC236B02 after successful point lookups. Carrier pricing is still unavailable; production readiness is not established. Focused tests: 50 passed. Full local Django suite: 371 discovered, 369 passed, two environment-specific skips (includes pre-existing untracked tests). Ruff passed; no migrations required.
