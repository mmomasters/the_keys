"""Constants for the The Keys integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "the_keys"
MIN_SCAN_INTERVAL = 10
DEFAULT_SCAN_INTERVAL: Final = timedelta(minutes=2).total_seconds()
CONF_GATEWAY_IP: Final = "gateway_ip"

# Rate limiting for gateway API requests
# Based on benchmark data (2026-03-14):
#   - locker_status responses take ~3.2s on average
#   - gateway /status responses take ~130ms on average
#   - Rapid back-to-back requests cause "Connection refused" on the physical gateway
#
# Heavy operations: open/close/calibrate/locker_status
#   The call itself takes ~3.2s, so 1.0s recovery delay after response is sufficient.
#   Total per-lock cycle ≈ 3.2s (response) + 1.0s (delay) = ~4.2s
DEFAULT_RATE_LIMIT_DELAY: Final = 1.0  # seconds

# Light operations: gateway /status, locker/sync, locker/update
#   ~130ms response time; 0.5s recovery is safe and avoids connection refused.
DEFAULT_RATE_LIMIT_DELAY_LIGHT: Final = 0.5  # seconds
