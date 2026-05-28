"""HMAC-SHA256 signing for the Process Guardian webhook payload."""

from __future__ import annotations

import hashlib
import hmac


def sign_payload(payload: str, secret: str) -> str:
    """Return the ``sha256=<hex>`` HMAC-SHA256 signature for *payload*.

    The signature is computed over the UTF-8 encoded payload bytes and matches
    the format verified by the ``x-hub-signature-256`` header on the server.

    Args:
        payload: The JSON request body as a plain string.
        secret:  The shared HMAC secret configured in ``commit-check.env``.

    Returns:
        A string of the form ``sha256=<lowercase hex digest>``.
    """
    digest = hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"sha256={digest}"
