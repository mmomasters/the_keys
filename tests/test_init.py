"""Tests for the The Keys integration setup helpers."""

from unittest.mock import AsyncMock, patch

import pytest

from custom_components.the_keys import _host_responds_to_ping


class _FakeProc:
    def __init__(self, returncode: int) -> None:
        self._returncode = returncode

    async def wait(self) -> int:
        return self._returncode


@pytest.mark.asyncio
async def test_ping_strips_port_and_returns_true_on_success():
    """A host that answers ping returns True, and the port is stripped off."""
    with patch(
        "custom_components.the_keys.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=_FakeProc(0)),
    ) as mock_exec:
        assert await _host_responds_to_ping("192.168.1.50:8080") is True
        # ICMP has no port — the hostname passed to ping must not include it.
        assert mock_exec.call_args.args[-1] == "192.168.1.50"


@pytest.mark.asyncio
async def test_ping_returns_false_when_host_does_not_answer():
    """A non-zero ping exit code (no reply) returns False so reboot is skipped."""
    with patch(
        "custom_components.the_keys.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=_FakeProc(1)),
    ):
        assert await _host_responds_to_ping("10.0.0.1") is False


@pytest.mark.asyncio
async def test_ping_assumes_reachable_when_binary_missing():
    """If the ping binary is unavailable, assume reachable to not block reboots."""
    with patch(
        "custom_components.the_keys.asyncio.create_subprocess_exec",
        new=AsyncMock(side_effect=FileNotFoundError("ping")),
    ):
        assert await _host_responds_to_ping("10.0.0.1") is True
