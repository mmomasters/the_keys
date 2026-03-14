"""Test the lock entity."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.the_keys.lock import TheKeysLockEntity
from custom_components.the_keys.the_keyspy.devices.lock import (
    CLOSED,
    OPENED,
    JAMMED,
    TheKeysLock,
)


def _make_mock_device(is_locked=False, is_jammed=False, is_unlocked=False, name="Test Lock", device_id=42):
    """Build a mock TheKeysLock device."""
    device = MagicMock(spec=TheKeysLock)
    device.name = name
    device.id = device_id
    device.is_locked = is_locked
    device.is_jammed = is_jammed
    device.is_unlocked = is_unlocked
    device.battery_level = 85
    return device


def _make_mock_coordinator(device):
    """Build a minimal mock coordinator whose data list contains the given device."""
    coordinator = MagicMock()
    coordinator.data = [device]
    coordinator.async_request_refresh = AsyncMock()
    return coordinator


# ──────────────────────────────────────────────────────────────
# Basic property tests
# ──────────────────────────────────────────────────────────────

def test_lock_entity_properties_locked():
    """Entity properties reflect the underlying device when locked."""
    device = _make_mock_device(is_locked=True)
    coordinator = _make_mock_coordinator(device)
    entity = TheKeysLockEntity(coordinator, device)

    assert entity.is_locked is True
    assert entity.is_jammed is False
    assert entity.available is True
    assert entity._attr_unique_id == f"{device.id}_lock"


def test_lock_entity_properties_unlocked():
    """Entity properties reflect the underlying device when unlocked."""
    device = _make_mock_device(is_locked=False)
    coordinator = _make_mock_coordinator(device)
    entity = TheKeysLockEntity(coordinator, device)

    assert entity.is_locked is False
    assert entity.is_jammed is False


def test_lock_entity_properties_jammed():
    """Entity properties reflect jammed state correctly."""
    device = _make_mock_device(is_jammed=True)
    coordinator = _make_mock_coordinator(device)
    entity = TheKeysLockEntity(coordinator, device)

    assert entity.is_jammed is True


# ──────────────────────────────────────────────────────────────
# async_lock / async_unlock
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_async_lock_calls_device_close():
    """async_lock() should call device.close() via executor."""
    device = _make_mock_device(is_locked=False)
    coordinator = _make_mock_coordinator(device)
    entity = TheKeysLockEntity(coordinator, device)
    entity.hass = MagicMock()
    entity.hass.async_add_executor_job = AsyncMock(return_value=None)
    entity.async_write_ha_state = MagicMock()

    with patch("asyncio.sleep", new_callable=AsyncMock):
        await entity.async_lock()

    entity.hass.async_add_executor_job.assert_awaited_once_with(device.close)
    entity.async_write_ha_state.assert_called()
    coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_unlock_calls_device_open():
    """async_unlock() should call device.open() via executor."""
    device = _make_mock_device(is_locked=True)
    coordinator = _make_mock_coordinator(device)
    entity = TheKeysLockEntity(coordinator, device)
    entity.hass = MagicMock()
    entity.hass.async_add_executor_job = AsyncMock(return_value=None)
    entity.async_write_ha_state = MagicMock()

    with patch("asyncio.sleep", new_callable=AsyncMock):
        await entity.async_unlock()

    entity.hass.async_add_executor_job.assert_awaited_once_with(device.open)
    entity.async_write_ha_state.assert_called()
    coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_lock_raises_on_error():
    """async_lock() should raise HomeAssistantError if device.close raises."""
    from homeassistant.exceptions import HomeAssistantError

    device = _make_mock_device()
    coordinator = _make_mock_coordinator(device)
    entity = TheKeysLockEntity(coordinator, device)
    entity.hass = MagicMock()
    entity.hass.async_add_executor_job = AsyncMock(side_effect=RuntimeError("boom"))

    with pytest.raises(HomeAssistantError):
        await entity.async_lock()


@pytest.mark.asyncio
async def test_async_unlock_raises_on_error():
    """async_unlock() should raise HomeAssistantError if device.open raises."""
    from homeassistant.exceptions import HomeAssistantError

    device = _make_mock_device()
    coordinator = _make_mock_coordinator(device)
    entity = TheKeysLockEntity(coordinator, device)
    entity.hass = MagicMock()
    entity.hass.async_add_executor_job = AsyncMock(side_effect=RuntimeError("boom"))

    with pytest.raises(HomeAssistantError):
        await entity.async_unlock()


# ──────────────────────────────────────────────────────────────
# _handle_coordinator_update
# ──────────────────────────────────────────────────────────────

def test_handle_coordinator_update_refreshes_device():
    """_handle_coordinator_update() should swap the device reference for the newly-polled one."""
    old_device = _make_mock_device(is_locked=False, device_id=42)
    new_device = _make_mock_device(is_locked=True, device_id=42)  # same ID, new state

    coordinator = _make_mock_coordinator(new_device)
    entity = TheKeysLockEntity(coordinator, old_device)
    entity.async_write_ha_state = MagicMock()

    entity._handle_coordinator_update()

    # After the update the entity should be using the new device object
    assert entity._device is new_device
    entity.async_write_ha_state.assert_called_once()


# ──────────────────────────────────────────────────────────────
# Device-level unit tests (TheKeysLock)
# ──────────────────────────────────────────────────────────────

def test_lock_device_is_locked_when_closed():
    """TheKeysLock.is_locked returns True only when status is CLOSED."""
    from custom_components.the_keys.the_keyspy.devices.lock import TheKeysLock

    gateway = MagicMock()
    lock = TheKeysLock(1, gateway, "Front Door", "ABCD", "secret")

    lock._status = CLOSED
    assert lock.is_locked is True
    assert lock.is_unlocked is False
    assert lock.is_jammed is False


def test_lock_device_is_unlocked_when_opened():
    """TheKeysLock.is_unlocked returns True only when status is OPENED."""
    from custom_components.the_keys.the_keyspy.devices.lock import TheKeysLock

    gateway = MagicMock()
    lock = TheKeysLock(1, gateway, "Front Door", "ABCD", "secret")

    lock._status = OPENED
    assert lock.is_unlocked is True
    assert lock.is_locked is False
    assert lock.is_jammed is False


def test_lock_device_is_jammed():
    """TheKeysLock.is_jammed returns True when the device is jammed."""
    from custom_components.the_keys.the_keyspy.devices.lock import TheKeysLock

    gateway = MagicMock()
    lock = TheKeysLock(1, gateway, "Front Door", "ABCD", "secret")

    lock._status = JAMMED
    assert lock.is_jammed is True
    assert lock.is_locked is False
    assert lock.is_unlocked is False


def test_lock_device_retrieve_infos_sets_status():
    """retrieve_infos() correctly maps API response status to internal _status."""
    from custom_components.the_keys.the_keyspy.devices.lock import TheKeysLock

    gateway = MagicMock()
    gateway.locker_status.return_value = {
        "status": "Door closed",
        "code": 50,
        "version": 81,
        "position": 4,
        "rssi": -47,
        "battery": 8097,
    }
    lock = TheKeysLock(1, gateway, "Front Door", "ABCD", "secret")
    lock.retrieve_infos()

    assert lock._status == CLOSED
    assert lock.is_locked is True


def test_lock_device_retrieve_infos_door_open():
    """retrieve_infos() correctly maps 'Door open' API response."""
    from custom_components.the_keys.the_keyspy.devices.lock import TheKeysLock

    gateway = MagicMock()
    gateway.locker_status.return_value = {
        "status": "Door open",
        "code": 50,
        "version": 81,
        "position": 4,
        "rssi": -47,
        "battery": 8097,
    }
    lock = TheKeysLock(1, gateway, "Front Door", "ABCD", "secret")
    lock.retrieve_infos()

    assert lock._status == OPENED
    assert lock.is_unlocked is True
    assert lock.is_locked is False
