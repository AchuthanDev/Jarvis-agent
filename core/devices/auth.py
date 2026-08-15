"""Device token generation and verification."""

from __future__ import annotations

import hmac
import secrets
from hashlib import sha256


def generate_device_token() -> str:
    """Return a new opaque bearer token for a companion agent."""
    return secrets.token_urlsafe(32)


def hash_device_token(token: str, secret_key: str) -> str:
    """Hash a device token with the server secret before storing it."""
    return hmac.new(secret_key.encode(), token.encode(), sha256).hexdigest()


def verify_device_token(token: str, token_hash: str | None, secret_key: str) -> bool:
    if not token_hash:
        return False
    expected = hash_device_token(token, secret_key)
    return hmac.compare_digest(expected, token_hash)
