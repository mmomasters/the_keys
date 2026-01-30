"""Constants for the The Keys integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "the_keys"
MIN_SCAN_INTERVAL = 10
DEFAULT_SCAN_INTERVAL: Final = timedelta(minutes=1).total_seconds()
CONF_GATEWAY_IP: Final = "gateway_ip"

# Rate limiting for gateway API requests
# Heavy operations: open/close/calibrate/status - these physically interact with locks
DEFAULT_RATE_LIMIT_DELAY: Final = 5.0  # seconds
# Light operations: gateway status/list/sync - these are quick status checks
DEFAULT_RATE_LIMIT_DELAY_LIGHT: Final = 1.0  # seconds
