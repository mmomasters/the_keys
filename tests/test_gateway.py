"""Tests for the gateway error type."""

import pytest

from custom_components.the_keys.the_keyspy.devices.gateway import GatewayError
from custom_components.the_keys.the_keyspy.errors import (
    GatewayUnreachableError,
    TheKeysApiError,
)


def test_gateway_error_exposes_code():
    """GatewayError extracts the numeric code from the gateway 'ko' payload."""
    err = GatewayError({"status": "ko", "code": 38, "error": "clock skew"})
    assert err.code == 38
    assert err.payload == {"status": "ko", "code": 38, "error": "clock skew"}


def test_gateway_error_code_none_when_absent():
    """Code is None when the payload carries no 'code' (or isn't a dict)."""
    assert GatewayError({"status": "ko"}).code is None
    assert GatewayError("opaque message").code is None


def test_gateway_error_is_runtimeerror_and_renders_payload():
    """Backwards compatible: still a RuntimeError and str() shows the payload."""
    err = GatewayError({"status": "ko", "code": 500})
    assert isinstance(err, RuntimeError)
    assert "500" in str(err)


def test_gateway_error_caught_as_runtimeerror():
    """Existing ``except RuntimeError`` / pytest.raises(RuntimeError) keep working."""
    with pytest.raises(RuntimeError):
        raise GatewayError({"status": "ko", "code": 33})


def test_gateway_unreachable_error_carries_host_and_original():
    """GatewayUnreachableError exposes the host and the wrapped requests exception."""
    original = TimeoutError("read timed out")
    err = GatewayUnreachableError("192.168.1.50:1234", original)
    assert err.host == "192.168.1.50:1234"
    assert err.original is original
    assert "192.168.1.50:1234" in str(err)


def test_gateway_unreachable_error_is_connectionerror():
    """Subclasses ConnectionError (and TheKeysApiError) so existing handlers catch it."""
    err = GatewayUnreachableError("h", OSError("boom"))
    assert isinstance(err, ConnectionError)
    assert isinstance(err, OSError)  # ConnectionError is an OSError subclass
    assert isinstance(err, TheKeysApiError)
    # The coordinator's lock loop catches (ConnectionError, ...) — confirm it would match.
    with pytest.raises(ConnectionError):
        raise GatewayUnreachableError("h", OSError("boom"))
