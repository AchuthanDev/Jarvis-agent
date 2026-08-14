"""Tests for audit redaction."""

from __future__ import annotations

from core.audit.record import redact_parameters


def test_redacts_only_listed_keys() -> None:
    params = {"query": "hello", "password": "secret", "token": "abc"}
    redacted = redact_parameters(params, ("password", "token"))
    assert redacted == {"query": "hello", "password": "[redacted]", "token": "[redacted]"}


def test_no_redact_leaves_parameters_unchanged() -> None:
    params = {"query": "hello"}
    assert redact_parameters(params, ()) == {"query": "hello"}


def test_missing_keys_are_ignored() -> None:
    params = {"query": "hello"}
    assert redact_parameters(params, ("password",)) == {"query": "hello"}
