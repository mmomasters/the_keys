"""The Keys integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

import requests

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (CONF_PASSWORD, CONF_SCAN_INTERVAL,
                                 CONF_USERNAME, Platform)
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import entity_platform
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from .the_keyspy import TheKeysApi, TheKeysLock
from .the_keyspy.devices import GatewayError

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


async def _host_responds_to_ping(host: str) -> bool:
    """Return True if the gateway host answers an ICMP ping.

    The gateway `_host` may carry a port (e.g. "192.168.1.50:8080"); ICMP has no
    port, so strip it before pinging. A host that does not answer ping means the
    remote site's network/internet is down: a cloud reboot can neither reach the
    gateway nor help, so callers should skip rebooting in that case.

    If the `ping` binary is missing or not permitted (some containers), we assume
    the host is reachable so we never suppress a legitimately-needed reboot.
    """
    hostname = host.split(":")[0].strip("[]")
    try:
        proc = await asyncio.create_subprocess_exec(
            "ping", "-c", "1", "-W", "2", hostname,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        return await proc.wait() == 0
    except OSError as err:
        _LOGGER.debug(
            "Could not run ping for %s (%s); assuming reachable", hostname, err
        )
        return True


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

            async def _note_unreachable(reason: str, can_reboot: bool):
                """Record a failed poll cycle and act on repeated failures.

                Logs once, counts failures, raises the HA Repair issue, and — only when
                the gateway is network-alive but its HTTP service is frozen
                (``can_reboot``) — triggers a cloud reboot.

                ``can_reboot`` is False when the host did not answer ping: the remote
                network/internet is down, so a cloud reboot can neither reach the gateway
                nor help.
                """
                nonlocal _gateway_reachable, _consecutive_failures, _last_reboot_time

                # Log WARNING only on the first failure; subsequent cycles log DEBUG to
                # avoid hundreds of identical warnings during a prolonged outage.
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

                # Raise a HA Repair issue and (maybe) auto-reboot after 5 consecutive
                # failures (~5 min at the default 1-min interval).
                _consecutive_failures += 1
                if _consecutive_failures >= 5:
                    # SAFETY CHECK 1: host doesn't answer ping → network/internet is down,
                    # a cloud reboot can't reach the gateway and wouldn't help.
                    if not can_reboot:
                        _LOGGER.warning(
                            "Gateway (%s) is unreachable and does not answer ping — the "
                            "remote network/internet appears to be down. Skipping reboot "
                            "(a cloud reboot cannot reach the gateway).",
                            gateway_host,
                        )
                    # SAFETY CHECK 2: don't reboot if it was last seen synchronizing
                    elif _is_synchronizing:
                        _LOGGER.warning(
                            "Gateway (%s) is unreachable but was last seen synchronizing. "
                            "Wait for it to finish.", gateway_host
                        )
                    # SAFETY CHECK 3: don't reboot if we just did it recently (30 min cooldown)
                    elif _last_reboot_time and (datetime.now() - _last_reboot_time) < timedelta(minutes=30):
                        _LOGGER.debug(
                            "Gateway (%s) is unreachable but was rebooted less than 30 min ago. "
                            "Wait for it to stabilize.", gateway_host
                        )
                    else:
                        _LOGGER.warning(
                            "Gateway (%s) has been unreachable for %d consecutive cycles but "
                            "still answers ping — triggering automatic reboot via cloud API",
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

            # Fast liveness pre-check: ping before the slow, retrying HTTP status call.
            # A non-answering host means the network/internet is down — skip HTTP entirely
            # (saves up to ~30s of executor-blocking timeouts) and never reboot.
            if not await _host_responds_to_ping(gateway_host):
                await _note_unreachable("no ping reply", can_reboot=False)
                return devices

            # Host answers ping — check the gateway's HTTP status. Routed through the
            # shared gateway object so the rate limiter coordinates this request with
            # the subsequent lock-polling requests.
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
                # Ping succeeded but the HTTP status failed → the gateway is on the
                # network but its service is likely frozen → reboot candidate.
                err_str = str(e)
                if "timed out" in err_str.lower() or "ConnectTimeout" in err_str:
                    reason = "connection timed out"
                elif "Connection refused" in err_str or "Errno 111" in err_str:
                    reason = "connection refused"
                elif "Name or service not known" in err_str or "getaddrinfo" in err_str:
                    reason = "DNS resolution failed"
                else:
                    reason = type(e).__name__

                await _note_unreachable(reason, can_reboot=True)
                return devices


        # Only refresh existing device objects, don't create new ones
        for device in devices:
            if isinstance(device, TheKeysLock):
                # Try to retrieve lock status with retry logic for timing errors
                for attempt in range(3):  # Try up to 3 times
                    try:
                        await hass.async_add_executor_job(device.retrieve_infos)
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
                        
                    except GatewayError as e:
                        # The gateway returned a 'ko' response; its numeric code tells us
                        # whether the failure is transient (busy / clock-skew) and worth a retry.
                        error_code = e.code

                        # Error code 400: action already started / 500: busy
                        # Gateway is temporarily occupied — wait and retry.
                        # Lock takes ~5s to physically move, so wait 6s before retrying.
                        if error_code in (400, 500):
                            _LOGGER.debug(
                                "Device %s is busy (error %s, attempt %d/3), "
                                "waiting 6s before retry...",
                                device.name, error_code, attempt + 1
                            )
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
                                    # Code 500 means the gateway is simply busy (mid-sync).
                                    # Treat as transient and log at DEBUG, not WARNING.
                                    is_busy = getattr(sync_err, "code", None) == 500
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

                    except Exception as e:
                        # Unexpected, non-gateway error — keep last state and move on
                        # rather than letting the whole update cycle crash.
                        _LOGGER.error("Unexpected error updating device %s: %s", device.name, e)
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
