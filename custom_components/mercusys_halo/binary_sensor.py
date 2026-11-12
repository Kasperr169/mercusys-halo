"""Binary sensors for Mercusys Halo."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import HaloCoordinator
from .entity import HaloEntity, HaloNodeEntity
from .models import RadioBand


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up connectivity and radio sensors."""
    coordinator: HaloCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([HaloInternetSensor(coordinator)])
    nodes: set[str] = set()
    bands: set[str] = set()

    @callback
    def _discover() -> None:
        if coordinator.data is None:
            return
        fresh: list[BinarySensorEntity] = []
        for node in coordinator.data.nodes:
            if node.mac in nodes:
                continue
            nodes.add(node.mac)
            fresh.append(HaloNodeOnlineSensor(coordinator, node.mac))
        for band in coordinator.data.bands:
            if band.key in bands:
                continue
            bands.add(band.key)
            fresh.append(HaloRadioSensor(coordinator, band.key, guest=False))
            fresh.append(HaloRadioSensor(coordinator, band.key, guest=True))
        if fresh:
            async_add_entities(fresh)

    coordinator.async_add_listener(_discover)
    _discover()


class HaloInternetSensor(HaloEntity, BinarySensorEntity):
    """IPv4 internet status from the panel."""

    _attr_translation_key = "internet"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: HaloCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_internet"

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.internet_online


class HaloNodeOnlineSensor(HaloNodeEntity, BinarySensorEntity):
    """Whether one discovered Halo unit is connected to the mesh."""

    _attr_translation_key = "node_online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: HaloCoordinator, mac: str) -> None:
        super().__init__(coordinator, mac)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_node_{mac}"

    @property
    def is_on(self) -> bool | None:
        node = self.node
        if node is None:
            return None
        return node.online

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        node = self.node
        if node is None:
            return {}
        return {
            "role": node.role,
            "ip": node.ip,
            "connection": node.connection,
            "firmware": node.firmware,
        }


class HaloRadioSensor(HaloEntity, BinarySensorEntity):
    """Host or guest radio for a band the panel reported."""

    def __init__(self, coordinator: HaloCoordinator, band_key: str, guest: bool) -> None:
        super().__init__(coordinator)
        self._band_key = band_key
        self._guest = guest
        suffix = "guest" if guest else "host"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{band_key}_{suffix}"

    def _band(self) -> RadioBand | None:
        if self.coordinator.data is None:
            return None
        for band in self.coordinator.data.bands:
            if band.key == self._band_key:
                return band
        return None

    @property
    def name(self) -> str:
        band = self._band()
        label = band.label if band else self._band_key
        if self._guest:
            return f"{label} guest"
        return label

    @property
    def is_on(self) -> bool | None:
        band = self._band()
        if band is None:
            return None
        return band.guest_enabled if self._guest else band.host_enabled

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        band = self._band()
        if band is None:
            return {}
        if self._guest:
            return {"ssid": band.guest_ssid}
        return {"ssid": band.ssid, "channel": band.channel}

    @property
    def icon(self) -> str:
        return "mdi:wifi-off" if self.is_on is False else "mdi:wifi"
