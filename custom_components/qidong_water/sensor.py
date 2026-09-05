"""Sensor platform for Qidong Water."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .billing import calculate_residential_bill, to_decimal
from .const import DOMAIN, MANUFACTURER
from .coordinator import AccountData, QidongWaterCoordinator


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _current(account: AccountData) -> dict[str, Any]:
    value = account.get("current")
    return value if isinstance(value, dict) else {}


def _history(account: AccountData) -> list[dict[str, Any]]:
    value = account.get("history")
    return value if isinstance(value, list) else []


def _latest_history(account: AccountData) -> dict[str, Any]:
    records = _history(account)
    return records[0] if records else {}


def _bill_calc(account: AccountData) -> dict[str, Decimal | str] | None:
    return calculate_residential_bill(_latest_history(account).get("sl"), account.get("billing_options"))


def _bill_calc_number(account: AccountData, key: str) -> float | None:
    calc = _bill_calc(account)
    if calc is None:
        return None
    value = calc.get(key)
    if isinstance(value, Decimal):
        return float(value)
    return None


def _bill_calc_text(account: AccountData, key: str) -> str | None:
    calc = _bill_calc(account)
    if calc is None:
        return None
    value = calc.get(key)
    return str(value) if value is not None else None


def _bill_difference(account: AccountData) -> float | None:
    calc = _bill_calc(account)
    actual = to_decimal(_latest_history(account).get("hjfy"))
    if calc is None or actual is None:
        return None
    estimated = calc.get("estimated_total")
    if not isinstance(estimated, Decimal):
        return None
    return float((actual - estimated).quantize(Decimal("0.01")))


@dataclass(frozen=True, kw_only=True)
class QidongWaterSensorEntityDescription(SensorEntityDescription):
    """Describe a Qidong Water sensor."""

    value_fn: Callable[[AccountData], Any]


SENSORS: tuple[QidongWaterSensorEntityDescription, ...] = (
    # ===== 基础状态 =====
    QidongWaterSensorEntityDescription(
        key="balance",
        name="余额",
        native_unit_of_measurement="CNY",
        device_class=SensorDeviceClass.MONETARY,
        value_fn=lambda a: _to_float(_current(a).get("bcye")),
    ),
    QidongWaterSensorEntityDescription(
        key="meter_reading",
        name="累计表码",
        native_unit_of_measurement="m³",
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda a: _to_float(_current(a).get("sybs")),
    ),
    QidongWaterSensorEntityDescription(
        key="current_usage",
        name="当前待结算水量",
        native_unit_of_measurement="m³",
        device_class=SensorDeviceClass.WATER,
        value_fn=lambda a: _to_float(_current(a).get("sl")),
    ),
    QidongWaterSensorEntityDescription(
        key="amount_due",
        name="当前应缴金额",
        native_unit_of_measurement="CNY",
        device_class=SensorDeviceClass.MONETARY,
        value_fn=lambda a: _to_float(_current(a).get("fee")),
    ),

    # ===== 水务实际账单 =====
    QidongWaterSensorEntityDescription(
        key="latest_bill_month",
        name="最近账单月份",
        value_fn=lambda a: _latest_history(a).get("ysny"),
    ),
    QidongWaterSensorEntityDescription(
        key="latest_bill_usage",
        name="最近账单用水量",
        native_unit_of_measurement="m³",
        device_class=SensorDeviceClass.WATER,
        value_fn=lambda a: _to_float(_latest_history(a).get("sl")),
    ),
    QidongWaterSensorEntityDescription(
        key="latest_bill_total_cost",
        name="最近账单实际总费用",
        native_unit_of_measurement="CNY",
        device_class=SensorDeviceClass.MONETARY,
        value_fn=lambda a: _to_float(_latest_history(a).get("hjfy")),
    ),
    QidongWaterSensorEntityDescription(
        key="latest_bill_water_cost",
        name="最近账单实际水费及代收费（不含污水）",
        native_unit_of_measurement="CNY",
        device_class=SensorDeviceClass.MONETARY,
        value_fn=lambda a: _to_float(_latest_history(a).get("sf")),
    ),
    QidongWaterSensorEntityDescription(
        key="latest_bill_sewage_cost",
        name="最近账单实际污水处理费",
        native_unit_of_measurement="CNY",
        device_class=SensorDeviceClass.MONETARY,
        value_fn=lambda a: _to_float(_latest_history(a).get("wsclf")),
    ),
    QidongWaterSensorEntityDescription(
        key="tracked_actual_cost",
        name="累计实际水费",
        native_unit_of_measurement="CNY",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda a: _to_float(a.get("tracked_actual_cost")),
    ),

    # ===== 阶梯测算 =====
    QidongWaterSensorEntityDescription(
        key="latest_bill_tier",
        name="最近账单阶梯",
        value_fn=lambda a: _bill_calc_text(a, "tier"),
    ),
    QidongWaterSensorEntityDescription(
        key="latest_bill_marginal_price",
        name="最近账单边际综合单价",
        native_unit_of_measurement="CNY/m³",
        value_fn=lambda a: _bill_calc_number(a, "marginal_all_in_price"),
    ),
    QidongWaterSensorEntityDescription(
        key="latest_bill_base_water_cost",
        name="最近账单基础水价费用（测算）",
        native_unit_of_measurement="CNY",
        device_class=SensorDeviceClass.MONETARY,
        value_fn=lambda a: _bill_calc_number(a, "base_cost"),
    ),
    QidongWaterSensorEntityDescription(
        key="latest_bill_water_resource_fee",
        name="最近账单水资源费（测算）",
        native_unit_of_measurement="CNY",
        device_class=SensorDeviceClass.MONETARY,
        value_fn=lambda a: _bill_calc_number(a, "water_resource_fee"),
    ),
    QidongWaterSensorEntityDescription(
        key="latest_bill_garbage_fee",
        name="最近账单生活垃圾处理费（测算）",
        native_unit_of_measurement="CNY",
        device_class=SensorDeviceClass.MONETARY,
        value_fn=lambda a: _bill_calc_number(a, "garbage_treatment_fee"),
    ),
    QidongWaterSensorEntityDescription(
        key="latest_bill_sewage_fee_estimated",
        name="最近账单污水处理费（测算）",
        native_unit_of_measurement="CNY",
        device_class=SensorDeviceClass.MONETARY,
        value_fn=lambda a: _bill_calc_number(a, "sewage_treatment_fee"),
    ),
    QidongWaterSensorEntityDescription(
        key="latest_bill_estimated_total",
        name="最近账单阶梯测算总费用",
        native_unit_of_measurement="CNY",
        device_class=SensorDeviceClass.MONETARY,
        value_fn=lambda a: _bill_calc_number(a, "estimated_total"),
    ),
    QidongWaterSensorEntityDescription(
        key="latest_bill_actual_difference",
        name="最近账单实际与测算差额",
        native_unit_of_measurement="CNY",
        device_class=SensorDeviceClass.MONETARY,
        value_fn=_bill_difference,
    ),
)



async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors and dynamically add newly-bound water accounts."""
    coordinator: QidongWaterCoordinator = entry.runtime_data
    known_accounts: set[str] = set()

    @callback
    def _check_new_accounts() -> None:
        current_accounts = set(coordinator.data or {})
        new_accounts = current_accounts - known_accounts
        if not new_accounts:
            return

        known_accounts.update(new_accounts)
        entities: list[QidongWaterSensor] = []
        for custcode in sorted(new_accounts):
            entities.extend(
                QidongWaterSensor(coordinator, entry, custcode, description)
                for description in SENSORS
            )
        async_add_entities(entities)

    _check_new_accounts()
    entry.async_on_unload(coordinator.async_add_listener(_check_new_accounts))


