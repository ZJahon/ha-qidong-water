"""Data coordinator for Qidong Water."""

from __future__ import annotations

from decimal import Decimal
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import QidongWaterApi, QidongWaterApiError
from .billing import merge_usage_history, normalize_bill_month, to_decimal
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

AccountData = dict[str, Any]
CoordinatorData = dict[str, AccountData]

_STORAGE_VERSION = 1


class QidongWaterCoordinator(DataUpdateCoordinator[CoordinatorData]):
    """Poll Qidong Water and maintain a persistent actual-cost accumulator."""

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
            update_interval=timedelta(hours=int(entry.options.get("update_interval", 6))),
        )
        self.api = api
        self._store: Store[dict[str, Any]] = Store(
            hass, _STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self._billing_state: dict[str, Any] = {"accounts": {}}

    async def async_initialize(self) -> None:
        """Load persistent billing tracker state before the first refresh."""
        stored = await self._store.async_load()
        if isinstance(stored, dict) and isinstance(stored.get("accounts"), dict):
            self._billing_state = stored

    def _update_actual_cost_tracker(
        self, custcode: str, history: list[dict[str, Any]]
    ) -> tuple[float, bool]:
        """Merge actual monthly bills into a persistent cumulative counter.

        The upstream history endpoint is a rolling window. Persisting each known
        bill month locally prevents the cumulative cost from dropping when an old
        month disappears from that window. Corrections to a previously seen month
        are applied as a delta.
        """
        accounts = self._billing_state.setdefault("accounts", {})
        tracker = accounts.setdefault(custcode, {"total": "0.00", "bills": {}})
        bills = tracker.setdefault("bills", {})

        total = to_decimal(tracker.get("total")) or Decimal("0.00")
        changed = False

        for record in history:
            month = str(record.get("ysny", "")).strip()
            cost = to_decimal(record.get("hjfy"))
            if not month or cost is None or cost < 0:
                continue

            old_cost = to_decimal(bills.get(month))
            if old_cost is None:
                total += cost
                bills[month] = str(cost)
                changed = True
            elif old_cost != cost:
                total += cost - old_cost
                bills[month] = str(cost)
                changed = True

        # Keep storage compact while still covering many years. Removing old keys
        # does not change the accumulated total; those costs stay in tracker.total.
        if len(bills) > 120:
            for old_month in sorted(bills)[:-120]:
                bills.pop(old_month, None)
                changed = True

        total = max(total, Decimal("0.00"))
        normalized_total = total.quantize(Decimal("0.01"))
        if tracker.get("total") != str(normalized_total):
            tracker["total"] = str(normalized_total)
            changed = True

        return float(normalized_total), changed

    async def _async_update_data(self) -> CoordinatorData:
        try:
            overview = await self.api.async_get_overview()
        except QidongWaterApiError as err:
            raise UpdateFailed(f"无法获取祁东水务账户数据: {err}") from err

        result: CoordinatorData = {}
        storage_changed = False

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

            tracked_actual_cost, changed = self._update_actual_cost_tracker(
                custcode, history
            )
            storage_changed = storage_changed or changed
            tracker = self._billing_state["accounts"][custcode]
            usage_history = tracker.setdefault("usage_history", {})
            usage_changed = merge_usage_history(usage_history, history)
            storage_changed = storage_changed or usage_changed
            history.sort(key=lambda row: normalize_bill_month(row.get("ysny")) or "", reverse=True)

            result[custcode] = {
                "current": current,
                "history": history,
                "history_error": history_error,
                "usage_history": dict(usage_history),
                "tracked_actual_cost": tracked_actual_cost,
                "options": self.config_entry.options,
            }

        if not result:
            raise UpdateFailed("接口返回成功，但没有发现已绑定的水表户号")

        if storage_changed:
            await self._store.async_save(self._billing_state)

        return result
