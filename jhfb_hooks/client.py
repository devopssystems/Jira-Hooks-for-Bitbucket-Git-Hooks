"""HTTP client for sending the commit-check request to the Process Guardian endpoint."""

from __future__ import annotations

import requests


def send_check(url: str, payload: str, signature: str) -> tuple[int, dict[str, object]]:
    """POST *payload* to *url* with the HMAC *signature* header.

    Args:
        url:       The Process Guardian web-trigger URL (including ``?repoSlug=`` if needed).
        payload:   The JSON request body produced by :func:`~jhfb_hooks.payload.build_payload`.
        signature: The ``sha256=<hex>`` value produced by :func:`~jhfb_hooks.signer.sign_payload`.

    Returns:
        A ``(status_code, response_body)`` tuple where *response_body* is the
        parsed JSON dict, or ``{}`` if the response could not be decoded.

    Raises:
        requests.exceptions.RequestException: On network or connection errors.
    """
    response = requests.post(
        url,
        data=payload.encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-hub-signature-256": signature,
        },
        timeout=30,
    )
    try:
        body: dict[str, object] = response.json()
    except Exception:  # noqa: BLE001
        body = {}
    return response.status_code, body
