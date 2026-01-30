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
        data = {}
        if identifier != "":
            data["identifier"] = identifier

        if share_code != "":
            timestamp = str(int(time.time()))
            data["ts"] = timestamp
            data["hash"] = base64.b64encode(hmac.new(share_code.encode(
                "ascii"), timestamp.encode("ascii"), "sha256").digest())

        url = "status"
        match action:
            case Action.STATUS:
                url = "status"
            case Action.UPDATE:
                url = "update"
                data = {"fake": True}
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

        response_data = self.__http_request(url, data)
        if "status" not in response_data:
            response_data["status"] = "ok"

        if response_data["status"] == "ko":
            raise RuntimeError(response_data)

        return response_data

    def __http_request(self, url: str, data: Optional[dict] = None) -> Any:
        method = "post" if data else "get"
        logger.debug("%s %s", method.upper(), url)
        try:
            with requests.Session() as session:
                full_url = f"http://{self._host}/{url}"
                response = session.post(
                    full_url, data=data) if method == "post" else session.get(full_url)
                logger.debug("response_data: %s", response.json())
                return response.json()
        except ConnectionError as error:
            raise error
