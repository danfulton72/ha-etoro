"""eToro API client."""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

import aiohttp

from .const import (
    BASE_URL,
    ENDPOINT_INSTRUMENTS,
    ENDPOINT_PNL_TEMPLATE,
    ENDPOINT_RATES,
    ENDPOINT_WATCHLIST_ITEMS,
    ENDPOINT_WATCHLISTS,
)

_LOGGER = logging.getLogger(__name__)

_MAX_RATE_LIMIT_RETRIES = 3
_DEFAULT_RETRY_AFTER = 1.0
_MAX_RETRY_AFTER = 60.0


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

        for attempt in range(_MAX_RATE_LIMIT_RETRIES + 1):
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

                    if resp.status == 429:
                        text = await resp.text()
                        if attempt >= _MAX_RATE_LIMIT_RETRIES:
                            raise EToroConnectionError(f"HTTP 429: {text}")

                        retry_after = _parse_retry_after(resp.headers.get("Retry-After"))
                        _LOGGER.warning(
                            "eToro rate limit reached on %s; retrying in %.1fs (%d/%d)",
                            endpoint,
                            retry_after,
                            attempt + 1,
                            _MAX_RATE_LIMIT_RETRIES,
                        )
                        await asyncio.sleep(retry_after)
                        continue

                    if resp.status not in (200, 201):
                        text = await resp.text()
                        _LOGGER.error("eToro API error %s on %s: %s", resp.status, url, text)
                        raise EToroConnectionError(f"HTTP {resp.status}: {text}")

                    return await resp.json()
            except aiohttp.ClientError as err:
                raise EToroConnectionError(f"Connection error: {err}") from err

        raise EToroConnectionError("eToro request failed after rate-limit retries")

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
        for rate in rates:
            iid = _instrument_id(rate)
            if iid is not None:
                result[iid] = rate
        _LOGGER.debug("eToro rates parsed keys: %s", list(result.keys())[:10])
        return result

    async def get_instruments(self, instrument_ids: list[int]) -> dict[int, dict]:
        """Fetch display metadata (name, symbol) for instrument IDs.

        eToro currently returns metadata under ``instrumentDisplayDatas``.
        Older/alternate response shapes are retained as fallbacks because the
        public API has historically varied field casing and wrapper names.
        """
        if not instrument_ids:
            return {}

        params = {"instrumentIds": ",".join(str(i) for i in instrument_ids)}
        data = await self._get(ENDPOINT_INSTRUMENTS, params=params)
        _LOGGER.debug("eToro /instruments raw response: %s", str(data)[:1000])

        if isinstance(data, list):
            instruments = data
        else:
            instruments = (
                data.get("instrumentDisplayDatas")
                or data.get("instruments")
                or data.get("Instruments")
                or data.get("data")
                or []
            )

        result: dict[int, dict] = {}
        for instrument in instruments:
            iid = _instrument_id(instrument)
            if iid is not None:
                result[iid] = instrument

        _LOGGER.debug("eToro instruments parsed keys: %s", list(result.keys())[:10])
        return result


def _instrument_id(data: dict[str, Any]) -> int | None:
    """Return an instrument ID across eToro's known casing variants."""
    iid = (
        data.get("instrumentId")
        or data.get("instrumentID")
        or data.get("InstrumentId")
        or data.get("InstrumentID")
    )
    return int(iid) if iid is not None else None


def _parse_retry_after(value: str | None) -> float:
    """Parse Retry-After seconds, clamped to a sensible polling delay."""
    if value is None:
        return _DEFAULT_RETRY_AFTER
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return _DEFAULT_RETRY_AFTER
    return max(0.0, min(seconds, _MAX_RETRY_AFTER))
