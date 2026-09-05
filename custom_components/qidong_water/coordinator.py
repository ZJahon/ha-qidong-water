"""Data coordinator for Qidong Water."""

from __future__ import annotations

from decimal import Decimal
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import QidongWaterApi, QidongWaterApiError
from .billing import to_decimal
from .const import (
    DOMAIN,
    CONF_UPDATE_INTERVAL,
    CONF_TARIFF_TIER1,
    CONF_TARIFF_TIER2,
    CONF_TARIFF_TIER3,
    CONF_WATER_RESOURCE,
    CONF_GARBAGE,
    CONF_SEWAGE,
    DEFAULT_TARIFF_OPTIONS,
)


_LOGGER = logging.getLogger(__name__)


AccountData = dict[str, Any]
CoordinatorData = dict[str, AccountData]


_STORAGE_VERSION = 1


class QidongWaterCoordinator(
    DataUpdateCoordinator[CoordinatorData]
):
    """
    Poll Qidong Water and maintain persistent data.
    """


    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: QidongWaterApi,
    ) -> None:

        self.config_entry = entry


        #
        # 读取配置页面参数
        #

        options = {
            **DEFAULT_TARIFF_OPTIONS,
            **entry.options,
        }


        interval = int(
            options.get(
                CONF_UPDATE_INTERVAL,
                6,
            )
        )


        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(
                hours=interval
            ),
        )


        self.api = api


        #
        # 保存水价配置
        #

        self.billing_options = {

            CONF_TARIFF_TIER1:
            float(
                options.get(
                    CONF_TARIFF_TIER1,
                    2.29,
                )
            ),


            CONF_TARIFF_TIER2:
            float(
                options.get(
                    CONF_TARIFF_TIER2,
                    3.435,
                )
            ),


            CONF_TARIFF_TIER3:
            float(
                options.get(
                    CONF_TARIFF_TIER3,
                    6.87,
                )
            ),


            CONF_WATER_RESOURCE:
            float(
                options.get(
                    CONF_WATER_RESOURCE,
                    0.08,
                )
            ),


            CONF_GARBAGE:
            float(
                options.get(
                    CONF_GARBAGE,
                    0.26,
                )
            ),


            CONF_SEWAGE:
            float(
                options.get(
                    CONF_SEWAGE,
                    0.85,
                )
            ),
        }



        self._store: Store[dict[str, Any]] = Store(
            hass,
            _STORAGE_VERSION,
            f"{DOMAIN}.{entry.entry_id}",
        )


        self._billing_state: dict[str, Any] = {
            "accounts": {}
        }



    async def async_initialize(self) -> None:
        """
        Load persistent billing tracker state.
        """

        stored = await self._store.async_load()


        if (
            isinstance(stored, dict)
            and isinstance(
                stored.get("accounts"),
                dict,
            )
        ):
            self._billing_state = stored



    def _update_actual_cost_tracker(
        self,
        custcode: str,
        history: list[dict[str, Any]],
    ) -> tuple[float, bool]:
        """
        Merge actual monthly bills.
        """


        accounts = self._billing_state.setdefault(
            "accounts",
            {},
        )


        tracker = accounts.setdefault(
            custcode,
            {
                "total": "0.00",
                "bills": {},
            },
        )


        bills = tracker.setdefault(
            "bills",
            {},
        )


        total = (
            to_decimal(
                tracker.get("total")
            )
            or Decimal("0.00")
        )


        changed = False



        for record in history:

            month = str(
                record.get(
                    "ysny",
                    "",
                )
            ).strip()


            cost = to_decimal(
                record.get(
                    "hjfy"
                )
            )


            if (
                not month
                or cost is None
                or cost < 0
            ):
                continue



            old_cost = to_decimal(
                bills.get(month)
            )


            if old_cost is None:

                total += cost

                bills[month] = str(cost)

                changed = True


            elif old_cost != cost:

                total += cost - old_cost

                bills[month] = str(cost)

                changed = True



        #
        # 保留120个月账单记录
        #

        if len(bills) > 120:

            for old_month in sorted(bills)[:-120]:

                bills.pop(
                    old_month,
                    None,
                )

                changed = True



        total = max(
            total,
            Decimal("0.00"),
        )


        normalized_total = total.quantize(
            Decimal("0.01")
        )


        if tracker.get("total") != str(normalized_total):

            tracker["total"] = str(
                normalized_total
            )

            changed = True



        return (
            float(normalized_total),
            changed,
        )



    async def _async_update_data(
        self,
    ) -> CoordinatorData:


        try:

            overview = await self.api.async_get_overview()


        except QidongWaterApiError as err:

            raise UpdateFailed(
                f"无法获取祁东水务账户数据: {err}"
            ) from err



        result: CoordinatorData = {}

        storage_changed = False



        for current in overview:


            custcode = str(
                current.get(
                    "custcode",
                    "",
                )
            ).strip()



            if not custcode:

                continue



            history: list[dict[str, Any]] = []

            history_error: str | None = None



            try:

                history = await self.api.async_get_history(
                    custcode
                )


            except QidongWaterApiError as err:


                history_error = str(err)


                _LOGGER.warning(
                    "无法获取户号 %s 的历史账单: %s",
                    custcode,
                    err,
                )



            tracked_actual_cost, changed = (
                self._update_actual_cost_tracker(
                    custcode,
                    history,
                )
            )


            storage_changed = (
                storage_changed
                or changed
            )



            result[custcode] = {

                #
                # 原始接口数据
                #

                "current": current,


                #
                # 历史账单
                #

                "history": history,


                "history_error": history_error,



                #
                # 累计实际费用
                #

                "tracked_actual_cost":
                    tracked_actual_cost,



                #
                # 水价配置
                #

                "billing_options":
                    self.billing_options,



                #
                # 保存原 options
                #

                "options":
                    self.config_entry.options,
            }



        if not result:

            raise UpdateFailed(
                "接口返回成功，但没有发现已绑定的水表户号"
            )



        if storage_changed:

            await self._store.async_save(
                self._billing_state
            )



        return result
