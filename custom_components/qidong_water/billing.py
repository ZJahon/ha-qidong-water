"""Residential water tariff calculations for Qidong Water."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

# Qidong residential monthly tier thresholds (m³)
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


def calculate_residential_bill(usage_value: Any) -> dict[str, Decimal | str] | None:
    """Calculate the Qidong residential monthly progressive water bill.

    The progressive part applies only to the base water price. Water-resource,
    household-garbage and sewage-treatment fees are charged per m³ across the
    whole monthly usage.
    """
    usage = to_decimal(usage_value)
    if usage is None or usage < 0:
        return None

    first = min(usage, TIER_1_LIMIT)
    second = min(max(usage - TIER_1_LIMIT, Decimal("0")), TIER_2_LIMIT - TIER_1_LIMIT)
    third = max(usage - TIER_2_LIMIT, Decimal("0"))

    base_raw = (
        first * BASE_PRICE_TIER_1
        + second * BASE_PRICE_TIER_2
        + third * BASE_PRICE_TIER_3
    )
    resource_raw = usage * WATER_RESOURCE_FEE
    garbage_raw = usage * GARBAGE_TREATMENT_FEE
    sewage_raw = usage * SEWAGE_TREATMENT_FEE

    base_cost = money(base_raw)
    resource_fee = money(resource_raw)
    garbage_fee = money(garbage_raw)
    sewage_fee = money(sewage_raw)
    total = money(base_cost + resource_fee + garbage_fee + sewage_fee)

    if usage <= TIER_1_LIMIT:
        tier = "一阶"
        marginal_base_price = BASE_PRICE_TIER_1
        marginal_all_in_price = (
            BASE_PRICE_TIER_1
            + WATER_RESOURCE_FEE
            + GARBAGE_TREATMENT_FEE
            + SEWAGE_TREATMENT_FEE
        )
        remaining = max(TIER_1_LIMIT - usage, Decimal("0"))
    elif usage <= TIER_2_LIMIT:
        tier = "二阶"
        marginal_base_price = BASE_PRICE_TIER_2
        marginal_all_in_price = (
            BASE_PRICE_TIER_2
            + WATER_RESOURCE_FEE
            + GARBAGE_TREATMENT_FEE
            + SEWAGE_TREATMENT_FEE
        )
        remaining = max(TIER_2_LIMIT - usage, Decimal("0"))
    else:
        tier = "三阶"
        marginal_base_price = BASE_PRICE_TIER_3
        marginal_all_in_price = (
            BASE_PRICE_TIER_3
            + WATER_RESOURCE_FEE
            + GARBAGE_TREATMENT_FEE
            + SEWAGE_TREATMENT_FEE
        )
        remaining = Decimal("0")

    effective_price = money(total / usage) if usage > 0 else Decimal("0.00")

    return {
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
