"""HMAC-SHA256 webhook payload signing and verification."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any


class WebhookSigner:
    """Signs and verifies webhook payloads using HMAC-SHA256.

    The signature is computed over the raw JSON bytes of the payload
    using the endpoint's shared secret.

    Usage::

        signer = WebhookSigner(secret="whsec_abc123")
        sig = signer.sign(payload)
        assert signer.verify(payload, sig)
    """

    HEADER_NAME = "X-Webhook-Signature"
    TIMESTAMP_HEADER = "X-Webhook-Timestamp"

    def __init__(self, secret: str) -> None:
        if not secret:
            raise ValueError("Signing secret must not be empty")
        self._secret = secret.encode("utf-8")

    def sign(self, payload: dict[str, Any], timestamp: str | None = None) -> str:
        """Produce an HMAC-SHA256 hex-digest for *payload*.

        Args:
            payload: JSON-serialisable dict to sign.
            timestamp: Optional ISO-8601 timestamp prepended to the
                signing body for replay-attack mitigation.

        Returns:
            Hex-encoded HMAC-SHA256 signature prefixed with ``sha256=``.
        """
        body = self._canonical_body(payload, timestamp)
        digest = hmac.new(self._secret, body, hashlib.sha256).hexdigest()
        return f"sha256={digest}"

    def verify(
        self,
        payload: dict[str, Any],
        signature: str,
        timestamp: str | None = None,
    ) -> bool:
        """Verify that *signature* matches the expected HMAC for *payload*.

        Uses :func:`hmac.compare_digest` for constant-time comparison.
        """
        expected = self.sign(payload, timestamp)
        return hmac.compare_digest(expected, signature)

    @staticmethod
    def _canonical_body(
        payload: dict[str, Any], timestamp: str | None = None
    ) -> bytes:
        """Build the canonical byte-string used for signing."""
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        if timestamp:
            raw = f"{timestamp}.{raw}"
        return raw.encode("utf-8")
