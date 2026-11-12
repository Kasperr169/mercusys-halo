"""Config flow for Mercusys Halo."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import callback

from .api import HaloAuthError, HaloClient, HaloConnectionError, HaloError, norm_mac
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .models import parse_nodes

CONF_VERIFY_SSL = "verify_ssl"


def _user_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
            vol.Required(CONF_PASSWORD): str,
            vol.Required(CONF_VERIFY_SSL, default=defaults.get(CONF_VERIFY_SSL, False)): bool,
        }
    )


class HaloConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config entry for one Halo mesh."""

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the panel address and the owner password."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                nodes = await _probe(
                    user_input[CONF_HOST],
                    user_input[CONF_PASSWORD],
                    user_input[CONF_VERIFY_SSL],
                )
            except HaloAuthError:
                errors["base"] = "invalid_auth"
            except (HaloConnectionError, HaloError):
                errors["base"] = "cannot_connect"
            else:
                master = next((node for node in nodes if node.role == "master"), nodes[0])
                await self.async_set_unique_id(norm_mac(master.raw_mac))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=master.name or "Mercusys Halo",
                    data={
                        CONF_HOST: user_input[CONF_HOST].strip(),
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_VERIFY_SSL: user_input[CONF_VERIFY_SSL],
                    },
                )
        return self.async_show_form(step_id="user", data_schema=_user_schema(), errors=errors)

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Start a password update after a rejected login."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the owner password again."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            password = user_input[CONF_PASSWORD]
            try:
                await _probe(entry.data[CONF_HOST], password, entry.data.get(CONF_VERIFY_SSL, False))
            except HaloAuthError:
                errors["base"] = "invalid_auth"
            except (HaloConnectionError, HaloError):
                errors["base"] = "cannot_connect"
            else:
                self.hass.config_entries.async_update_entry(
                    entry,
                    data={**entry.data, CONF_PASSWORD: password},
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return HaloOptionsFlow()


class HaloOptionsFlow(OptionsFlow):
    """Let the poll interval be changed without rewriting the entry."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = int(self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                    )
                }
            ),
        )


async def _probe(host: str, password: str, verify_ssl: bool):
    client = HaloClient(host, password, verify_ssl)
    devices = await client.async_discover()
    return parse_nodes({"device_list": devices})
