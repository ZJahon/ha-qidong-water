"""Constants for the Qidong Water integration."""

from datetime import timedelta

DOMAIN = "qidong_water"
NAME = "祁东水务"

CONF_WID = "wid"

BASE_URL = "https://ccpay.thiscc.com"
OVERVIEW_PATH = "/waterPay/wxpay/getTotalNew.action"
HISTORY_PATH = "/waterPay/search/searchRecord.action"

DEFAULT_UPDATE_INTERVAL = timedelta(hours=6)
REQUEST_TIMEOUT = 20

MANUFACTURER = "祁东县水务集团有限公司"
