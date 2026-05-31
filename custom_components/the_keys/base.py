"""Base classes."""
import logging

from homeassistant.helpers.entity import DeviceInfo, Entity
from .the_keyspy import TheKeysDevice

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def gateway_is_synchronizing(hass, device) -> bool:
    """Return True if the lock's gateway is in any 'Synchronizing' phase.

    Mirrors the coordinator pre-check (__init__.py async_update_data) so
    user-initiated actions don't race against a busy gateway and get code 34.
    Returns False if the status call itself fails — the caller's own error
    handling then surfaces the real network/HTTP problem.
    """
    try:
        status = await hass.async_add_executor_job(device._gateway.status)
    except Exception as err:
        _LOGGER.debug(
            "Gateway sync pre-check failed for %s (%s); proceeding without skip",
            device.name, err,
        )
        return False
    return "Synchronizing" in status.get("current_status", "")


class TheKeysEntity(Entity):
    """Representation of a the_keys entity."""

    def __init__(self, device: TheKeysDevice):
        """Init a TheKeys entity."""
        self._device = device

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(device.id))},
            name=device.name,
            manufacturer="The Keys",
            model="Gateway" if device.__class__.__name__ == "TheKeysGateway" else "Smart Lock",
        )

    @property
    def available(self) -> bool:
        """Return the available state."""
        return self._device is not None

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return self._attr_unique_id
