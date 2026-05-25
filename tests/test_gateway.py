"""Tests for the gateway error type."""

import pytest

from custom_components.the_keys.the_keyspy.devices.gateway import GatewayError


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
