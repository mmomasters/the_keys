"""The Keys integration."""
from __future__ import annotations

import logging
from datetime import timedelta

import requests

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (CONF_PASSWORD, CONF_SCAN_INTERVAL,
                                 CONF_USERNAME, Platform)
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import entity_platform
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from .the_keyspy import TheKeysApi, TheKeysLock

from .const import (
    CONF_GATEWAY_IP,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_RATE_LIMIT_DELAY,
    DEFAULT_RATE_LIMIT_DELAY_LIGHT,
    DOMAIN,
)
from .the_keyspy.devices import TheKeysGateway

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
        rate_limit_delay=DEFAULT_RATE_LIMIT_DELAY,
        rate_limit_delay_light=DEFAULT_RATE_LIMIT_DELAY_LIGHT,
    )
    
    # Get devices ONCE during setup, not on every update!
    # This prevents resetting to default values (is_locked=False, battery=0)
    devices = await hass.async_add_executor_job(api.get_devices)
    _LOGGER.info("Loaded %d devices from The Keys API", len(devices))

    # Track gateway reachability to avoid repeating the same WARNING every poll cycle
    _gateway_reachable = True
    # Track if the gateway is currently synchronizing
    _is_synchronizing = False
    # Track the last reboot time to avoid reboot loops
    _last_reboot_time = None
    # Count consecutive failed cycles; used to raise a HA Repair issue after prolonged outages
    _consecutive_failures = 0
    # Issue ID is scoped to this config entry so multi-instance setups work correctly
    _issue_id = f"gateway_unreachable_{entry.entry_id}"

    async def async_update_data():
        """Refresh device data - DO NOT call get_devices again!"""
        nonlocal _gateway_reachable, _is_synchronizing, _last_reboot_time, _consecutive_failures

        # Check gateway reachability/status before polling individual devices.
        # We route this through the shared gateway object so the rate limiter
        # coordinates this request with subsequent lock polling requests.
        gateway_device = next(
            (d for d in devices if isinstance(d, TheKeysLock) and hasattr(d, "_gateway")),
            None,
        )
        if gateway_device:
            gateway_host = gateway_device._gateway._host
            try:
                gateway_status = await hass.async_add_executor_job(
                    gateway_device._gateway.status
                )

                # Gateway is reachable — log recovery if it was previously down
                if not _gateway_reachable:
                    _LOGGER.info("Gateway (%s) is back online, resuming device updates", gateway_host)
                    _gateway_reachable = True

                # Clear any active repair issue and reset the failure counter
                _consecutive_failures = 0
                ir.async_delete_issue(hass, DOMAIN, _issue_id)

                if "Synchronizing" in gateway_status.get("current_status", ""):
                    _LOGGER.info("Gateway is synchronizing, skipping lock updates this cycle")
                    _is_synchronizing = True
                    return devices  # Return without updating, keep last state
                
                _is_synchronizing = False

            except Exception as e:
                # Gateway is unreachable — skip all device polls this cycle.
                # Log WARNING only on first failure; subsequent cycles log DEBUG
                # to avoid hundreds of identical warnings during an outage.
                err_str = str(e)
                if "timed out" in err_str.lower() or "ConnectTimeout" in err_str:
                    reason = "connection timed out"
                elif "Connection refused" in err_str or "Errno 111" in err_str:
                    reason = "connection refused"
                elif "Name or service not known" in err_str or "getaddrinfo" in err_str:
                    reason = "DNS resolution failed"
                else:
                    reason = type(e).__name__

                if _gateway_reachable:
                    _LOGGER.warning(
                        "Gateway (%s) is unreachable (%s), skipping device updates",
                        gateway_host, reason,
                    )
                    _gateway_reachable = False
                else:
                    _LOGGER.debug(
                        "Gateway (%s) still unreachable (%s), skipping device updates",
                        gateway_host, reason,
                    )

                # Raise a HA Repair issue and trigger auto-reboot after 5 consecutive failures 
                # (~5 min at default 1-min interval).
                _consecutive_failures += 1
                if _consecutive_failures >= 5:
                    # SAFETY CHECK 1: Don't reboot if it was already synchronizing
                    if _is_synchronizing:
                        _LOGGER.warning(
                            "Gateway (%s) is unreachable but was last seen synchronizing. "
                            "Wait for it to finish.", gateway_host
                        )
                    # SAFETY CHECK 2: Don't reboot if we just did it recently (30 min cooldown)
                    elif _last_reboot_time and (datetime.now() - _last_reboot_time) < timedelta(minutes=30):
                        _LOGGER.debug(
                            "Gateway (%s) is unreachable but was rebooted less than 30 min ago. "
                            "Wait for it to stabilize.", gateway_host
                        )
                    else:
                        _LOGGER.warning(
                            "Gateway (%s) has been unreachable for %d consecutive cycles — "
                            "triggering automatic reboot via cloud API",
                            gateway_host, _consecutive_failures,
                        )
                        # Trigger reboot - use the REAL accessory ID from gateway_device._gateway.id
                        # (Note: local IP manual setups sometimes mock ID=1, we must ensure 
                        # the API uses the real cloud ID discovered during setup)
                        success = await hass.async_add_executor_job(
                            api.reboot_gateway, gateway_device._gateway.id
                        )
                        if success:
                            _LOGGER.info("Automatic reboot command successfully sent for %s", gateway_host)
                            _last_reboot_time = datetime.now()
                        else:
                            _LOGGER.error("Failed to trigger automatic reboot for %s", gateway_host)

                    ir.async_create_issue(
                        hass,
                        DOMAIN,
                        _issue_id,
                        is_fixable=False,
                        severity=ir.IssueSeverity.WARNING,
                        translation_key="gateway_unreachable",
                        translation_placeholders={
                            "gateway_host": gateway_host,
                            "consecutive_failures": str(_consecutive_failures),
                        },
                    )

                return devices
        
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
                    except (ConnectionError, TimeoutError, OSError,
                            requests.exceptions.RequestException) as e:
                        # Network/connection errors (both built-in and requests-specific).
                        # gateway.py already logged at DEBUG after exhausting its own retries.
                        # Log at DEBUG here too to avoid duplicate noise — the gateway
                        # health check at the top of this function owns the single WARNING
                        # per cycle when the gateway is unreachable.
                        _LOGGER.debug(
                            "Network error updating device %s (keeping last state): %s",
                            device.name, str(e)
                        )
                        break  # Don't retry - already retried at gateway level
                        
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
                        
                        # Error code 400: action already started / 500: busy
                        # Gateway is temporarily occupied — wait and retry.
                        # Lock takes ~5s to physically move, so wait 6s before retrying.
                        if error_code in (400, 500):
                            _LOGGER.debug(
                                "Device %s is busy (error %s, attempt %d/3), "
                                "waiting 6s before retry...",
                                device.name, error_code, attempt + 1
                            )
                            import asyncio
                            await asyncio.sleep(6)
                            continue  # Retry after waiting

                        # Error code 38: gateway time invalid - auto-sync and retry
                        if error_code == 38:
                            _LOGGER.info(
                                "Gateway time invalid for %s (error 38, attempt %d/3), "
                                "auto-syncing gateway time...",
                                device.name, attempt + 1
                            )
                            # Gateway may be busy - retry the sync itself up to 3 times
                            import asyncio
                            sync_ok = False
                            for sync_attempt in range(3):
                                try:
                                    await hass.async_add_executor_job(device._gateway.synchronize)
                                    sync_ok = True
                                    _LOGGER.info(
                                        "Gateway time sync succeeded for %s, retrying status...",
                                        device.name
                                    )
                                    break
                                except Exception as sync_err:
                                    sync_err_msg = str(sync_err)
                                    # Check if the gateway is simply busy (code 500)
                                    # — this happens when it is mid-synchronization.
                                    # Treat as transient and log at DEBUG, not WARNING.
                                    is_busy = (
                                        "'code': 500" in sync_err_msg
                                        or '"code": 500' in sync_err_msg
                                        or "busy" in sync_err_msg.lower()
                                    )
                                    if sync_attempt < 2:
                                        _LOGGER.debug(
                                            "Gateway sync busy for %s (sync attempt %d/3): %s, "
                                            "waiting 5s...",
                                            device.name, sync_attempt + 1, sync_err_msg
                                        )
                                        await asyncio.sleep(5)
                                    else:
                                        log_fn = _LOGGER.debug if is_busy else _LOGGER.warning
                                        log_fn(
                                            "Failed to auto-sync gateway time for %s after "
                                            "3 attempts: %s",
                                            device.name, sync_err_msg
                                        )
                            if not sync_ok:
                                break  # Give up on this device this cycle
                            continue  # Retry status after successful sync

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
                
                # No additional sleep needed here — the shared gateway object's
                # rate limiter already serializes all requests to the physical device.

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
    coordinator.api = api

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
