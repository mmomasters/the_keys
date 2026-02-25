from curses import meta
from .base import TheKeysDevice
import base64
import hmac
import time
import requests
from enum import Enum
from typing import Any, Optional

import logging

logger = logging.getLogger("the_keyspy.devices.gateway")


class Action(Enum):
    """All available actions"""

    STATUS = "status"
    UPDATE = "update"
    SYNCHRONIZE = "synchronize"

    LOCKER_OPEN = "locker_open"
    LOCKER_CLOSE = "locker_close"
    LOCKER_CALIBRATE = "locker_calibrate"
    LOCKER_STATUS = "locker_status"
    LOCKER_SYNCHRONIZE = "locker_synchronize"
    LOCKER_UPDATE = "locker_update"

    def __str__(self):
        return self.value


class TheKeysGateway(TheKeysDevice):
    """Gateway device implementation"""

    def __init__(self, id: int, host: str, rate_limit_delay: float = 5.0, rate_limit_delay_light: float = 1.0) -> None:
        super().__init__(id)
        self._host = host
        # Rate limiting to prevent overwhelming the gateway:
        # - Heavy operations (open/close/calibrate/locker_status): 5.0s delay
        # - Light operations (gateway status/list/sync/update): 1.0s delay
        self._rate_limit_delay = rate_limit_delay  # Delay for heavy operations
        self._rate_limit_delay_light = rate_limit_delay_light  # Delay for light operations
        self._last_request_time = 0

    def _rate_limit(self, light_operation: bool = False) -> None:
        """Enforce rate limiting between requests
        
        Args:
            light_operation: If True, use lighter rate limit for discovery/status endpoints
                           Based on benchmark: light operations can use 0.2s delay safely
        """
        current_time = time.time()
        time_since_last_request = current_time - self._last_request_time
        
        # Choose appropriate delay based on operation type
        delay = self._rate_limit_delay_light if light_operation else self._rate_limit_delay
        
        if time_since_last_request < delay:
            sleep_time = delay - time_since_last_request
            logger.debug(
                "[Rate Limit] %s operation - waiting %.2fs before next request...",
                "light" if light_operation else "heavy",
                sleep_time
            )
            time.sleep(sleep_time)
        
        self._last_request_time = time.time()

    # Gateway actions
    def status(self) -> Any:
        # Light operation - benchmark shows avg 0.132s response time
        self._rate_limit(light_operation=True)
        return self.action(Action.STATUS)

    def update(self) -> bool:
        # Light operation
        self._rate_limit(light_operation=True)
        return self.action(Action.UPDATE)["status"] == "ok"

    def synchronize(self) -> bool:
        # Light operation
        self._rate_limit(light_operation=True)
        return self.action(Action.SYNCHRONIZE)["status"] == "ok"

    # Locker actions
    def locker_open(self, identifier: str, share_code: str) -> bool:
        # Heavy operation - physically opens lock
        self._rate_limit(light_operation=False)
        return self.action(Action.LOCKER_OPEN, identifier, share_code)["status"] == "ok"

    def locker_close(self, identifier: str, share_code: str) -> bool:
        # Heavy operation - physically closes lock
        self._rate_limit(light_operation=False)
        return self.action(Action.LOCKER_CLOSE, identifier, share_code)["status"] == "ok"

    def locker_calibrate(self, identifier: str, share_code: str) -> bool:
        # Heavy operation - calibrates lock
        self._rate_limit(light_operation=False)
        return self.action(Action.LOCKER_CALIBRATE, identifier, share_code)["status"] == "ok"

    def locker_status(self, identifier: str, share_code: str) -> Any:
        # Heavy operation - queries lock status
        self._rate_limit(light_operation=False)
        return self.action(Action.LOCKER_STATUS, identifier, share_code)

    def locker_synchronize(self, identifier: str, share_code: str) -> bool:
        # Light operation
        self._rate_limit(light_operation=True)
        return self.action(Action.LOCKER_SYNCHRONIZE, identifier, share_code)["status"] == "ok"

    def locker_update(self, identifier: str, share_code: str) -> bool:
        # Light operation
        self._rate_limit(light_operation=True)
        return self.action(Action.LOCKER_UPDATE, identifier, share_code)["status"] == "ok"

    # Common actions
    def action(self, action: Action, identifier: str = "", share_code: str = "") -> Any:
        url = "status"
        match action:
            case Action.STATUS:
                url = "status"
            case Action.UPDATE:
                url = "update"
            case Action.SYNCHRONIZE:
                url = "synchronize"
            case Action.LOCKER_OPEN:
                url = "open"
            case Action.LOCKER_CLOSE:
                url = "close"
            case Action.LOCKER_CALIBRATE:
                url = "calibrate"
            case Action.LOCKER_STATUS:
                url = "locker_status"
            case Action.LOCKER_SYNCHRONIZE:
                url = "locker/synchronize"
            case Action.LOCKER_UPDATE:
                url = "locker/update"

        max_ts_retries = 3
        for ts_attempt in range(max_ts_retries):
            # Build request data with a FRESH timestamp on every attempt so that
            # a stale-timestamp error (code 33) can be resolved by retrying.
            data = {}
            if identifier != "":
                data["identifier"] = identifier

            if action == Action.UPDATE:
                data = {"fake": True}
            elif share_code != "":
                timestamp = str(int(time.time()))
                data["ts"] = timestamp
                data["hash"] = base64.b64encode(hmac.new(
                    share_code.encode("ascii"),
                    timestamp.encode("ascii"),
                    "sha256",
                ).digest())

            response_data = self.__http_request(url, data)
            if "status" not in response_data:
                response_data["status"] = "ok"

            if response_data["status"] == "ko":
                error_code = response_data.get("code")
                # Error 33: timestamp too old — regenerate and retry immediately
                if error_code == 33 and ts_attempt < max_ts_retries - 1:
                    logger.debug(
                        "Timestamp rejected by gateway for %s (error 33, attempt %d/%d), "
                        "regenerating and retrying...",
                        url, ts_attempt + 1, max_ts_retries,
                    )
                    time.sleep(1)  # Brief pause before regenerating timestamp
                    continue
                raise RuntimeError(response_data)

            return response_data

        # Should not be reached, but raise if all retries exhausted
        raise RuntimeError({"status": "ko", "code": 33, "error": "timestamp rejected after all retries"})

    def __http_request(self, url: str, data: Optional[dict] = None) -> Any:
        method = "post" if data else "get"
        logger.debug("%s %s", method.upper(), url)
        
        # Add timeout and retry logic for network resilience
        timeout = 10  # 10 second timeout
        max_retries = 3
        retry_delay = 1  # Start with 1 second
        
        for attempt in range(max_retries):
            try:
                with requests.Session() as session:
                    full_url = f"http://{self._host}/{url}"
                    if method == "post":
                        response = session.post(full_url, data=data, timeout=timeout)
                    else:
                        response = session.get(full_url, timeout=timeout)
                    
                    logger.debug("response_data: %s", response.json())
                    return response.json()

            except requests.exceptions.ConnectionError as error:
                error_str = str(error)
                # "Connection refused" (errno 111) means the gateway is actively down.
                # Retrying immediately is pointless — it won't recover in 1-4 seconds.
                # Fail fast so the caller can handle it without wasting time.
                if "Connection refused" in error_str or "Errno 111" in error_str:
                    logger.debug(
                        "Connection refused by %s for /%s — gateway is down, failing fast",
                        self._host, url,
                    )
                    raise

                # Other ConnectionError (e.g. reset, aborted) — retry with backoff
                if attempt < max_retries - 1:
                    logger.debug(
                        "Connection error to %s (attempt %d/%d): %s - retrying in %ds...",
                        self._host, attempt + 1, max_retries, error_str, retry_delay,
                    )
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    logger.debug(
                        "Failed to connect to %s after %d attempts: %s",
                        self._host, max_retries, error_str,
                    )
                    raise

            except (requests.exceptions.Timeout, ConnectionResetError) as error:
                # Timeouts may recover — retry with exponential backoff
                if attempt < max_retries - 1:
                    logger.debug(
                        "Timeout/reset on %s (attempt %d/%d): %s - retrying in %ds...",
                        self._host, attempt + 1, max_retries, str(error), retry_delay,
                    )
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    # Final timeout failure — log at DEBUG; __init__.py health check owns
                    # the single WARNING per cycle when the gateway is unreachable
                    logger.debug(
                        "Failed to connect to %s after %d attempts: %s",
                        self._host, max_retries, str(error),
                    )
                    raise

            except requests.exceptions.RequestException as error:
                # Other request errors (don't retry these)
                logger.debug("Request error to %s: %s", self._host, str(error))
                raise
