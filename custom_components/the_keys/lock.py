"""The Keys Lock device."""
import asyncio
import logging

import requests

from homeassistant.components.lock import LockEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_platform
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .the_keyspy import TheKeysLock
from .the_keyspy.devices import GatewayError

from .base import TheKeysEntity, gateway_is_synchronizing
from .const import DOMAIN

GATEWAY_SYNCING_MSG = (
    "Gateway is synchronizing — try again in a minute."
)

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
            entities.append(TheKeysLockEntity(coordinator, device))

    async_add_entities(entities, update_before_add=False)

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


class TheKeysLockEntity(CoordinatorEntity, TheKeysEntity, LockEntity):
    """TheKeys lock device implementation."""

    def __init__(self, coordinator, device: TheKeysLock):
        """Init a TheKeys lock entity."""
        super().__init__(coordinator)
        TheKeysEntity.__init__(self, device=device)
        self._attr_unique_id = f"{self._device.id}_lock"
        self._device = device

    async def async_lock(self, **kwargs):
        """Lock the device."""
        if await gateway_is_synchronizing(self.hass, self._device):
            raise HomeAssistantError(GATEWAY_SYNCING_MSG)
        try:
            await self.hass.async_add_executor_job(self._device.close)
        except (requests.exceptions.ConnectionError, ConnectionError, OSError) as err:
            _LOGGER.warning("Gateway not responding while locking %s: %s", self._device.name, err)
            raise HomeAssistantError(
                f"Gateway not responding — could not lock {self._device.name}. "
                "Please wait a moment and try again."
            ) from err
        except Exception as err:
            _LOGGER.error("Error locking %s: %s", self._device.name, err)
            raise HomeAssistantError(f"Could not lock {self._device.name}: {err}") from err
        # _device._status is already set to CLOSED by device.close(); write it immediately.
        # Do NOT set _attr_is_locked here — it has no effect because is_locked is a property
        # that reads _device.is_locked, and _attr_is_locked would be silently ignored.
        self.async_write_ha_state()
        # Wait for the lock to physically finish moving (~5s), then force a status refresh
        await asyncio.sleep(6)
        await self.coordinator.async_request_refresh()

    async def async_unlock(self, **kwargs):
        """Unlock the device."""
        if await gateway_is_synchronizing(self.hass, self._device):
            raise HomeAssistantError(GATEWAY_SYNCING_MSG)
        try:
            await self.hass.async_add_executor_job(self._device.open)
        except (requests.exceptions.ConnectionError, ConnectionError, OSError) as err:
            _LOGGER.warning("Gateway not responding while unlocking %s: %s", self._device.name, err)
            raise HomeAssistantError(
                f"Gateway not responding — could not unlock {self._device.name}. "
                "Please wait a moment and try again."
            ) from err
        except Exception as err:
            _LOGGER.error("Error unlocking %s: %s", self._device.name, err)
            raise HomeAssistantError(f"Could not unlock {self._device.name}: {err}") from err
        # _device._status is already set to OPENED by device.open(); write it immediately.
        # Do NOT set _attr_is_locked here — it has no effect because is_locked is a property
        # that reads _device.is_locked, and _attr_is_locked would be silently ignored.
        self.async_write_ha_state()
        # Wait for the lock to physically finish moving (~5s), then force a status refresh
        await asyncio.sleep(6)
        await self.coordinator.async_request_refresh()

    @property
    def is_locked(self) -> bool:
        """Return true if lock is locked."""
        return self._device.is_locked

    @property
    def is_jammed(self) -> bool:
        """Return true if lock is jammed."""
        return self._device.is_jammed

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Find our device in the coordinator's data
        for device in self.coordinator.data:
            if isinstance(device, TheKeysLock) and device.id == self._device.id:
                self._device = device
                break
        self.async_write_ha_state()

    async def async_calibrate(self) -> None:
        """Calibrate the lock."""
        if await gateway_is_synchronizing(self.hass, self._device):
            _LOGGER.info(
                "Gateway (%s) is synchronizing, try again shortly — calibrate skipped for %s",
                self._device._gateway._host, self._device.name,
            )
            return
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
        if await gateway_is_synchronizing(self.hass, self._device):
            _LOGGER.info(
                "Gateway (%s) is synchronizing, try again shortly — sync skipped for %s",
                self._device._gateway._host, self._device.name,
            )
            return
        try:
            for attempt in range(2):
                try:
                    await self.hass.async_add_executor_job(self._device.retrieve_infos)
                    _LOGGER.info("Sync command sent to %s", self._device.name)
                    return
                except GatewayError as err:
                    if err.code in (33, 34) and attempt == 0:
                        _LOGGER.debug(
                            "Transient error %s syncing %s, retrying once...",
                            err.code, self._device.name,
                        )
                        await asyncio.sleep(1)
                        continue
                    if err.code in (33, 34):
                        _LOGGER.warning(
                            "Lock %s unreachable after retry (error %s) — keeping last state",
                            self._device.name, err.code,
                        )
                        return
                    raise
        except Exception as err:
            _LOGGER.error("Error syncing %s: %s", self._device.name, err)
            raise
