"""The Keys Lock device."""
import logging

from homeassistant.components.lock import LockEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform
from the_keyspy import TheKeysLock

from .base import TheKeysEntity
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SERVICE_CALIBRATE = "calibrate"
SERVICE_SYNC = "sync"


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up TheKeys lock devices."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    if not coordinator.data:
        return

    entities = []
    for device in coordinator.data:
        if isinstance(device, TheKeysLock):
            entities.append(TheKeysLockEntity(device))

    async_add_entities(entities, update_before_add=True)

    # Register custom services
    platform = entity_platform.async_get_current_platform()
    
    platform.async_register_entity_service(
        SERVICE_CALIBRATE,
        {},
        "async_calibrate",
    )
    
    platform.async_register_entity_service(
        SERVICE_SYNC,
        {},
        "async_sync",
    )


class TheKeysLockEntity(TheKeysEntity, LockEntity):
    """TheKeys lock device implementation."""

    def __init__(self, device: TheKeysLock):
        """Init a TheKeys lock entity."""
        super().__init__(device=device)
        self._attr_unique_id = f"{self._device.id}_lock"

    def lock(self, **kwargs):
        """Lock the device."""
        self._device.close()
        self._attr_is_locked = True

    def unlock(self, **kwargs):
        """Unlock the device."""
        self._device.open()
        self._attr_is_locked = False

    def update(self) -> None:
        """Update the device."""
        try:
            self._device.retrieve_infos()
            self._attr_is_locked = self._device.is_locked
        except Exception as e:
            _LOGGER.error("Error updating lock: %s", e)

    async def async_calibrate(self) -> None:
        """Calibrate the lock."""
        try:
            if hasattr(self._device, 'calibrate'):
                await self.hass.async_add_executor_job(self._device.calibrate)
                _LOGGER.info("Calibrate command sent to %s", self._device.name)
            else:
                _LOGGER.warning("Calibrate method not available for %s", self._device.name)
        except Exception as err:
            _LOGGER.error("Error calibrating %s: %s", self._device.name, err)
            raise

    async def async_sync(self) -> None:
        """Sync the lock state."""
        try:
            if hasattr(self._device, 'sync'):
                await self.hass.async_add_executor_job(self._device.sync)
                _LOGGER.info("Sync command sent to %s", self._device.name)
            elif hasattr(self._device, 'retrieve_infos'):
                await self.hass.async_add_executor_job(self._device.retrieve_infos)
                _LOGGER.info("Sync (retrieve_infos) command sent to %s", self._device.name)
            else:
                _LOGGER.warning("Sync method not available for %s", self._device.name)
        except Exception as err:
            _LOGGER.error("Error syncing %s: %s", self._device.name, err)
            raise
