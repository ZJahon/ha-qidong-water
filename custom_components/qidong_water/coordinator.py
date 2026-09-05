"""Data coordinator for Qidong Water."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import QidongWaterApi, QidongWaterApiError
from .const import DEFAULT_UPDATE_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

AccountData = dict[str, Any]
CoordinatorData = dict[str, AccountData]


class QidongWaterCoordinator(DataUpdateCoordinator[CoordinatorData]):
    """Poll the Qidong Water endpoints and combine account + history data."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: QidongWaterApi,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=DEFAULT_UPDATE_INTERVAL,
        )
        self.api = api

    async def _async_update_data(self) -> CoordinatorData:
        try:
            overview = await self.api.async_get_overview()
        except QidongWaterApiError as err:
            raise UpdateFailed(f"无法获取祁东水务账户数据: {err}") from err

        result: CoordinatorData = {}

        for current in overview:
            custcode = str(current.get("custcode", "")).strip()
            if not custcode:
                continue

            history: list[dict[str, Any]] = []
            history_error: str | None = None
            try:
                history = await self.api.async_get_history(custcode)
            except QidongWaterApiError as err:
                # Keep the account online even when the historical endpoint is
                # temporarily unavailable. History-backed sensors become unknown.
                history_error = str(err)
                _LOGGER.warning("无法获取户号 %s 的历史账单: %s", custcode, err)

            result[custcode] = {
                "current": current,
                "history": history,
                "history_error": history_error,
            }

        if not result:
            raise UpdateFailed("接口返回成功，但没有发现已绑定的水表户号")

        return result
