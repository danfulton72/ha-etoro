"""Config flow for eToro integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import EToroApiClient, EToroAuthError, EToroConnectionError
from .const import (
    CONF_API_KEY,
    CONF_ENVIRONMENT,
    CONF_USER_KEY,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    ENV_REAL,
    ENVIRONMENTS,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): str,
        vol.Required(CONF_USER_KEY): str,
        vol.Required(CONF_ENVIRONMENT, default=ENV_REAL): vol.In(ENVIRONMENTS),
        vol.Optional("scan_interval", default=DEFAULT_SCAN_INTERVAL): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=60)
        ),
    }
)


class EToroConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for eToro."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            # Only block a duplicate entry for the SAME environment - real and
            # demo each get their own config entry (see README).
            await self.async_set_unique_id(
                f"{DOMAIN}_{user_input[CONF_ENVIRONMENT]}"
            )
            self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass)
            client = EToroApiClient(
                api_key=user_input[CONF_API_KEY],
                user_key=user_input[CONF_USER_KEY],
                environment=user_input[CONF_ENVIRONMENT],
                session=session,
            )
            try:
                valid = await client.validate_credentials()
                if not valid:
                    errors["base"] = "auth_failed"
            except EToroAuthError:
                errors["base"] = "auth_failed"
            except EToroConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during eToro setup")
                errors["base"] = "unknown"

            if not errors:
                return self.async_create_entry(
                    title=f"eToro ({user_input[CONF_ENVIRONMENT].capitalize()})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> EToroOptionsFlow:
        return EToroOptionsFlow(config_entry)


class EToroOptionsFlow(config_entries.OptionsFlow):
    """Options flow to update scan interval."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema(
            {
                vol.Optional(
                    "scan_interval",
                    default=self._config_entry.options.get(
                        "scan_interval", DEFAULT_SCAN_INTERVAL
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60))
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
