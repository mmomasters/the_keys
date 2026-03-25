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
- **`devices/gateway.py` (`TheKeysGateway`)** — Local HTTP client for the physical gateway (e.g. `192.168.x.x:port`). Enforces a per-gateway **rate limiter** (heavy ops: 1s, light ops: 0.5s) that serializes all requests to prevent hardware overload. Has its own 3-attempt retry with backoff.
- **`devices/lock.py` (`TheKeysLock`)** — Lock state and battery level. Battery uses a calibrated linear formula (raw ADC → %, ±1% accuracy).

### `custom_components/the_keys/` — Home Assistant integration
- **`__init__.py`** — Sets up a `DataUpdateCoordinator`. **Critical design**: `api.get_devices()` is called **once** during setup; every subsequent poll updates the same objects in place. Re-calling `get_devices()` would reset state to defaults.
- **`config_flow.py`** — UI setup: phone number (auto-converts `0...` → `+33...`), password, optional manual gateway IP/hostname with `:port`, and scan interval.
- **`lock.py` / `sensor.py` / `button.py`** — HA entities backed by the coordinator.

### Coordinator update flow (`__init__.py::async_update_data`)
1. Check gateway reachability via `gateway.status()`.
2. On failure, increment `_consecutive_failures`. After 5 failures, trigger cloud reboot (30-min cooldown between reboots; skip if gateway was last seen synchronizing).
3. On success, iterate locks and call `device.retrieve_infos()` with per-lock retry logic keyed on error codes:
   - **400/500** (busy) → wait 6s, retry
   - **38** (clock skew) → call `gateway.synchronize()`, retry
   - **33/34** (transient) → retry once

### Gateway caching
`TheKeysApi.get_devices()` caches `TheKeysGateway` instances by host IP so all locks on the same physical gateway share **one** gateway object and therefore one rate limiter.

### Token refresh
`TheKeysApi.authenticated` checks both presence and expiry of the JWT access token (with a 60s buffer). `__http_request` calls `__authenticate()` automatically when the token is absent or expired.
