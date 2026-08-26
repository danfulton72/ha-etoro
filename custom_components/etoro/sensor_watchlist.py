"""eToro watchlist instrument price sensors — one sensor per instrument."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_ENVIRONMENT, DOMAIN
from .coordinator import EToroCoordinator, WatchlistInstrument
from .entity import EToroCoordinatorEntity

_LOGGER = logging.getLogger(__name__)

CURRENCY_USD = "USD"


async def async_setup_watchlist_sensors(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    coordinator: EToroCoordinator,
) -> None:
    """Register one price sensor per watchlist instrument."""
    environment = entry.data.get(CONF_ENVIRONMENT, "real")
    known_ids: set[int] = set()

    def _add_new_entities() -> None:
        new_entities = []
        for instrument in coordinator.data.watchlist_instruments:
            if instrument.instrument_id not in known_ids:
                known_ids.add(instrument.instrument_id)
                new_entities.append(
                    EToroWatchlistSensor(coordinator, instrument, environment)
                )
        if new_entities:
            _LOGGER.debug("Adding %d new watchlist instrument sensors", len(new_entities))
            async_add_entities(new_entities)

    _add_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_entities))


class EToroWatchlistSensor(EToroCoordinatorEntity, SensorEntity):
    """Price sensor for a single instrument in a watchlist."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = CURRENCY_USD
    _attr_icon = "mdi:chart-line"

    def __init__(
        self,
        coordinator: EToroCoordinator,
        instrument: WatchlistInstrument,
        environment: str,
    ) -> None:
        super().__init__(coordinator, environment)
        self._instrument_id = instrument.instrument_id
        self._attr_unique_id = f"etoro_{environment}_watchlist_{instrument.instrument_id}"
        self._attr_name = instrument.display_name
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"etoro_{environment}_watchlist")},
            "name": f"eToro Watchlists ({environment.capitalize()})",
            "manufacturer": "eToro",
            "model": "Watchlist Prices",
            "configuration_url": "https://www.etoro.com/watchlists",
        }

    def _get_instrument(self) -> WatchlistInstrument | None:
        if not self.coordinator.data:
            return None
        return next(
            (
                inst
                for inst in self.coordinator.data.watchlist_instruments
                if inst.instrument_id == self._instrument_id
            ),
            None,
        )

    @property
    def native_value(self) -> float | None:
        inst = self._get_instrument()
        if inst is None:
            return None
        price = inst.mid_price
        return round(price, 6) if price is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        inst = self._get_instrument()
        if inst is None:
            return {}
        return {
            "instrument_id": inst.instrument_id,
            "symbol": inst.symbol,
            "bid": inst.bid,
            "ask": inst.ask,
            "spread": inst.spread,
            "last_daily_close": inst.last_daily_close,
            "watchlists": inst.watchlist_name,
        }

    @property
    def available(self) -> bool:
        return super().available and self._get_instrument() is not None
