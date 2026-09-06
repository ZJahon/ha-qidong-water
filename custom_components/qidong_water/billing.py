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
    """Require all monthly volumes from January through the latest bill.

    Missing months are not assumed to be zero: new accounts or non-monthly
    billing require authoritative baseline information before estimation.
    """
    month = normalize_bill_month(latest.get("ysny"))
    if month is None:
        return {"complete": False, "missing_months": [], "reason": "账单月份无效或无历史账单"}
    year, number = map(int, month.split("-"))
    missing = []
    prior = Decimal("0")
    for index in range(1, number + 1):
        key = f"{year:04d}-{index:02d}"
        value = to_decimal(stored.get(key))
        if value is None or not value.is_finite() or value < 0:
            missing.append(key)
        elif index < number:
            prior += value
    current = to_decimal(latest.get("sl"))
    if current is None or not current.is_finite() or current < 0:
        if month not in missing:
            missing.append(month)
    if missing:
        return {"complete": False, "year": year, "missing_months": missing,
                "reason": "年内账单水量不完整，无法准确测算年度阶梯"}
    return {"complete": True, "year": year, "missing_months": [],
            "prior_usage": prior, "annual_usage": prior + current,
            "reason": "按账单月份归属自然年；年内各月水量完整"}
