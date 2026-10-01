# 02 — Select CDEK pickup point and obtain quote
Status: done
Blocked by: None

What to build: functional searchable CDEK pickup selection from official data, alongside optional official map, so the checkout works without requiring customers to know pickup codes. Preserve real server calculation and quote signing.

- [x] Customer searches by city and selects a real office from the results.
- [x] Server retrieves official CDEK data with bounded inputs and no arbitrary URL proxy.
- [x] Selected pickup triggers the existing verified quote and total refresh.
- [x] Errors, missing API configuration and expired quotes are recoverable.
- [x] Shipping prices are never fabricated in the runtime storefront.
- [x] Focused server/browser tests cover selection and quote binding.

Parent verification: all seven CDEK/customer browser scenarios pass, and an unmocked official sandbox city→PVZ→quote→trial-payment journey passes at 1440/390 px. Total 1290 + 252 = 1542 RUB is preserved. Office list is scrollable and collapses after selection; change-point action restores the selected keyboard focus.

## Comments

2026-10-01: Implemented city search (`/checkout/cdek/cities/`) and a paginated office directory (`/checkout/cdek/offices/`), native city selection, labeled radio rows with automatic signed quotes, optional map and manual-code fallback. Requests are bounded, rate-limited, cached by API identity and use only fixed official routes. Pending responses cannot restore a quote after another selection; keyboard arrow navigation is debounced before calculation. Missing credentials and provider errors leave contacts/cart intact.

Calculator now requires the official `total_sum`, which includes VAT/services. A successful live sandbox probe reported `delivery_sum=210` and `total_sum=252`; the latter is the payable delivery amount. Parent agent independently verified official city, office and calculator responses using the published sandbox credentials. No runtime fixtures or fabricated prices were added.

Verification: `manage.py test orders.test_cdek_selection orders.test_cdek --settings=config.settings_test --noinput`: 24 passed. Ruff, JS syntax and whitespace checks passed. Browser tests added for desktop/mobile selection, keyboard flow, contact-preserving retry and invalidation; integrated browser/visual run is owned by the parent agent and pending at this handoff. Referenced `/tdd` and `/code-review` skills are absent locally; focused test-first work and manual code review completed instead. No commit created as requested.

Official city endpoint/filter reference: [CDEK SDK LocationCities](https://github.com/cdek-it/sdk2.0/blob/master/src/Actions/LocationCities.php); [CDEK API documentation](https://apidoc.cdek.ru/).
