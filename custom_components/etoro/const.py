"""Constants for the eToro integration."""

DOMAIN = "etoro"
PLATFORMS = ["sensor"]

CONF_API_KEY = "api_key"
CONF_USER_KEY = "user_key"
CONF_ENVIRONMENT = "environment"

ENV_REAL = "real"
ENV_DEMO = "demo"
ENVIRONMENTS = [ENV_REAL, ENV_DEMO]

DEFAULT_SCAN_INTERVAL = 5  # minutes

BASE_URL = "https://public-api.etoro.com/api/v1"

# Endpoints
# PnL endpoint is environment-scoped: /trading/info/{env}/pnl
# It returns credit, positions, mirrors, orders — everything needed
ENDPOINT_PNL_TEMPLATE = "/trading/info/{env}/pnl"
ENDPOINT_WATCHLISTS = "/watchlists"
ENDPOINT_WATCHLIST_ITEMS = "/watchlists/{watchlist_id}/items"
ENDPOINT_RATES = "/market-data/instruments/rates"
ENDPOINT_INSTRUMENTS = "/market-data/instruments"
ENDPOINT_IDENTITY = "/identity"

ATTR_EQUITY = "equity"
ATTR_AVAILABLE_CASH = "available_cash"
ATTR_TOTAL_INVESTED = "total_invested"
ATTR_UNREALIZED_PL = "unrealized_pl"
ATTR_REALIZED_PL = "realized_pl"
ATTR_POSITIONS = "positions"
ATTR_ENVIRONMENT = "environment"
