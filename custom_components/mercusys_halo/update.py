"""Firmware update entities for discovered Halo units.

The panel can check for a newer version. Installing it is left to the
Mercusys app, because that path reboots the mesh.
"""

from __future__ import annotations

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import HaloCoordinator
from .entity import HaloNodeEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one firmware entity per Halo unit."""
    coordinator: HaloCoordinator = hass.data[DOMAIN][entry.entry_id]
    known: set[str] = set()

    @callback
    def _discover() -> None:
        if coordinator.data is None:
            return
        fresh = []
        for node in coordinator.data.nodes:
            if node.mac in known:
                continue
            known.add(node.mac)
            fresh.append(HaloFirmwareUpdate(coordinator, node.mac))
        if fresh:
            async_add_entities(fresh)

    coordinator.async_add_listener(_discover)
    _discover()


class HaloFirmwareUpdate(HaloNodeEntity, UpdateEntity):
    """Installed firmware, plus the latest version after a check."""

    _attr_translation_key = "firmware"
    _attr_supported_features = UpdateEntityFeature(0)

    def __init__(self, coordinator: HaloCoordinator, mac: str) -> None:
        super().__init__(coordinator, mac)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_firmware_{mac}"

    @property
    def installed_version(self) -> str | None:
        node = self.node
        return node.firmware if node else None

    @property
    def latest_version(self) -> str | None:
        if self.coordinator.data is None or not self.coordinator.data.firmware_checked:
            return None
        offer = self.coordinator.data.firmware_for(self._mac)
        if offer is None:
            return self.installed_version
        return offer.latest or self.installed_version
