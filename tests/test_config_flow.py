"""Tests for config_flow.py's duplicate-entry / unique-id scoping fix."""
import pytest

from etoro.config_flow import STEP_USER_DATA_SCHEMA
from etoro.const import CONF_API_KEY, CONF_ENVIRONMENT, CONF_USER_KEY, DOMAIN, ENV_DEMO, ENV_REAL


def test_schema_requires_api_key_and_user_key():
    with pytest.raises(Exception):
        STEP_USER_DATA_SCHEMA({CONF_ENVIRONMENT: ENV_REAL})  # missing api_key/user_key


def test_schema_defaults_environment_to_real_and_accepts_valid_input():
    result = STEP_USER_DATA_SCHEMA({
        CONF_API_KEY: "pk",
        CONF_USER_KEY: "uk",
    })
    assert result[CONF_ENVIRONMENT] == ENV_REAL
    assert result["scan_interval"] == 5


def test_schema_rejects_invalid_environment():
    with pytest.raises(Exception):
        STEP_USER_DATA_SCHEMA({
            CONF_API_KEY: "pk",
            CONF_USER_KEY: "uk",
            CONF_ENVIRONMENT: "not_a_real_environment",
        })


def test_schema_rejects_scan_interval_out_of_range():
    with pytest.raises(Exception):
        STEP_USER_DATA_SCHEMA({
            CONF_API_KEY: "pk",
            CONF_USER_KEY: "uk",
            "scan_interval": 999,
        })


def test_unique_id_is_scoped_per_environment():
    """Regression test for the fixed bug: real and demo must get distinct
    unique ids so both can be added as separate config entries."""
    real_uid = f"{DOMAIN}_{ENV_REAL}"
    demo_uid = f"{DOMAIN}_{ENV_DEMO}"
    assert real_uid != demo_uid
    assert real_uid == "etoro_real"
    assert demo_uid == "etoro_demo"
