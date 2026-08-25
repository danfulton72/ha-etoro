"""Shared eToro entity helpers."""
from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import EToroCoordinator


class EToroCoordinatorEntity(CoordinatorEntity[EToroCoordinator]):
    """Base entity for eToro coordinator-backed entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EToroCoordinator, environment: str) -> None:
        super().__init__(coordinator)
        self._environment = environment

    @property
    def available(self) -> bool:
        """Return whether coordinator data is available and current."""
        return self.coordinator.last_update_success and self.coordinator.data is not None
