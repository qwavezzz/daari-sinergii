# Linux release and operations

The production target is Ubuntu 24.04 LTS, Python 3.12 (Ubuntu security updates), PostgreSQL 16, Nginx from the Ubuntu security repository, Node.js 22 LTS for builds only, and the exact Python/npm dependencies in the repository. Local Windows validation uses Python 3.14 and explicit SQLite development settings. PostgreSQL is mandatory in production; concurrency acceptance must run against PostgreSQL.

## First installation

1. Prepare a VPS with SSH, a restricted deployment account, backups, monitoring and DNS for the main and shop hosts. Run `sudo bash deploy/bootstrap.sh`. Install a verified Node.js 22 distribution. Create a dedicated PostgreSQL role/database with no superuser or database-creation rights. Bind PostgreSQL to loopback; close external port 5432.
2. Fill `/etc/dari/dari.env` from `.env.example`. Generate a random Django secret. Keep the file `root:dari`, mode `0640`, outside releases and static directories. `EnvironmentFile` does not execute shell substitutions; use proper systemd quoting for JSON. Never commit the completed file.
3. Configure PostgreSQL backup access through `PGSERVICE`, `PGSERVICEFILE` and a private `PGPASSFILE` (mode `0600`). The service file identifies the same database as `DATABASE_URL`. Set these environment variables for `dari-backup.service` in the env file. Credentials are not passed as shell command arguments.
4. Obtain a Let's Encrypt certificate for all three configured names (main, www, shop). Use a temporary HTTP-only ACME virtual host before installing the final TLS config. Disable Ubuntu's example default server so there is exactly one `default_server`. Nginx must support the `http2 on` directive; on Ubuntu's older Nginx 1.24 replace it with `listen 443 ssl http2` and remove `http2 on`.
5. Prepare an immutable checkout in `/srv/dari/releases/<release-id>`, then run `sudo bash deploy/release.sh /srv/dari/releases/<release-id>`. The script creates the venv, installs locked dependencies, builds assets, checks production settings, backs up an existing installation, migrates, installs roles, collects static files, switches the release and verifies both hosts. Do not run migration procedures concurrently.
6. On the initial release run `manage.py import_legacy_content` with the production environment to import original content and protected documents, then create a superuser. Both commands must run under the `dari` account and the same environment (`systemd-run` pattern in `release.sh`). Do not place admin/session cookies on a shared parent domain.

## Enabling orders and payment

The store initially has no products, prices, delivery promises or legal texts. Add real SKUs, confirmed prices, images, stock and product tax codes in Admin. Add the agreed `DeliveryMethod` records with explicit prices, publish terms/privacy/delivery texts in `StoreSettings`, enable its checkout toggle, and set `CHECKOUT_ENABLED=true`. Both switches and the required documents are checked on the server.

Use a YooKassa test shop first. Set its credentials, `YOOKASSA_ENABLED=true` and `YOOKASSA_TEST_MODE=true`; register `/payments/yookassa/webhook/` on the shop domain for payment succeeded/canceled/waiting_for_capture and refund succeeded. No card data is accepted by Django. Callback payloads are untrusted hints: authenticated provider requests verify the shop account, order UUID, amount, currency, test flag and status before changing finances. Returning to an order page does not establish payment; its protected POST refresh and the reconciliation timer verify it.

Do not enable live payments until the seller, agreement, delivery, tax rates, receipt timing and return process have been agreed and tested. Live mode additionally requires `YOOKASSA_LIVE_APPROVED=true` and `YOOKASSA_RECEIPT_MODE=provider` or `external`. Provider mode currently supports product receipts with explicitly configured VAT codes and rejects paid delivery until delivery fiscalization has been implemented for the approved scheme. `external` is only for an approved externally operated cash register; no external fiscalization integration is included here. This is a launch dependency, not a free-delivery default.

Refunds are performed in the YooKassa dashboard; authenticated webhook/reconciliation imports their confirmed state. Admin cannot set a financial status. A refund does not automatically return goods to stock. Order fulfillment transitions use guarded Admin actions. Orders and payment history cannot be deleted through Admin.

## Routine operation

The static locations explicitly enable gzip for CSS/JavaScript/SVG. Verify `nginx -t` before reload,
then request an actual hashed JS/CSS URL with `Accept-Encoding: gzip` and check `Content-Encoding: gzip`
and `Vary: Accept-Encoding`. Local Django development measurements do not include this saving.
Private HTML/API response compression is not enabled by these static-location directives.

`dari-reconcile.timer` checks payment attempts, retries unknown creation with its original payload/key only within a conservative 23-hour window (provider guarantee: 24 hours), imports refunds and releases only reserves without unresolved payments. An unknown payment beyond that window keeps its reservation and flags the order for manual review. Do not create a replacement payment until its outcome is established. Delayed successful payments are retained and stock conflicts are visible in Admin. Confirmed successful status never regresses.

`dari-notifications.timer` retries durable notification records. SMTP errors never roll back orders or money. A stable Message-ID reduces duplicates, but ordinary SMTP cannot guarantee exactly-once delivery if the process dies after the mail server accepted a message. The order/payment state itself is idempotent.

Monitor `systemctl status dari*`, `journalctl -u dari`, both `/health/` endpoints, failed timers, disk space, certificate expiry, orders needing attention, stale payment checks and unsent notifications. Logs exclude credentials and provider/card payloads. Run `clearsessions` regularly and arrange retention of expired carts/rate buckets according to the agreed personal-data policy.

## Backups, restore drill and rollback

The backup timer makes a PostgreSQL custom-format dump and an archive of public/private uploads outside web roots. Configure encrypted off-server copy and retention with the chosen storage provider before launch. Local copies alone are insufficient. For a consistent recovery point during active uploads/orders, run the pre-release copy under a maintenance window or use database point-in-time recovery plus versioned/object storage; a sequential SQL/media dump is not a cross-system atomic snapshot.

Test restoration into a **separate** PostgreSQL database and separate media directories: verify SHA256 checksums, create the empty restore database, run `pg_restore --no-owner --no-privileges` into that database, extract the archive into the separate restore directory, run Django checks and compare content, orders, payment IDs and all document checksums. Do not connect a restore drill to live payment credentials or email delivery. Record restore duration and recovered order timestamps; agree RPO/RTO before launch.

To roll back application code, first check database migration compatibility, point `/srv/dari/current` to `/srv/dari/previous`, and restart Gunicorn. Keep old hashed static assets until all relevant releases and browser caches have expired. Do not run `collectstatic --clear` during release. Never overwrite the live database with an old dump after orders have arrived. Use forward migrations or a reviewed data-preserving recovery process. DNS/domain switching, backup restoration and real payment tests remain deployment acceptance tasks on the actual server.

References: [Django deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/), [Django 5.2.17 security release](https://www.djangoproject.com/weblog/2026/aug/04/security-releases/), [YooKassa notifications](https://yookassa.ru/developers/using-api/webhooks), [YooKassa idempotency](https://yookassa.ru/developers/using-api/interaction-format).
