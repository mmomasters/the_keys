"""Test The Keys button platform."""
import pytest
from unittest.mock import MagicMock, patch
from homeassistant.core import HomeAssistant

from custom_components.the_keys.button import (
    TheKeysUnlockButton,
    TheKeysCalibrateButton,
    TheKeysSyncButton,
)


@pytest.fixture
def mock_device():
    """Mock TheKeysLock device."""
    device = MagicMock()
    device.id = "test_lock_123"
    device.name = "Test Lock"
    device.open = MagicMock()
    device.calibrate = MagicMock()
    device.sync = MagicMock()
    device.retrieve_infos = MagicMock()
    return device


async def test_unlock_button(hass: HomeAssistant, mock_device):
    """Test unlock button press."""
    button = TheKeysUnlockButton(mock_device)
    button.hass = hass
    
    assert button.unique_id == "test_lock_123_unlock_button"
    assert button.name == "Test Lock Unlock"
    assert button.icon == "mdi:lock-open"
    
    await button.async_press()
    mock_device.open.assert_called_once()


async def test_calibrate_button(hass: HomeAssistant, mock_device):
    """Test calibrate button press."""
    button = TheKeysCalibrateButton(mock_device)
    button.hass = hass
    
    assert button.unique_id == "test_lock_123_calibrate_button"
    assert button.name == "Test Lock Calibrate"
    assert button.icon == "mdi:tune"
    
    await button.async_press()
    mock_device.calibrate.assert_called_once()


async def test_sync_button(hass: HomeAssistant, mock_device):
    """Test sync button press."""
    button = TheKeysSyncButton(mock_device)
    button.hass = hass
    
    assert button.unique_id == "test_lock_123_sync_button"
    assert button.name == "Test Lock Sync"
    assert button.icon == "mdi:sync"
    
    await button.async_press()
    mock_device.sync.assert_called_once()


async def test_sync_button_fallback(hass: HomeAssistant, mock_device):
    """Test sync button with fallback to retrieve_infos."""
    # Remove sync method to test fallback
    delattr(mock_device, 'sync')
    
    button = TheKeysSyncButton(mock_device)
    button.hass = hass
    
    await button.async_press()
    mock_device.retrieve_infos.assert_called_once()
