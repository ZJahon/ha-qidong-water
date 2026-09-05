"""Config flow for Qidong Water."""

from __future__ import annotations

import hashlib
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    QidongWaterApi,
    QidongWaterApiError,
    QidongWaterConnectionError,
)

from .const import (
    DOMAIN,
    NAME,
    CONF_WID,

    CONF_UPDATE_INTERVAL,
    CONF_TARIFF_TIER1,
    CONF_TARIFF_TIER2,
    CONF_TARIFF_TIER3,
    CONF_WATER_RESOURCE,
    CONF_GARBAGE,
    CONF_SEWAGE,

    DEFAULT_TARIFF_OPTIONS,
)


def _wid_unique_id(wid: str) -> str:
    """
    Hash wid to avoid exposing it.
    """
    return hashlib.sha256(
        wid.strip().encode("utf-8")
    ).hexdigest()[:24]


async def _validate_input(
    hass: HomeAssistant,
    wid: str,
) -> int:
    """
    Validate wid and return discovered account count.
    """

    api = QidongWaterApi(
        async_get_clientsession(hass),
        wid,
    )

    accounts = await api.async_get_overview()

    return len(
        [
            item
            for item in accounts
            if str(item.get("custcode", "")).strip()
        ]
    )


class QidongWaterConfigFlow(
    config_entries.ConfigFlow,
    domain=DOMAIN,
):
    """
    Handle a config flow for Qidong Water.
    """

    VERSION = 1


    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """
        Initial setup.
        """

        errors = {}

        if user_input:

            wid = user_input[CONF_WID].strip()

            try:

                count = await _validate_input(
                    self.hass,
                    wid,
                )


                if count == 0:

                    errors["base"] = "no_accounts"


                else:

                    await self.async_set_unique_id(
                        _wid_unique_id(wid)
                    )

                    self._abort_if_unique_id_configured()


                    return self.async_create_entry(
                        title=NAME,
                        data={
                            CONF_WID: wid,
                        },
                        options=DEFAULT_TARIFF_OPTIONS,
                    )


            except QidongWaterConnectionError:

                errors["base"] = "cannot_connect"


            except QidongWaterApiError:

                errors["base"] = "invalid_response"


            except Exception:

                errors["base"] = "unknown"



        schema = vol.Schema(
            {
                vol.Required(
                    CONF_WID
                ): TextSelector(
                    TextSelectorConfig(
                        type=TextSelectorType.PASSWORD
                    )
                )
            }
        )


        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )



class QidongWaterOptionsFlow(
    config_entries.OptionsFlow,
):
    """
    Handle Qidong Water options.
    """


    def __init__(
        self,
        config_entry: config_entries.ConfigEntry,
    ) -> None:

        self.config_entry = config_entry



    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """
        Configure options.
        """


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

                #
                # 刷新周期
                #

                vol.Required(
                    CONF_UPDATE_INTERVAL,
                    default=options.get(
                        CONF_UPDATE_INTERVAL,
                        6,
                    ),
                ):
                    vol.All(
                        vol.Coerce(int),
                        vol.Range(
                            min=1,
                            max=168,
                        ),
                    ),



                #
                # 阶梯水价
                #

                vol.Required(
                    CONF_TARIFF_TIER1,
                    default=options.get(
                        CONF_TARIFF_TIER1,
                        2.29,
                    ),
                ):
                    vol.Coerce(float),



                vol.Required(
                    CONF_TARIFF_TIER2,
                    default=options.get(
                        CONF_TARIFF_TIER2,
                        3.435,
                    ),
                ):
                    vol.Coerce(float),



                vol.Required(
                    CONF_TARIFF_TIER3,
                    default=options.get(
                        CONF_TARIFF_TIER3,
                        6.87,
                    ),
                ):
                    vol.Coerce(float),



                #
                # 附加费用
                #

                vol.Required(
                    CONF_WATER_RESOURCE,
                    default=options.get(
                        CONF_WATER_RESOURCE,
                        0.08,
                    ),
                ):
                    vol.Coerce(float),



                vol.Required(
                    CONF_GARBAGE,
                    default=options.get(
                        CONF_GARBAGE,
                        0.26,
                    ),
                ):
                    vol.Coerce(float),



                vol.Required(
                    CONF_SEWAGE,
                    default=options.get(
                        CONF_SEWAGE,
                        0.85,
                    ),
                ):
                    vol.Coerce(float),

            }
        )


        return self.async_show_form(
            step_id="init",
            data_schema=schema,
        )



async def async_get_options_flow(
    config_entry: config_entries.ConfigEntry,
) -> QidongWaterOptionsFlow:
    """
    Return options flow handler.
    """

    return QidongWaterOptionsFlow(
        config_entry
    )
