"""Buttons for Mercusys Halo."""

from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import HaloCoordinator
from .entity import HaloEntity, HaloNodeEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up restart and firmware-check buttons."""
    coordinator: HaloCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            HaloRebootAllButton(coordinator),
            HaloCheckFirmwareButton(coordinator),
        ]
    )
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
            fresh.append(HaloRebootNodeButton(coordinator, node.mac))
        if fresh:
            async_add_entities(fresh)

    coordinator.async_add_listener(_discover)
    _discover()


class HaloRebootAllButton(HaloEntity, ButtonEntity):
    """Restart every Halo unit the panel currently lists."""

    _attr_translation_key = "reboot_all"
    _attr_device_class = ButtonDeviceClass.RESTART

    def __init__(self, coordinator: HaloCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_reboot_all"

    async def async_press(self) -> None:
        data = self.coordinator.data
        if data is None or not data.nodes:
            raise HomeAssistantError("no Halo units have been discovered yet")
        try:
            await self.coordinator.async_reboot([node.raw_mac for node in data.nodes])
        except ConfigEntryAuthFailed:
            raise
        except Exception as err:
            raise HomeAssistantError(str(err)) from err


class HaloCheckFirmwareButton(HaloEntity, ButtonEntity):
    """Ask the panel to check for firmware updates."""

    _attr_translation_key = "check_firmware"
    _attr_icon = "mdi:update"

    def __init__(self, coordinator: HaloCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_check_firmware"

    async def async_press(self) -> None:
        try:
            await self.coordinator.async_check_firmware()
        except ConfigEntryAuthFailed:
            raise
        except Exception as err:
            raise HomeAssistantError(str(err)) from err


class HaloRebootNodeButton(HaloNodeEntity, ButtonEntity):
    """Restart one Halo unit discovered from the panel."""

    _attr_translation_key = "reboot"
    _attr_device_class = ButtonDeviceClass.RESTART

    def __init__(self, coordinator: HaloCoordinator, mac: str) -> None:
        super().__init__(coordinator, mac)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_reboot_{mac}"

    async def async_press(self) -> None:
        node = self.node
        if node is None:
            raise HomeAssistantError("this Halo unit is no longer in the panel")
        try:
            await self.coordinator.async_reboot([node.raw_mac])
        except ConfigEntryAuthFailed:
            raise
        except Exception as err:
            raise HomeAssistantError(str(err)) from err
