"""Residential water tariff calculations for Qidong Water."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from .const import CONF_TIER1_LIMIT, CONF_TIER2_LIMIT

# Default monthly tier thresholds (m³)
TIER_1_LIMIT = Decimal("25")
TIER_2_LIMIT = Decimal("35")

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


def calculate_residential_bill(usage_value: Any, options: dict[str, Any] | None = None) -> dict[str, Decimal | str] | None:
    """Calculate the Qidong residential monthly progressive water bill.

    The progressive part applies only to the base water price. Water-resource,
    household-garbage and sewage-treatment fees are charged per m³ across the
    whole monthly usage.
    """
    usage = to_decimal(usage_value)
    if usage is None or not usage.is_finite() or usage < 0:
        return None

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

    first = min(usage, tier1_limit)
    second = min(max(usage - tier1_limit, Decimal("0")), tier2_limit - tier1_limit)
    third = max(usage - tier2_limit, Decimal("0"))

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

    if usage <= tier1_limit:
        tier = "一阶"
        marginal_base_price = tier1_price
        marginal_all_in_price = (
            tier1_price + resource_price + garbage_price + sewage_price
        )
        remaining = max(tier1_limit - usage, Decimal("0"))
    elif usage <= tier2_limit:
        tier = "二阶"
        marginal_base_price = tier2_price
        marginal_all_in_price = (
            tier2_price + resource_price + garbage_price + sewage_price
        )
        remaining = max(tier2_limit - usage, Decimal("0"))
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
