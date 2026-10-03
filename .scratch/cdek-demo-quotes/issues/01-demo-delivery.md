# Implement explicit demo delivery quotes

Status: done

Implement the opt-in mode, signed quote invalidation, permanent bank-payment exclusion, visible labels, tests and deployment instructions described in the parent spec.

## Result

Implemented and verified; see spec verification. Settings and VPS instructions: `docs/CDEK-DEMO-DELIVERY.md`. Genuine carrier API remains untouched and continues to report calculator failures; synthetic pricing is explicitly opted into and cannot enter bank payments.
