"""Tests for companion device token helpers."""

from core.devices.auth import generate_device_token, hash_device_token, verify_device_token


def test_generated_tokens_are_unique() -> None:
    assert generate_device_token() != generate_device_token()


def test_token_hash_verification() -> None:
    token = "device-token"
    token_hash = hash_device_token(token, "server-secret")

    assert verify_device_token(token, token_hash, "server-secret")
    assert not verify_device_token("wrong", token_hash, "server-secret")
    assert not verify_device_token(token, token_hash, "other-secret")
