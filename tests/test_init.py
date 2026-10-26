"""Tests for the The Keys integration setup helpers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.the_keys import _host_is_alive


class _FakeProc:
    def __init__(self, returncode: int) -> None:
        self._returncode = returncode

    async def wait(self) -> int:
        return self._returncode


def _tcp_fails():
    return patch(
        "custom_components.the_keys.asyncio.open_connection",
        new=AsyncMock(side_effect=OSError("connection refused")),
    )


@pytest.mark.asyncio
async def test_tcp_connect_success_skips_ping():
    """A host accepting TCP on the gateway port is alive without pinging."""
    writer = MagicMock()
    with patch(
        "custom_components.the_keys.asyncio.open_connection",
        new=AsyncMock(return_value=(MagicMock(), writer)),
    ) as mock_conn, patch(
        "custom_components.the_keys.asyncio.create_subprocess_exec",
        new=AsyncMock(),
    ) as mock_exec:
        assert await _host_is_alive("192.168.1.50:8080") is True
        assert mock_conn.call_args.args == ("192.168.1.50", 8080)
        writer.close.assert_called_once()
        mock_exec.assert_not_called()


@pytest.mark.asyncio
async def test_falls_back_to_ping_when_tcp_fails():
    """TCP failing but ping answering still counts as alive (HTTP frozen, network up)."""
    with _tcp_fails(), patch(
        "custom_components.the_keys.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=_FakeProc(0)),
    ) as mock_exec:
        assert await _host_is_alive("192.168.1.50:8080") is True
        # ICMP has no port — the hostname passed to ping must not include it.
        assert mock_exec.call_args.args[-1] == "192.168.1.50"


@pytest.mark.asyncio
async def test_returns_false_when_neither_tcp_nor_ping_answers():
    """No TCP connect and no ping reply returns False so reboot is skipped."""
    with _tcp_fails(), patch(
        "custom_components.the_keys.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=_FakeProc(1)),
    ):
        assert await _host_is_alive("10.0.0.1") is False


@pytest.mark.asyncio
async def test_assumes_reachable_when_ping_binary_missing():
    """If TCP fails and ping is unavailable, assume reachable to not block reboots."""
    with _tcp_fails(), patch(
        "custom_components.the_keys.asyncio.create_subprocess_exec",
        new=AsyncMock(side_effect=FileNotFoundError("ping")),
    ):
        assert await _host_is_alive("10.0.0.1") is True