class QidongWaterSensor(CoordinatorEntity[QidongWaterCoordinator], SensorEntity):
    """Representation of one Qidong Water sensor."""

    entity_description: QidongWaterSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: QidongWaterCoordinator,
        entry: ConfigEntry,
        custcode: str,
        description: QidongWaterSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._custcode = custcode
        entry_uid = entry.unique_id or entry.entry_id
        self._attr_unique_id = f"{entry_uid}_{custcode}_{description.key}"

    @property
    def available(self) -> bool:
        """Return whether this account is present in the latest response."""
        return super().available and self._custcode in (self.coordinator.data or {})

    @property
    def native_value(self) -> Any:
        """Return the sensor value from coordinator memory."""
        account = (self.coordinator.data or {}).get(self._custcode)
        if account is None:
            return None
        return self.entity_description.value_fn(account)

    @property
    def device_info(self) -> DeviceInfo:
        """Group all sensors for one customer code into one HA device."""
        account = (self.coordinator.data or {}).get(self._custcode, {})
        current = _current(account)
        entry_uid = self.coordinator.config_entry.unique_id or self.coordinator.config_entry.entry_id

        customer_name = str(current.get("custname", "")).strip()
        company = str(current.get("cname", MANUFACTURER)).strip() or MANUFACTURER

        display = f"水表 {self._custcode}"
        if customer_name:
            display = f"{display} · {customer_name}"

        return DeviceInfo(
            identifiers={(DOMAIN, f"{entry_uid}_{self._custcode}")},
            name=display,
            manufacturer=company,
            model="祁东水务云端水表账户",
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Attach useful, low-volume metadata to selected sensors."""
        account = (self.coordinator.data or {}).get(self._custcode)
        if account is None:
            return None

        current = _current(account)
        attrs: dict[str, Any] = {"户号": self._custcode}

        if self.entity_description.key == "meter_reading":
            attrs.update(
                {
                    "客户名称": current.get("custname"),
                    "水表地址": current.get("address"),
                    "水表代码": current.get("sbcode"),
                    "本月表数": current.get("bybs"),
                }
            )

        if self.entity_description.key == "latest_bill_month":
            latest = _latest_history(account)
            attrs.update(
                {
                    "上月表数": latest.get("sybs"),
                    "本月表数": latest.get("bybs"),
                    "用水量": latest.get("sl"),
                    "合计费用": latest.get("hjfy"),
                    "实际水费及代收费（不含污水）": latest.get("sf"),
                    "实际污水处理费": latest.get("wsclf"),
                    "最近10期": _history(account)[:10],
                }
            )

        if self.entity_description.key in {
            "latest_bill_tier",
            "latest_bill_estimated_total",
            "latest_bill_actual_difference",
        }:
            calc = _bill_calc(account)
            if calc is not None:
                attrs.update(
                    {
                        "阶梯规则": "月用水≤25m³一阶；25-35m³二阶；>35m³三阶",
                        "一阶基础水价": "2.29 CNY/m³",
                        "二阶基础水价": "3.435 CNY/m³",
                        "三阶基础水价": "6.87 CNY/m³",
                        "水资源费": "0.08 CNY/m³",
                        "生活垃圾处理费": "0.26 CNY/m³",
                        "污水处理费": "0.85 CNY/m³",
                        "距下一阶剩余水量": float(calc["remaining_to_next_tier"]),
                    }
                )

        if self.entity_description.key == "tracked_actual_cost":
            latest = _latest_history(account)
            attrs.update(
                {
                    "数据来源": "水务实际账单 hjfy",
                    "最近已见账单月份": latest.get("ysny"),
                    "最近实际账单": latest.get("hjfy"),
                    "说明": "本地持久化累计，适合作为 HA 能源→水→费用统计；首次启用以接口可见历史账单建立基线。",
                }
            )

        return attrs
