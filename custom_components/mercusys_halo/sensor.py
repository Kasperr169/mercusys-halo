"""Sensors for Mercusys Halo."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import HaloCoordinator
from .entity import HaloEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up address and client-count sensors."""
    coordinator: HaloCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            HaloWanIpSensor(coordinator),
            HaloLanIpSensor(coordinator),
            HaloClientCountSensor(coordinator),
        ]
    )


class HaloWanIpSensor(HaloEntity, SensorEntity):
    """WAN address reported by the panel."""

    _attr_translation_key = "wan_ip"
    _attr_icon = "mdi:ip-network"

    def __init__(self, coordinator: HaloCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_wan_ip"

    @property
    def native_value(self) -> str | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.wan_ip


class HaloLanIpSensor(HaloEntity, SensorEntity):
    """LAN address reported by the panel."""

    _attr_translation_key = "lan_ip"
    _attr_icon = "mdi:ip-network"

    def __init__(self, coordinator: HaloCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_lan_ip"

    @property
    def native_value(self) -> str | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.lan_ip


class HaloClientCountSensor(HaloEntity, SensorEntity):
    """How many clients the panel currently marks online."""

    _attr_translation_key = "clients"
    _attr_icon = "mdi:account-multiple"
    _attr_native_unit_of_measurement = "clients"

    def __init__(self, coordinator: HaloCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_clients"

    @property
    def native_value(self) -> int | None:
        if self.coordinator.data is None:
            return None
        return sum(1 for client in self.coordinator.data.clients if client.online)
