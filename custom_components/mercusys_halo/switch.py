"""Switch platform for Mercusys Halo."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import HaloCoordinator
from .entity import HaloEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the wireless switch."""
    coordinator: HaloCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([HaloWifiSwitch(coordinator)])


class HaloWifiSwitch(HaloEntity, SwitchEntity):
    """Turn the whole wireless network on or off.

    The panel has one switch for every band. It does not expose 5 GHz alone.
    """

    _attr_translation_key = "wifi"
    _attr_icon = "mdi:wifi"

    def __init__(self, coordinator: HaloCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_wifi"

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.wifi_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)

    async def _set(self, enabled: bool) -> None:
        try:
            await self.coordinator.async_set_wifi(enabled)
        except ConfigEntryAuthFailed:
            raise
        except Exception as err:
            raise HomeAssistantError(str(err)) from err
