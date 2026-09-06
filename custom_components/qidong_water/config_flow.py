"""Config flow for Qidong Water."""

from __future__ import annotations

import hashlib
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .api import (
    QidongWaterApi,
    QidongWaterApiError,
    QidongWaterConnectionError,
)
from .const import (
    CONF_GARBAGE,
    CONF_SEWAGE,
    CONF_TARIFF_TIER1,
    CONF_TARIFF_TIER2,
    CONF_TARIFF_TIER3,
    CONF_UPDATE_INTERVAL,
    CONF_WATER_RESOURCE,
    CONF_WID,
    DEFAULT_TARIFF_OPTIONS,
    DOMAIN,
    NAME,
)


def _wid_unique_id(wid: str) -> str:
    """Hash the wid so the config-entry unique ID does not expose it."""
    return hashlib.sha256(wid.strip().encode("utf-8")).hexdigest()[:24]


async def _validate_input(hass: HomeAssistant, wid: str) -> int:
    """Validate wid and return number of discovered accounts."""
    api = QidongWaterApi(async_get_clientsession(hass), wid)
    accounts = await api.async_get_overview()
    return len([x for x in accounts if str(x.get("custcode", "")).strip()])


class QidongWaterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Qidong Water."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, str] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}

        if user_input is not None:
            wid = user_input[CONF_WID].strip()
            try:
                count = await _validate_input(self.hass, wid)
                if count == 0:
                    errors["base"] = "no_accounts"
                else:
                    unique_id = _wid_unique_id(wid)
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=NAME,
                        data={CONF_WID: wid},
                        description_placeholders={"count": str(count)},
                    )
            except QidongWaterConnectionError:
                errors["base"] = "cannot_connect"
            except QidongWaterApiError:
                errors["base"] = "invalid_response"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"

        schema = vol.Schema(
            {
                vol.Required(CONF_WID): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                )
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders=description_placeholders,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow."""
        return QidongWaterOptionsFlow()


class QidongWaterOptionsFlow(config_entries.OptionsFlow):
    """Handle Qidong Water options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage options."""

        if user_input is not None:
            return self.async_create_entry(
                title="",
                data=user_input,
            )

        options = {
            **DEFAULT_TARIFF_OPTIONS,
            **self.config_entry.options,
        }

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_UPDATE_INTERVAL,
                    default=options[CONF_UPDATE_INTERVAL],
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=168)),

                vol.Required(
                    CONF_TARIFF_TIER1,
                    default=options[CONF_TARIFF_TIER1],
                ): vol.Coerce(float),

                vol.Required(
                    CONF_TARIFF_TIER2,
                    default=options[CONF_TARIFF_TIER2],
                ): vol.Coerce(float),

                vol.Required(
                    CONF_TARIFF_TIER3,
                    default=options[CONF_TARIFF_TIER3],
                ): vol.Coerce(float),

                vol.Required(
                    CONF_WATER_RESOURCE,
                    default=options[CONF_WATER_RESOURCE],
                ): vol.Coerce(float),

                vol.Required(
                    CONF_GARBAGE,
                    default=options[CONF_GARBAGE],
                ): vol.Coerce(float),

                vol.Required(
                    CONF_SEWAGE,
                    default=options[CONF_SEWAGE],
                ): vol.Coerce(float),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
        )
