# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run all tests
pytest tests/

# Run a single test file
pytest tests/test_lock.py -v

# Run a single test
pytest tests/test_lock.py::test_lock_open -v

# Lint (auto-fix)
scripts/lint
# equivalent to: ruff check . --fix
```

## Architecture

This is a Home Assistant custom integration for The Keys smart locks. It has two distinct layers:

### `the_keyspy/` — Python library
Handles all communication, independent of Home Assistant:
- **`api.py` (`TheKeysApi`)** — Cloud API client. Authenticates with JWT tokens (auto-refreshed on expiry), discovers devices, manages access shares, and triggers cloud reboots. Device discovery runs **once at setup** and returns a list of `TheKeysDevice` objects.
- **`devices/gateway.py` (`TheKeysGateway`)** — Local HTTP client for the physical gateway (e.g. `192.168.x.x:port`). Enforces a per-gateway **rate limiter** (heavy ops: 1s, light ops: 0.5s) that serializes all requests to prevent hardware overload. Has its own 3-attempt retry with backoff and a `(connect=5s, read=15s)` timeout. Raises typed errors: `GatewayError` (carries the gateway's numeric `.code` for a `ko` response) and `GatewayUnreachableError` (wraps `requests` timeout/connection errors after retries are exhausted; subclasses both `TheKeysApiError` and `ConnectionError`).
- **`devices/lock.py` (`TheKeysLock`)** — Lock state and battery level. Battery uses a calibrated linear formula (raw ADC → %, ±1% accuracy).

### `custom_components/the_keys/` — Home Assistant integration
- **`__init__.py`** — Sets up a `DataUpdateCoordinator`. **Critical design**: `api.get_devices()` is called **once** during setup; every subsequent poll updates the same objects in place. Re-calling `get_devices()` would reset state to defaults.
- **`config_flow.py`** — UI setup: phone number (auto-converts `0...` → `+33...`), password, optional manual gateway IP/hostname with `:port`, and scan interval.
- **`lock.py` / `sensor.py` / `button.py`** — HA entities backed by the coordinator.

### Coordinator update flow (`__init__.py::async_update_data`)
1. **Ping-first liveness gate**: ICMP-ping the gateway host (`_host_responds_to_ping`) before any HTTP. A non-answering host means the network/internet is down — skip HTTP entirely (avoids ~30s of executor-blocking timeouts) and **never reboot** (a cloud reboot can't reach the gateway).
2. If the host answers ping, check reachability via `gateway.status()`.
3. On failure, `_note_unreachable()` increments `_consecutive_failures`. After 5 failures, trigger a cloud reboot **only when the host still answers ping** (= HTTP frozen but network alive); also skipped during a 30-min cooldown or if the gateway was last seen synchronizing. A HA Repair issue is raised regardless.
4. **Stuck-sync watchdog**: `_synchronizing_since` records when the gateway first entered a `Synchronizing` phase. If that state persists past `STUCK_SYNC_THRESHOLD` (10 min — well above the ~4-min worst-case observed in `/tmp/gateway_bench.log` on 2026-05-31), force a cloud reboot even though the normal `_is_synchronizing` guard would block it. Still respects the 30-min cooldown.
5. On success, iterate locks and call `device.retrieve_infos()` with per-lock retry logic keyed on `GatewayError.code`:
   - **400/500** (busy) → wait 6s, retry
   - **38** (clock skew) → call `gateway.synchronize()`, retry
   - **33/34** (transient) → retry once

### User-action sync pre-check
The gateway runs a continuous cycle `Synchronizing gw → Synchronizing <lockID> → Scanning → …` where the `gw` phase dominates (60 s to 4 min+). Any user action that has to reach the lock (lock / unlock / sync / calibrate buttons and services) calls `gateway_is_synchronizing(hass, device)` (defined in `base.py`) first:
- **lock / unlock** → `raise HomeAssistantError("Gateway is synchronizing — try again in a minute.")` so HA surfaces a popup.
- **sync / calibrate** → log INFO and return silently.
- **Reboot button** is deliberately exempt — rebooting a stuck gateway is the escape hatch.

The `Sync` paths additionally catch `GatewayError` with `.code in (33, 34)` and retry once with a 1s pause (handles the race where the gateway starts syncing between pre-check and call); on persistent failure they log WARNING (not ERROR).

### Gateway caching
`TheKeysApi.get_devices()` caches `TheKeysGateway` instances by host IP so all locks on the same physical gateway share **one** gateway object and therefore one rate limiter.

### Token refresh
`TheKeysApi.authenticated` checks both presence and expiry of the JWT access token (with a 60s buffer). `__http_request` calls `__authenticate()` automatically when the token is absent or expired.
