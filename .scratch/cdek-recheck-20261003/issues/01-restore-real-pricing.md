# Restore actual CDEK checkout prices

Status: blocked

Read the parent spec for current live evidence. The code already sends validated
origin and destination PVZ codes. The shared CDEK sandbox returns HTTP 500 even
for the tariff list without any shipment parameters. The public store separately
returns the sender-location error; its deployed release/settings need inspection.

## Acceptance

- TLT3, city 431, is the effective origin on the intended site.
- The carrier returns an actual price and delivery period for several routes.
- Selecting a PVZ updates the checkout shipping amount and total.
- No synthetic price is presented as a carrier tariff.

## Comments

2026-10-03: Browser flow and three actual API routes checked; 45 integration tests
passed. No successful live quote obtained. Waiting for clarification about the
owner's private API credentials and access to the installed server environment.

2026-10-03 follow-up: Owner confirms test credentials only. Production credentials
are not available. Await sandbox recovery or a working example/access supplied
by CDEK support; do not treat enabling synthetic demo prices as resolution.
