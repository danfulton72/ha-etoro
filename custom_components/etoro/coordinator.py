"""eToro DataUpdateCoordinator."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import EToroApiClient, EToroAuthError, EToroConnectionError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass
class WatchlistInstrument:
    """A single instrument from a watchlist, enriched with live price data."""

    instrument_id: int
    watchlist_id: int | str
    watchlist_name: str
    display_name: str
    symbol: str
    bid: float | None = None
    ask: float | None = None
    last_daily_close: float | None = None
    spread: float | None = None

    @property
    def mid_price(self) -> float | None:
        """Mid-point between bid and ask."""
        if self.bid is not None and self.ask is not None:
            return round((self.bid + self.ask) / 2, 6)
        return self.ask or self.bid

    @property
    def entity_id_suffix(self) -> str:
        """Safe suffix for entity unique_id and slug."""
        symbol = self.symbol or str(self.instrument_id)
        return symbol.lower().replace(" ", "_").replace("/", "_").replace("-", "_")


def _get_ci(d: dict, *keys: str) -> Any:
    """Get the first present key from a dict, trying several casing variants."""
    for key in keys:
        if key in d and d[key] is not None:
            return d[key]
    return None


@dataclass
class EToroData:
    """Snapshot of all data pulled from eToro."""

    pnl_raw: dict[str, Any] = field(default_factory=dict)
    watchlists: list[dict] = field(default_factory=list)
    watchlist_instruments: list[WatchlistInstrument] = field(default_factory=list)
    rates_by_instrument: dict[int, dict] = field(default_factory=dict)
    instruments_by_id: dict[int, dict] = field(default_factory=dict)

    @property
    def _portfolio(self) -> dict:
        return self.pnl_raw.get("clientPortfolio", self.pnl_raw)

    @property
    def credit(self) -> float:
        return float(self._portfolio.get("credit", 0) or 0)

    @property
    def positions(self) -> list[dict]:
        return self._portfolio.get("positions", []) or []

    @property
    def mirrors(self) -> list[dict]:
        return self._portfolio.get("mirrors", []) or []

    @property
    def orders(self) -> list[dict]:
        return self._portfolio.get("orders", []) or []

    @property
    def orders_for_open(self) -> list[dict]:
        return self._portfolio.get("ordersForOpen", []) or []

    @property
    def available_cash(self) -> float:
        manual_pending = sum(
            float(o.get("amount", 0) or 0)
            for o in self.orders_for_open
            if (o.get("mirrorID") or 0) == 0
        )
        mit_orders = sum(float(o.get("amount", 0) or 0) for o in self.orders)
        return round(self.credit - (manual_pending + mit_orders), 2)

    @property
    def unrealized_pl(self) -> float:
        pos_pnl = sum(
            float((p.get("unrealizedPnL") or {}).get("pnL", 0) or 0)
            for p in self.positions
        )
        mirror_pos_pnl = sum(
            float((mp.get("unrealizedPnL") or {}).get("pnL", 0) or 0)
            for m in self.mirrors
            for mp in (m.get("positions") or [])
        )
        mirror_closed_pnl = sum(
            float(m.get("closedPositionsNetProfit", 0) or 0)
            for m in self.mirrors
        )
        return round(pos_pnl + mirror_pos_pnl + mirror_closed_pnl, 2)

    @property
    def total_invested(self) -> float:
        pos_amount = sum(float(p.get("amount", 0) or 0) for p in self.positions)
        mirror_pos_amount = sum(
            float(mp.get("amount", 0) or 0)
            for m in self.mirrors
            for mp in (m.get("positions") or [])
        )
        mirror_available = sum(
            float((m.get("availableAmount", 0) or 0) - (m.get("closedPositionsNetProfit", 0) or 0))
            for m in self.mirrors
        )
        manual_orders_amount = sum(
            float(o.get("amount", 0) or 0)
            for o in self.orders_for_open
            if (o.get("mirrorID") or 0) == 0
        )
        manual_orders_costs = sum(
            float(o.get("totalExternalCosts", 0) or 0)
            for o in self.orders_for_open
            if (o.get("mirrorID") or 0) == 0
        )
        mit_amount = sum(float(o.get("amount", 0) or 0) for o in self.orders)
        return round(
            pos_amount
            + mirror_pos_amount
            + mirror_available
            + manual_orders_amount
            + manual_orders_costs
            + mit_amount,
            2,
        )

    @property
    def equity(self) -> float:
        return round(self.available_cash + self.total_invested + self.unrealized_pl, 2)

    @property
    def realized_pl(self) -> float | None:
        val = self._portfolio.get("realizedPnL") or self._portfolio.get("closedPositionsNetProfit")
        return round(float(val), 2) if val is not None else None

    @property
    def open_positions_count(self) -> int:
        return len(self.positions)

    @property
    def all_positions(self) -> list[dict]:
        result = []
        for p in self.positions:
            iid_raw = _get_ci(p, "instrumentId", "instrumentID", "InstrumentId", "InstrumentID")
            iid = int(iid_raw) if iid_raw is not None else None

            unrealized = p.get("unrealizedPnL") or {}
            current_rate = _get_ci(unrealized, "currentRate", "CurrentRate") or _get_ci(
                p, "currentRate", "CurrentRate"
            )
            if current_rate is None and iid is not None:
                rate = self.rates_by_instrument.get(iid, {})
                bid = rate.get("bid") or rate.get("Bid")
                ask = rate.get("ask") or rate.get("Ask")
                if bid is not None and ask is not None:
                    current_rate = round((float(bid) + float(ask)) / 2, 6)
                else:
                    current_rate = ask or bid

            meta = self.instruments_by_id.get(iid, {}) if iid is not None else {}
            instrument_name = _get_ci(
                meta,
                "instrumentDisplayName",
                "displayname",
                "displayName",
                "DisplayName",
            ) or (f"Instrument {iid}" if iid is not None else "Unknown")
            symbol = _get_ci(
                meta,
                "symbolFull",
                "internalSymbolFull",
                "symbol",
                "Symbol",
            )

            result.append(
                {
                    "instrument_id": iid,
                    "instrument_name": instrument_name,
                    "symbol": symbol,
                    "amount": p.get("amount"),
                    "unrealized_pl": unrealized.get("pnL"),
                    "open_rate": p.get("openRate"),
                    "current_rate": current_rate,
                    "direction": "BUY" if p.get("isBuy", True) else "SELL",
                    "leverage": p.get("leverage"),
                    "open_date": p.get("openDateTime"),
                }
            )
        return result


class EToroCoordinator(DataUpdateCoordinator[EToroData]):
    """Coordinator that fetches all eToro data on a schedule."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: EToroApiClient,
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=scan_interval),
        )
        self.client = client
        self._instrument_metadata_cache: dict[int, dict] = {}

    async def _async_update_data(self) -> EToroData:
        _LOGGER.debug("eToro coordinator update triggered")
        try:
            pnl, watchlists = await asyncio.gather(
                self.client.get_pnl(),
                self.client.get_watchlists(),
                return_exceptions=True,
            )

            if isinstance(pnl, EToroAuthError):
                raise UpdateFailed(f"eToro authentication error: {pnl}") from pnl
            if isinstance(pnl, (EToroConnectionError, Exception)) and not isinstance(pnl, dict):
                raise UpdateFailed(f"eToro PnL error: {pnl}") from pnl

            if isinstance(watchlists, Exception):
                _LOGGER.warning("eToro watchlists fetch failed: %s", watchlists)
                watchlists = []

            _LOGGER.debug("eToro raw PnL response: %s", pnl)

            watchlist_instruments = await self._fetch_watchlist_prices(watchlists)

            position_ids = self._extract_position_instrument_ids(pnl)
            rates_by_instrument: dict[int, dict] = {}

            if position_ids:
                missing_metadata_ids = position_ids - self._instrument_metadata_cache.keys()
                coroutines = [self.client.get_rates(list(position_ids))]
                if missing_metadata_ids:
                    coroutines.append(self.client.get_instruments(list(missing_metadata_ids)))

                results = await asyncio.gather(*coroutines, return_exceptions=True)
                rates_result = results[0]
                if isinstance(rates_result, Exception):
                    _LOGGER.warning("Failed to fetch position rates: %s", rates_result)
                else:
                    rates_by_instrument = rates_result

                if missing_metadata_ids:
                    instruments_result = results[1]
                    if isinstance(instruments_result, Exception):
                        _LOGGER.warning(
                            "Failed to fetch position instrument metadata: %s",
                            instruments_result,
                        )
                    else:
                        self._instrument_metadata_cache.update(instruments_result)

            return EToroData(
                pnl_raw=pnl,
                watchlists=watchlists,
                watchlist_instruments=watchlist_instruments,
                rates_by_instrument=rates_by_instrument,
                instruments_by_id=dict(self._instrument_metadata_cache),
            )

        except UpdateFailed:
            raise
        except Exception as err:
            raise UpdateFailed(f"eToro data fetch failed: {err}") from err

    @staticmethod
    def _extract_position_instrument_ids(pnl: dict) -> set[int]:
        """Collect unique instrument IDs across manual and mirrored positions."""
        portfolio = pnl.get("clientPortfolio", pnl) if isinstance(pnl, dict) else {}
        ids: set[int] = set()

        for p in portfolio.get("positions", []) or []:
            iid = _get_ci(p, "instrumentId", "instrumentID", "InstrumentId", "InstrumentID")
            if iid is not None:
                ids.add(int(iid))

        for m in portfolio.get("mirrors", []) or []:
            for p in m.get("positions") or []:
                iid = _get_ci(p, "instrumentId", "instrumentID", "InstrumentId", "InstrumentID")
                if iid is not None:
                    ids.add(int(iid))

        return ids

    async def _fetch_watchlist_prices(self, watchlists: list[dict]) -> list[WatchlistInstrument]:
        """Extract instruments from embedded watchlist items, then bulk-fetch rates."""
        if not watchlists:
            return []

        instrument_to_watchlists: dict[int, list[tuple[dict, dict]]] = {}

        for wl in watchlists:
            items = wl.get("items") or []
            for item in items:
                item_type = item.get("itemType") or item.get("ItemType") or ""
                if item_type.lower() != "instrument":
                    continue
                iid = item.get("itemId") or item.get("ItemId")
                if iid is None:
                    continue
                iid = int(iid)
                instrument_to_watchlists.setdefault(iid, []).append((wl, item))

        _LOGGER.debug(
            "Total unique instrument IDs found: %d - %s",
            len(instrument_to_watchlists),
            list(instrument_to_watchlists.keys())[:10],
        )

        if not instrument_to_watchlists:
            return []

        all_ids = list(instrument_to_watchlists.keys())
        try:
            rates = await self.client.get_rates(all_ids)
        except Exception as err:
            _LOGGER.warning("Failed to fetch watchlist rates: %s", err)
            rates = {}

        seen: set[int] = set()
        output: list[WatchlistInstrument] = []

        for iid, wl_item_pairs in instrument_to_watchlists.items():
            if iid in seen:
                continue
            seen.add(iid)

            wl, item = wl_item_pairs[0]
            market = item.get("market") or {}
            display_name = market.get("displayName") or market.get("name") or f"Instrument {iid}"
            symbol = market.get("symbolName") or market.get("symbol") or display_name

            all_wl_names = list(
                {
                    (w.get("name") or w.get("displayName") or str(w.get("watchlistId", "")))
                    for w, _ in wl_item_pairs
                }
            )

            rate = rates.get(iid, {})
            bid = _safe_float(rate.get("bid") or rate.get("Bid"))
            ask = _safe_float(rate.get("ask") or rate.get("Ask"))
            last_close = _safe_float(rate.get("lastDailyClose") or rate.get("LastDailyClose"))
            spread = round(ask - bid, 6) if bid is not None and ask is not None else None

            output.append(
                WatchlistInstrument(
                    instrument_id=iid,
                    watchlist_id=wl.get("watchlistId") or wl.get("id", ""),
                    watchlist_name=", ".join(sorted(all_wl_names)),
                    display_name=display_name,
                    symbol=symbol,
                    bid=bid,
                    ask=ask,
                    last_daily_close=last_close,
                    spread=spread,
                )
            )

        return sorted(output, key=lambda x: x.symbol)


def _safe_float(val: Any) -> float | None:
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None
