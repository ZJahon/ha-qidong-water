"""Residential water tariff calculations for Qidong Water."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any
import re

from .const import CONF_TIER1_LIMIT, CONF_TIER2_LIMIT

# Default annual tier thresholds per household (m³)
TIER_1_LIMIT = Decimal("300")
TIER_2_LIMIT = Decimal("420")

# Base water price (CNY/m³)
BASE_PRICE_TIER_1 = Decimal("2.29")
BASE_PRICE_TIER_2 = Decimal("3.435")
BASE_PRICE_TIER_3 = Decimal("6.87")

# Per-m³ charges collected together with the water bill.
WATER_RESOURCE_FEE = Decimal("0.08")
GARBAGE_TREATMENT_FEE = Decimal("0.26")
SEWAGE_TREATMENT_FEE = Decimal("0.85")

MONEY_QUANT = Decimal("0.01")
PRICE_QUANT = Decimal("0.001")


def to_decimal(value: Any) -> Decimal | None:
    """Convert an upstream value to Decimal safely."""
    if value is None:
        return None
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        return None


def money(value: Decimal) -> Decimal:
    """Round a money amount to fen using normal half-up billing rounding."""
    return value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def calculate_residential_bill(usage_value: Any, options: dict[str, Any] | None = None, prior_usage_value: Any = None) -> dict[str, Decimal | str] | None:
    """Calculate one bill using the prior usage in the same calendar year.

    The progressive part applies only to the base water price. Water-resource,
    household-garbage and sewage-treatment fees are charged per m³ across the
    whole billed usage. A known year-to-date baseline is required.
    """
    usage = to_decimal(usage_value)
    if usage is None or not usage.is_finite() or usage < 0:
        return None

    prior_usage = to_decimal(prior_usage_value)
    if prior_usage is None or not prior_usage.is_finite() or prior_usage < 0:
        return None
    annual_usage = prior_usage + usage

    options = options or {}
    tier1_limit = to_decimal(options.get(CONF_TIER1_LIMIT, TIER_1_LIMIT))
    tier2_limit = to_decimal(options.get(CONF_TIER2_LIMIT, TIER_2_LIMIT))
    if (
        tier1_limit is None or tier2_limit is None
        or not tier1_limit.is_finite() or not tier2_limit.is_finite()
        or tier1_limit <= 0 or tier2_limit <= tier1_limit
    ):
        return None
    tier1_price = to_decimal(options.get("tariff_tier1", BASE_PRICE_TIER_1))
    tier2_price = to_decimal(options.get("tariff_tier2", BASE_PRICE_TIER_2))
    tier3_price = to_decimal(options.get("tariff_tier3", BASE_PRICE_TIER_3))
    resource_price = to_decimal(options.get("water_resource_fee", WATER_RESOURCE_FEE))
    garbage_price = to_decimal(options.get("garbage_fee", GARBAGE_TREATMENT_FEE))
    sewage_price = to_decimal(options.get("sewage_fee", SEWAGE_TREATMENT_FEE))

    prices = (tier1_price, tier2_price, tier3_price, resource_price, garbage_price, sewage_price)
    if any(price is None or not price.is_finite() or price < 0 for price in prices):
        return None

    first = max(min(annual_usage, tier1_limit) - min(prior_usage, tier1_limit), Decimal("0"))
    second = max(
        min(annual_usage, tier2_limit) - max(prior_usage, tier1_limit),
        Decimal("0"),
    )
    third = max(annual_usage - max(prior_usage, tier2_limit), Decimal("0"))

    base_raw = (
        first * tier1_price
        + second * tier2_price
        + third * tier3_price
    )
    resource_raw = usage * resource_price
    garbage_raw = usage * garbage_price
    sewage_raw = usage * sewage_price

    base_cost = money(base_raw)
    resource_fee = money(resource_raw)
    garbage_fee = money(garbage_raw)
    sewage_fee = money(sewage_raw)
    total = money(base_cost + resource_fee + garbage_fee + sewage_fee)

    if annual_usage <= tier1_limit:
        tier = "一阶"
        marginal_base_price = tier1_price
        marginal_all_in_price = (
            tier1_price + resource_price + garbage_price + sewage_price
        )
        remaining = max(tier1_limit - annual_usage, Decimal("0"))
    elif annual_usage <= tier2_limit:
        tier = "二阶"
        marginal_base_price = tier2_price
        marginal_all_in_price = (
            tier2_price + resource_price + garbage_price + sewage_price
        )
        remaining = max(tier2_limit - annual_usage, Decimal("0"))
    else:
        tier = "三阶"
        marginal_base_price = tier3_price
        marginal_all_in_price = (
            tier3_price + resource_price + garbage_price + sewage_price
        )
        remaining = Decimal("0")

    effective_price = money(total / usage) if usage > 0 else Decimal("0.00")

    return {
        "tier1_limit": tier1_limit,
        "tier2_limit": tier2_limit,
        "tier1_price": tier1_price,
        "tier2_price": tier2_price,
        "tier3_price": tier3_price,
        "resource_price": resource_price,
        "garbage_price": garbage_price,
        "sewage_price": sewage_price,
        "prior_annual_usage": prior_usage,
        "annual_usage": annual_usage,
        "tier1_usage": first,
        "tier2_usage": second,
        "tier3_usage": third,
        "usage": usage,
        "tier": tier,
        "base_cost": base_cost,
        "water_resource_fee": resource_fee,
        "garbage_treatment_fee": garbage_fee,
        "sewage_treatment_fee": sewage_fee,
        "estimated_total": total,
        "marginal_base_price": marginal_base_price.quantize(PRICE_QUANT),
        "marginal_all_in_price": marginal_all_in_price.quantize(PRICE_QUANT),
        "effective_price": effective_price,
        "remaining_to_next_tier": remaining,
    }


def normalize_bill_month(value: Any) -> str | None:
    """Normalize a billing month without guessing a malformed date."""
    match = re.fullmatch(r"(\d{4})[./-]?(\d{1,2})", str(value).strip())
    if match is None:
        return None
    year, month = map(int, match.groups())
    if not 1 <= year <= 9999 or not 1 <= month <= 12:
        return None
    return f"{year:04d}-{month:02d}"


def merge_usage_history(
    stored: dict[str, Any], history: list[dict[str, Any]],
) -> bool:
    """Upsert monthly volumes; duplicate conflicting rows are ambiguous."""
    observed: dict[str, str | None] = {}
    for row in history:
        month = normalize_bill_month(row.get("ysny"))
        if month is None:
            continue
        usage = to_decimal(row.get("sl"))
        value = str(usage) if usage is not None and usage.is_finite() and usage >= 0 else None
        if month in observed and (
            observed[month] is None or value is None
            or to_decimal(observed[month]) != to_decimal(value)
        ):
            observed[month] = None
        else:
            observed[month] = value
    changed = False
    for month, value in observed.items():
        if month not in stored or stored[month] != value:
            stored[month] = value
            changed = True
    return changed


def annual_usage_context(
    latest: dict[str, Any], stored: dict[str, Any],
) -> dict[str, Any]:
    """Sum issued bills; manual meter readings need not occur every month."""
    month = normalize_bill_month(latest.get("ysny"))
    current = to_decimal(latest.get("sl"))
    if month is None or current is None or not current.is_finite() or current < 0:
        return {"calculable": False, "complete": False, "missing_months": [],
                "reason": "本期账单月份或水量无效，无法测算"}
    year, number = map(int, month.split("-"))
    missing = []
    prior = Decimal("0")
    for index in range(1, number):
        key = f"{year:04d}-{index:02d}"
        if key not in stored:
            # No bill for this month: its consumption may be in a later reading.
            continue
        value = to_decimal(stored[key])
        if value is None or not value.is_finite() or value < 0:
            missing.append(key)
        else:
            prior += value
    # The current row is required; conflicting rows for its month stay invalid.
    if month in stored and stored[month] is None:
        return {"calculable": False, "complete": False, "missing_months": [month],
                "reason": "本期账单水量记录冲突，无法测算"}
    return {"calculable": True, "complete": not missing, "year": year,
            "missing_months": missing, "prior_usage": prior,
            "annual_usage": prior + current,
            "reason": ("已有账单水量无效或冲突：仅按有效记录估算，可能低估阶梯和费用"
                       if missing else "按已记录账单累计；人工抄表可跨月，未单独出账月份无需补零或补算")}


def recorded_year_usage(stored: dict[str, Any], year: int) -> dict[str, Any]:
    """Return recorded billed usage for one year, excluding unbilled usage."""
    values = {}
    for month, raw in stored.items():
        normalized = normalize_bill_month(month)
        value = to_decimal(raw)
        if normalized and normalized.startswith(f"{year:04d}-"):
            values[normalized] = value if value is not None and value.is_finite() and value >= 0 else None
    valid = {month: value for month, value in values.items() if value is not None}
    last = max(values, default=None)
    missing = sorted(month for month, value in values.items() if value is None)
    return {"year": year, "usage": sum(valid.values(), Decimal("0")) if valid else None,
            "months": sorted(valid), "latest_month": last, "missing_months": missing,
            "complete": bool(valid) and not missing}


def infer_fixed_bill_rate(history: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Recognize a recent stable all-in rate, never a legal tariff policy.

    Require three distinct positive-volume bills, including the latest positive
    bill, with explicit zero add-ons. Missing fields are not zero. The candidate
    rate must reproduce each bill after cent rounding. A mismatch ends the run.
    """
    rows = sorted(history, key=lambda row: normalize_bill_month(row.get("ysny")) or "", reverse=True)
    seen: dict[str, tuple[Decimal, ...]] = {}
    rate = None
    months = []
    for row in rows:
        month = normalize_bill_month(row.get("ysny"))
        values = tuple(to_decimal(row.get(key)) for key in ("sl", "sf", "hjfy", "ljclf", "qtxm", "wsclf"))
        if month is None or any(v is None or not v.is_finite() or v < 0 for v in values):
            break
        if month in seen:
            if seen[month] != values:
                return None
            continue
        seen[month] = values
        usage, water, total, garbage, other, sewage = values
        if garbage != 0 or other != 0 or sewage != 0 or water != total:
            break
        if usage == 0:
            if total != 0:
                break
            continue
        candidate = (water / usage).quantize(PRICE_QUANT, rounding=ROUND_HALF_UP)
        if rate is None:
            rate = candidate
        if money(usage * rate) != water:
            break
        months.append(month)
    if rate is None or len(months) < 3:
        return None
    return {"rate": rate, "months": months, "sample_count": len(months)}


def calculate_observed_fixed_bill(usage_value: Any, rate: Decimal) -> dict[str, Decimal | str] | None:
    """Apply an observed all-in rate without adding default residential fees."""
    usage = to_decimal(usage_value)
    if usage is None or not usage.is_finite() or usage < 0:
        return None
    if not rate.is_finite() or rate < 0:
        return None
    total = money(usage * rate)
    return {
        "billing_mode": "observed_fixed",
        "tier": "固定单价（账单识别）",
        "usage": usage,
        "base_cost": total,
        "water_resource_fee": Decimal("0.00"),
        "garbage_treatment_fee": Decimal("0.00"),
        "sewage_treatment_fee": Decimal("0.00"),
        "estimated_total": total,
        "marginal_all_in_price": rate,
        "effective_price": rate if usage else Decimal("0.00"),
    }
