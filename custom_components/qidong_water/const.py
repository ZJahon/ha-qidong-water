"""Constants for the Qidong Water integration."""

from datetime import timedelta

DOMAIN = "qidong_water"
NAME = "祁东水务"

CONF_WID = "wid"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_TARIFF_TIER1 = "tariff_tier1"
CONF_TARIFF_TIER2 = "tariff_tier2"
CONF_TARIFF_TIER3 = "tariff_tier3"
CONF_WATER_RESOURCE = "water_resource_fee"
CONF_GARBAGE = "garbage_fee"
CONF_SEWAGE = "sewage_fee"

DEFAULT_TARIFF_OPTIONS = {
    CONF_UPDATE_INTERVAL: 6,
    CONF_TARIFF_TIER1: 2.29,
    CONF_TARIFF_TIER2: 3.435,
    CONF_TARIFF_TIER3: 6.87,
    CONF_WATER_RESOURCE: 0.08,
    CONF_GARBAGE: 0.26,
    CONF_SEWAGE: 0.85,
}

BASE_URL = "https://ccpay.thiscc.com"
OVERVIEW_PATH = "/waterPay/wxpay/getTotalNew.action"
HISTORY_PATH = "/waterPay/search/searchRecord.action"

DEFAULT_UPDATE_INTERVAL = timedelta(hours=6)
REQUEST_TIMEOUT = 20

MANUFACTURER = "祁东县水务集团有限公司"
