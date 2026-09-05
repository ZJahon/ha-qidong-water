"""HTTP client for Qidong Water (祁东水务)."""

from __future__ import annotations

import json
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

from .const import BASE_URL, HISTORY_PATH, OVERVIEW_PATH, REQUEST_TIMEOUT


class QidongWaterApiError(Exception):
    """Base API error."""


class QidongWaterConnectionError(QidongWaterApiError):
    """Connection to the upstream service failed."""


class QidongWaterInvalidResponse(QidongWaterApiError):
    """The upstream service returned an unexpected response."""


class QidongWaterApi:
    """Small async client for the public-facing Qidong Water H5 endpoints."""

    def __init__(self, session: ClientSession, wid: str) -> None:
        self._session = session
        self._wid = wid.strip()
        self._timeout = ClientTimeout(total=REQUEST_TIMEOUT)

    @property
    def wid(self) -> str:
        """Return the configured WeChat wid identifier."""
        return self._wid

    @staticmethod
    def _headers() -> dict[str, str]:
        # The server accepts normal form-encoded XHR requests. No Cookie is used.
        return {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": BASE_URL,
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/132.0.0.0 Safari/537.36"
            ),
        }

    async def _post_form(self, path: str, data: dict[str, str]) -> Any:
        try:
            async with self._session.post(
                f"{BASE_URL}{path}",
                data=data,
                headers=self._headers(),
                timeout=self._timeout,
            ) as response:
                text = await response.text()
                if response.status != 200:
                    raise QidongWaterConnectionError(
                        f"HTTP {response.status} from {path}"
                    )
        except (ClientError, TimeoutError) as err:
            raise QidongWaterConnectionError(str(err)) from err

        try:
            return json.loads(text)
        except (TypeError, json.JSONDecodeError) as err:
            raise QidongWaterInvalidResponse(
                f"Non-JSON response from {path}: {text[:160]!r}"
            ) from err

    async def async_get_overview(self) -> list[dict[str, Any]]:
        """Return all water accounts bound to this wid."""
        param = json.dumps(
            {"wid": self._wid, "gpsx": 0, "gpsy": 0},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        payload = await self._post_form(OVERVIEW_PATH, {"param": param})

        if not isinstance(payload, dict) or str(payload.get("status")) != "100":
            raise QidongWaterInvalidResponse(
                f"Unexpected overview status: {payload!r}"
            )

        details = payload.get("details")
        if not isinstance(details, list):
            raise QidongWaterInvalidResponse("Overview has no details list")

        return [item for item in details if isinstance(item, dict)]

    async def async_get_history(self, custcode: str) -> list[dict[str, Any]]:
        """Return recent billing/meter history for one customer code."""
        payload = await self._post_form(
            HISTORY_PATH,
            {
                "type": "1",
                "custCode": f"{custcode},1,10,1",
                "wxid": self._wid,
            },
        )

        if not isinstance(payload, dict) or str(payload.get("res")) != "100":
            raise QidongWaterInvalidResponse(
                f"Unexpected history status for {custcode}: {payload!r}"
            )

        data = payload.get("data")
        if not isinstance(data, list):
            return []

        return [item for item in data if isinstance(item, dict)]
