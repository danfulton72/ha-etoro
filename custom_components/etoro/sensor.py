"""eToro sensors."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ENVIRONMENT, DOMAIN
from .coordinator import EToroCoordinator, EToroData

_LOGGER = logging.getLogger(__name__)

CURRENCY_USD = "USD"


@dataclass
class EToroSensorEntityDescription(SensorEntityDescription):
    """Extended description with a value extractor."""

    value_fn: Callable[[EToroData], Any] | None = None
    extra_attrs_fn: Callable[[EToroData], dict] | None = None


SENSOR_DESCRIPTIONS: tuple[EToroSensorEntityDescription, ...] = (
    EToroSensorEntityDescription(
        key="equity",
        name="Equity",
        icon="mdi:bank",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=CURRENCY_USD,
        value_fn=lambda d: d.equity,
        extra_attrs_fn=lambda d: {
            "available_cash": d.available_cash,
            "total_invested": d.total_invested,
            "unrealized_pl": d.unrealized_pl,
            "formula": "available_cash + total_invested + unrealized_pl",
        },
    ),
    EToroSensorEntityDescription(
        key="available_cash",
        name="Available Cash",
        icon="mdi:cash",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=CURRENCY_USD,
        value_fn=lambda d: d.available_cash,
        extra_attrs_fn=lambda d: {
            "credit": d.credit,
            "pending_orders": len(d.orders) + len(d.orders_for_open),
        },
    ),
    EToroSensorEntityDescription(
        key="total_invested",
        name="Total Invested",
        icon="mdi:trending-up",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=CURRENCY_USD,
        value_fn=lambda d: d.total_invested,
        extra_attrs_fn=lambda d: {
            "manual_positions": len(d.positions),
            "copy_portfolios": len(d.mirrors),
        },
    ),
    EToroSensorEntityDescription(
        key="unrealized_pl",
        name="Unrealized P&L",
        icon="mdi:chart-line",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=CURRENCY_USD,
        value_fn=lambda d: d.unrealized_pl,
    ),
    EToroSensorEntityDescription(
        key="realized_pl",
        name="Realized P&L",
        icon="mdi:currency-usd",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=CURRENCY_USD,
        value_fn=lambda d: d.realized_pl,
    ),
    EToroSensorEntityDescription(
        key="open_positions",
        name="Open Positions",
        icon="mdi:briefcase",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.open_positions_count,
        extra_attrs_fn=lambda d: {"positions": d.all_positions},
    ),
    EToroSensorEntityDescription(
        key="watchlist_count",
        name="Watchlists",
        icon="mdi:eye",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: len(d.watchlists),
        extra_attrs_fn=lambda d: {
            "watchlists": [
                {"name": w.get("name", ""), "id": w.get("id", w.get("watchlistId", ""))}
                for w in d.watchlists
            ]
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    from .sensor_watchlist import async_setup_watchlist_sensors

    coordinator: EToroCoordinator = hass.data[DOMAIN][entry.entry_id]
    environment = entry.data.get(CONF_ENVIRONMENT, "real")

    # Portfolio summary sensors
    async_add_entities(
        EToroSensor(coordinator, description, environment)
        for description in SENSOR_DESCRIPTIONS
    )

    # One price sensor per watchlist instrument
    await async_setup_watchlist_sensors(hass, entry, async_add_entities, coordinator)


class EToroSensor(CoordinatorEntity[EToroCoordinator], SensorEntity):
    """A single eToro sensor."""

    entity_description: EToroSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EToroCoordinator,
        description: EToroSensorEntityDescription,
        environment: str,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"etoro_{environment}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"etoro_{environment}")},
            "name": f"eToro ({environment.capitalize()})",
            "manufacturer": "eToro",
            "model": f"{environment.capitalize()} Account",
            "configuration_url": "https://www.etoro.com/settings/trade",
        }

    @property
    def native_value(self) -> Any:
        if self.entity_description.value_fn is None:
            return None
        try:
            val = self.entity_description.value_fn(self.coordinator.data)
            if isinstance(val, float):
                return round(val, 2)
            return val
        except Exception:
            _LOGGER.debug("Failed to compute value for %s", self.entity_description.key, exc_info=True)
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if self.entity_description.extra_attrs_fn is None:
            return {}
        try:
            return self.entity_description.extra_attrs_fn(self.coordinator.data)
        except Exception:
            return {}

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self.coordinator.data is not None
