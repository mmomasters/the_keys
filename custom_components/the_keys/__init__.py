"""The Keys integration."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (CONF_PASSWORD, CONF_SCAN_INTERVAL,
                                 CONF_USERNAME, Platform)
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import entity_platform
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from the_keyspy import TheKeysApi, TheKeysLock

from .const import CONF_GATEWAY_IP, DEFAULT_SCAN_INTERVAL, DOMAIN

PLATFORMS: list[Platform] = [Platform.LOCK, Platform.SENSOR, Platform.BUTTON]

_LOGGER = logging.getLogger(__name__)

SERVICE_CALIBRATE = "calibrate"
SERVICE_SYNC = "sync"


async def async_setup_coordinator(hass: HomeAssistant, entry: ConfigEntry) -> DataUpdateCoordinator:
    """Set up the coordinator."""
    api = TheKeysApi(
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        entry.data[CONF_GATEWAY_IP] or None,
    )
    
    # Get devices ONCE during setup, not on every update!
    # This prevents resetting to default values (is_locked=False, battery=0)
    devices = await hass.async_add_executor_job(api.get_devices)
    _LOGGER.info("Loaded %d devices from The Keys API", len(devices))

    async def async_update_data():
        """Refresh device data - DO NOT call get_devices again!"""
        # Only refresh existing device objects, don't create new ones
        for device in devices:
            if isinstance(device, TheKeysLock):
                # Log raw device data BEFORE retrieve_infos
                _LOGGER.debug(
                    "BEFORE retrieve_infos - Lock %s (ID: %s): is_locked=%s, battery=%s",
                    device.name, device.id, device.is_locked, device.battery_level
                )
                try:
                    await hass.async_add_executor_job(device.retrieve_infos)
                    # Log raw device data AFTER retrieve_infos
                    _LOGGER.debug(
                        "AFTER retrieve_infos - Lock %s (ID: %s): is_locked=%s, battery=%s",
                        device.name, device.id, device.is_locked, device.battery_level
                    )
                except Exception as e:
                    # Parse error to check if it's transient
                    error_msg = str(e)
                    error_code = None
                    
                    # Try to parse error dict from exception string
                    if "{'status':" in error_msg or '{"status":' in error_msg:
                        try:
                            import ast
                            error_dict = ast.literal_eval(error_msg)
                            if isinstance(error_dict, dict):
                                error_code = error_dict.get('code')
                        except (ValueError, SyntaxError):
                            import re
                            code_match = re.search(r"'code':\s*(\d+)", error_msg)
                            if code_match:
                                error_code = int(code_match.group(1))
                    
                    # Error codes 33 and 34 are transient, just log at debug level
                    if error_code in [33, 34]:
                        _LOGGER.debug("Transient API error for %s (code %s), keeping last state", device.name, error_code)
                    else:
                        _LOGGER.error("Error updating device %s: %s", device.name, e)

        # Return the SAME device objects, not new ones!
        return devices

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="the_keys",
        update_method=async_update_data,
        update_interval=timedelta(seconds=entry.data.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
    )

    await coordinator.async_config_entry_first_refresh()
    return coordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up The Keys from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    coordinator = await async_setup_coordinator(hass, entry)
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle removal of an entry."""
    if unloaded_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)

    return unloaded_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
