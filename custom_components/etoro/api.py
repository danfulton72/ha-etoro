"""eToro API client."""
from __future__ import annotations

import uuid
import logging
from typing import Any

import aiohttp

from .const import (
    BASE_URL,
    ENDPOINT_PNL_TEMPLATE,
    ENDPOINT_WATCHLISTS,
    ENDPOINT_WATCHLIST_ITEMS,
    ENDPOINT_RATES,
    ENDPOINT_INSTRUMENTS,
)

_LOGGER = logging.getLogger(__name__)


class EToroAuthError(Exception):
    """Raised when authentication fails."""


class EToroConnectionError(Exception):
    """Raised when connection to eToro API fails."""


class EToroApiClient:
    """Async client for the eToro public API."""

    def __init__(
        self,
        api_key: str,
        user_key: str,
        environment: str,
        session: aiohttp.ClientSession,
    ) -> None:
        self._api_key = api_key
        self._user_key = user_key
        self._environment = environment  # "real" or "demo"
        self._session = session

    def _headers(self) -> dict[str, str]:
        return {
            "x-request-id": str(uuid.uuid4()),
            "x-api-key": self._api_key,
            "x-user-key": self._user_key,
            "Content-Type": "application/json",
        }

    async def _get(self, endpoint: str, params: dict | None = None) -> Any:
        url = BASE_URL + endpoint
        try:
            async with self._session.get(
                url,
                headers=self._headers(),
                params=params,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status in (401, 403):
                    text = await resp.text()
                    raise EToroAuthError(f"HTTP {resp.status}: {text}")
                if resp.status not in (200, 201):
                    text = await resp.text()
                    _LOGGER.error("eToro API error %s on %s: %s", resp.status, url, text)
                    raise EToroConnectionError(f"HTTP {resp.status}: {text}")
                return await resp.json()
        except aiohttp.ClientError as err:
            raise EToroConnectionError(f"Connection error: {err}") from err

    # ------------------------------------------------------------------
    # Portfolio
    # ------------------------------------------------------------------

    async def validate_credentials(self) -> bool:
        """Return True if credentials are valid."""
        try:
            await self._get(ENDPOINT_WATCHLISTS)
            return True
        except EToroAuthError:
            return False
        except EToroConnectionError:
            raise

    async def get_pnl(self) -> dict:
        """Fetch the P&L snapshot for the configured environment."""
        endpoint = ENDPOINT_PNL_TEMPLATE.format(env=self._environment)
        return await self._get(endpoint)

    # ------------------------------------------------------------------
    # Watchlists
    # ------------------------------------------------------------------

    async def get_watchlists(self) -> list[dict]:
        data = await self._get(ENDPOINT_WATCHLISTS)
        _LOGGER.debug("eToro /watchlists raw response: %s", data)
        if isinstance(data, list):
            return data
        return data.get("watchlists", [])

    async def get_watchlist_items(self, watchlist_id: int | str) -> list[dict]:
        """Fetch items for a specific watchlist.

        Returns list of {ItemId, ItemType, ItemRank} dicts.
        ItemType == 'Instrument' for tradeable assets.
        """
        endpoint = ENDPOINT_WATCHLIST_ITEMS.format(watchlist_id=watchlist_id)
        data = await self._get(endpoint)
        if isinstance(data, list):
            return data
        return data.get("items", data.get("watchlistItems", []))

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    async def get_rates(self, instrument_ids: list[int]) -> dict[int, dict]:
        """Fetch live bid/ask rates for a list of instrument IDs.

        API: GET /market-data/instruments/rates?instrumentIds=1,2,3
        Response per item: {instrumentId, bid, ask, lastDailyClose, ...}
        Returns dict keyed by int instrumentId.
        """
        if not instrument_ids:
            return {}
        params = {"instrumentIds": ",".join(str(i) for i in instrument_ids)}
        data = await self._get(ENDPOINT_RATES, params=params)
        _LOGGER.debug("eToro /rates raw response: %s", str(data)[:500])
        rates = data if isinstance(data, list) else data.get("rates", data.get("Rates", []))
        result = {}
        for r in rates:
            iid = (
                r.get("instrumentId")
                or r.get("instrumentID")
                or r.get("InstrumentId")
                or r.get("InstrumentID")
            )
            if iid is not None:
                result[int(iid)] = r
        _LOGGER.debug("eToro rates parsed keys: %s", list(result.keys())[:10])
        return result

    async def get_instruments(self, instrument_ids: list[int]) -> dict[int, dict]:
        """Fetch display metadata (name, symbol) for a list of instrument IDs.

        API: GET /market-data/instruments?instrumentIds=1,2,3&fields=...
        Returns dict keyed by int instrumentId.
        """
        if not instrument_ids:
            return {}
        params = {
            "instrumentIds": ",".join(str(i) for i in instrument_ids),
            "fields": "instrumentId,displayname,internalSymbolFull,instrumentTypeId",
        }
        data = await self._get(ENDPOINT_INSTRUMENTS, params=params)
        instruments = data if isinstance(data, list) else data.get("instruments", data.get("Instruments", []))
        result = {}
        for inst in instruments:
            iid = (
                inst.get("instrumentId")
                or inst.get("instrumentID")
                or inst.get("InstrumentId")
                or inst.get("InstrumentID")
            )
            if iid is not None:
                result[int(iid)] = inst
        _LOGGER.debug("eToro instruments parsed keys: %s", list(result.keys())[:10])
        return result
