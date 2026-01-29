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
                # Try to retrieve lock status with retry logic for timing errors
                success = False
                for attempt in range(3):  # Try up to 3 times
                    try:
                        await hass.async_add_executor_job(device.retrieve_infos)
                        success = True
                        break  # Success! Exit retry loop
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
                        
                        # Error code 33: timestamp too old - retry once
                        # Error code 34: unknown transient error - retry once
                        if error_code in [33, 34] and attempt == 0:
                            _LOGGER.debug(
                                "Transient error %s for %s (attempt %d/3), retrying once...",
                                error_code, device.name, attempt + 1
                            )
                            continue  # Retry once with new timestamp
                        elif error_code in [33, 34]:
                            # Lock is likely out of gateway range or offline
                            # Keep last state without spamming retries
                            _LOGGER.debug(
                                "Lock %s unreachable (error %s), keeping last state",
                                device.name, error_code
                            )
                            break
                        else:
                            # Not a transient error, log and move on
                            _LOGGER.error("Error updating device %s: %s", device.name, e)
                            break
                
                # Add delay between lock queries to prevent gateway contention
                # Gateway can only process one request at a time
                import asyncio
                await asyncio.sleep(0.5)  # 500ms delay between locks

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
