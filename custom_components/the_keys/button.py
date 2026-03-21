"""The Keys Button entities."""
import logging

import requests

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import EntityCategory
from .the_keyspy import TheKeysGateway, TheKeysLock

from .base import TheKeysEntity
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up TheKeys button entities."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    if not coordinator.data:
        return

    entities = []
    for device in coordinator.data:
        if isinstance(device, TheKeysLock):
            entities.append(TheKeysCalibrateButton(coordinator, device))
            entities.append(TheKeysSyncButton(coordinator, device))
        elif isinstance(device, TheKeysGateway):
            entities.append(TheKeysRebootButton(coordinator, device))

    async_add_entities(entities, update_before_add=False)


class TheKeysButtonEntity(CoordinatorEntity, TheKeysEntity, ButtonEntity):
    """Base class for TheKeys button entities."""

    def __init__(self, coordinator, device: TheKeysLock, button_type: str):
        """Init a TheKeys button entity."""
        super().__init__(coordinator)
        TheKeysEntity.__init__(self, device=device)
        self._device = device
        self._button_type = button_type
        self._attr_unique_id = f"{self._device.id}_{button_type}_button"
        # Don't set entity_category - we want these in main Controls, not Configuration

    @property
    def name(self) -> str:
        """Return the name of the button."""
        return f"{self._device.name} {self._button_type.replace('_', ' ').title()}"


class TheKeysCalibrateButton(TheKeysButtonEntity):
    """Button to calibrate The Keys lock."""

    def __init__(self, coordinator, device: TheKeysLock):
        """Init calibrate button."""
        super().__init__(coordinator, device, "calibrate")
        self._attr_icon = "mdi:tune"

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            if hasattr(self._device, 'calibrate'):
                await self.hass.async_add_executor_job(self._device.calibrate)
                _LOGGER.info("Calibrate command sent to %s", self._device.name)
                await self.coordinator.async_request_refresh()
            else:
                _LOGGER.warning("Calibrate method not available for %s", self._device.name)
        except (requests.exceptions.ConnectionError, ConnectionError, OSError) as err:
            _LOGGER.warning(
                "Gateway not responding while calibrating %s: %s", self._device.name, err
            )
        except Exception as err:
            _LOGGER.error("Error calibrating %s: %s", self._device.name, err)


class TheKeysSyncButton(TheKeysButtonEntity):
    """Button to sync The Keys lock."""

    def __init__(self, coordinator, device: TheKeysLock):
        """Init sync button."""
        super().__init__(coordinator, device, "sync")
        self._attr_icon = "mdi:sync"

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            if hasattr(self._device, 'sync'):
                await self.hass.async_add_executor_job(self._device.sync)
                _LOGGER.info("Sync command sent to %s", self._device.name)
            elif hasattr(self._device, 'retrieve_infos'):
                # Fallback to retrieve_infos as a sync alternative
                await self.hass.async_add_executor_job(self._device.retrieve_infos)
                _LOGGER.info("Sync (retrieve_infos) command sent to %s", self._device.name)
            else:
                _LOGGER.warning("Sync method not available for %s", self._device.name)
            # Request coordinator update after sync
            await self.coordinator.async_request_refresh()
        except (requests.exceptions.ConnectionError, ConnectionError, OSError) as err:
            _LOGGER.warning(
                "Gateway not responding while syncing %s: %s", self._device.name, err
            )
        except Exception as err:
            _LOGGER.error("Error syncing %s: %s", self._device.name, err)


class TheKeysRebootButton(CoordinatorEntity, TheKeysEntity, ButtonEntity):
    """Button to reboot The Keys gateway."""

    def __init__(self, coordinator, device):
        """Init reboot button."""
        super().__init__(coordinator)
        TheKeysEntity.__init__(self, device=device)
        self._device = device
        self._attr_unique_id = f"{self._device.id}_reboot_button"
        self._attr_icon = "mdi:restart"
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def name(self) -> str:
        """Return the name of the button."""
        return "Reboot"

    async def async_press(self) -> None:
        """Handle the button press."""
        # Use the API directly from the coordinator
        # The coordinator has access to the api via its update_method closure
        # but here we'll need to reach it.
        # Coordinator setup creates 'api' variable.
        # We can find it in the coordinator's state if we stored it, 
        # but current __init__.py doesn't store api on coordinator.
        # Let's check __init__.py again.
        
        # Accessing api from coordinator's underlying api object if possible
        # In __init__.py, api is a local variable in async_setup_coordinator.
        # We need to make it accessible.
        
        try:
            # For now, we assume the coordinator has an api attribute 
            # (we will add it in the next step)
            if hasattr(self.coordinator, 'api'):
                _LOGGER.info("Manually triggering reboot for gateway %s", self._device.id)
                success = await self.hass.async_add_executor_job(
                    self.coordinator.api.reboot_gateway, self._device.id
                )
                if success:
                    _LOGGER.info("Reboot command successfully sent to cloud for %s", self._device._host)
                else:
                    _LOGGER.error("Failed to send reboot command for %s", self._device._host)
            else:
                _LOGGER.error("API not available on coordinator for reboot")
        except Exception as err:
            _LOGGER.error("Error rebooting %s: %s", self._device._host, err)
