"""Expiring, order-scoped bearer links. UUID knowledge alone never grants access."""

from django.conf import settings
from django.core import signing
from django.utils.crypto import constant_time_compare, salted_hmac

SALT = "orders.email-access.v1"
SESSION_KEY = "order_email_access"


def identity(order):
    return salted_hmac(SALT, f"{order.public_id}:{order.email.casefold()}:{order.access_version}").hexdigest()


def make_access_token(order):
    return signing.dumps({"order": str(order.public_id), "identity": identity(order)}, salt=SALT)


def valid_access_token(order, token):
    if not isinstance(token, str) or len(token) > 512:
        return False
    try:
        data = signing.loads(token, salt=SALT, max_age=settings.ORDER_EMAIL_LINK_MAX_AGE)
        return (
            isinstance(data, dict)
            and data.get("order") == str(order.public_id)
            and isinstance(data.get("identity"), str)
            and constant_time_compare(data["identity"], identity(order))
        )
    except signing.BadSignature:
        return False


def has_email_access(request, order):
    grants = request.session.get(SESSION_KEY, {})
    return isinstance(grants, dict) and valid_access_token(order, grants.get(str(order.public_id)))


def grant_email_access(request, order, token):
    grants = request.session.get(SESSION_KEY, {})
    if not isinstance(grants, dict):
        grants = {}
    # Bound session growth; expiry/signature are rechecked on every access.
    grants.pop(str(order.public_id), None)
    grants = dict(list(grants.items())[-19:])
    grants[str(order.public_id)] = token
    request.session[SESSION_KEY] = grants
