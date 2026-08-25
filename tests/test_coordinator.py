"""Functional tests for etoro.coordinator computed properties and helpers."""
import pytest

from etoro.coordinator import EToroCoordinator, EToroData, _get_ci


def test_get_ci_finds_first_matching_key_variant():
    assert _get_ci({"instrumentID": 5}, "instrumentId", "instrumentID") == 5
    assert _get_ci({"InstrumentId": 7}, "instrumentId", "InstrumentId") == 7
    assert _get_ci({}, "instrumentId", "instrumentID") is None
    assert _get_ci({"instrumentId": None, "instrumentID": 9}, "instrumentId", "instrumentID") == 9


SAMPLE_PNL = {
    "clientPortfolio": {
        "credit": 10000.0,
        "positions": [
            {
                "instrumentId": 1001,
                "amount": 500.0,
                "openRate": 100.0,
                "isBuy": True,
                "leverage": 1,
                "openDateTime": "2025-01-01T00:00:00Z",
                "unrealizedPnL": {"pnL": 25.5},
            },
            {
                "instrumentID": 2002,
                "amount": 300.0,
                "openRate": 50.0,
                "isBuy": False,
                "leverage": 2,
                "openDateTime": "2025-02-01T00:00:00Z",
                "unrealizedPnL": {"pnL": -10.0},
            },
        ],
        "mirrors": [
            {
                "availableAmount": 1000.0,
                "closedPositionsNetProfit": 50.0,
                "positions": [
                    {"amount": 200.0, "unrealizedPnL": {"pnL": 5.0}},
                ],
            }
        ],
        "orders": [{"amount": 100.0}],
        "ordersForOpen": [
            {"amount": 50.0, "mirrorID": 0, "totalExternalCosts": 1.0},
            {"amount": 999.0, "mirrorID": 7},
        ],
        "realizedPnL": 42.0,
    }
}


def test_equity_available_cash_and_invested_math():
    data = EToroData(pnl_raw=SAMPLE_PNL)
    assert data.available_cash == 9850.0
    assert data.unrealized_pl == 70.5
    assert data.total_invested == 2101.0
    assert data.equity == round(data.available_cash + data.total_invested + data.unrealized_pl, 2)
    assert data.realized_pl == 42.0
    assert data.open_positions_count == 2


def test_all_positions_resolves_instrument_id_across_casing_variants():
    data = EToroData(pnl_raw=SAMPLE_PNL)
    positions = data.all_positions
    assert len(positions) == 2
    assert positions[0]["instrument_id"] == 1001
    assert positions[0]["direction"] == "BUY"
    assert positions[0]["unrealized_pl"] == 25.5
    assert positions[1]["instrument_id"] == 2002
    assert positions[1]["direction"] == "SELL"
    assert positions[1]["unrealized_pl"] == -10.0


def test_all_positions_resolves_current_etoro_instrument_metadata():
    data = EToroData(
        pnl_raw=SAMPLE_PNL,
        instruments_by_id={
            1001: {
                "instrumentID": 1001,
                "instrumentDisplayName": "Apple Inc",
                "symbolFull": "AAPL",
            },
            2002: {
                "instrumentID": 2002,
                "instrumentDisplayName": "Tesla Inc",
                "symbolFull": "TSLA",
            },
        },
    )
    positions = data.all_positions
    assert positions[0]["instrument_name"] == "Apple Inc"
    assert positions[0]["symbol"] == "AAPL"
    assert positions[1]["instrument_name"] == "Tesla Inc"
    assert positions[1]["symbol"] == "TSLA"


def test_all_positions_retains_legacy_metadata_field_support():
    data = EToroData(
        pnl_raw=SAMPLE_PNL,
        instruments_by_id={
            1001: {"displayname": "Apple Inc", "internalSymbolFull": "AAPL"},
            2002: {"displayName": "Tesla Inc", "symbol": "TSLA"},
        },
    )
    positions = data.all_positions
    assert positions[0]["instrument_name"] == "Apple Inc"
    assert positions[0]["symbol"] == "AAPL"
    assert positions[1]["instrument_name"] == "Tesla Inc"
    assert positions[1]["symbol"] == "TSLA"


def test_all_positions_falls_back_to_placeholder_name_when_metadata_missing():
    data = EToroData(pnl_raw=SAMPLE_PNL)
    positions = data.all_positions
    assert positions[0]["instrument_name"] == "Instrument 1001"
    assert positions[1]["instrument_name"] == "Instrument 2002"
    assert positions[0]["symbol"] is None


def test_all_positions_falls_back_to_live_rates_for_current_rate():
    data = EToroData(
        pnl_raw=SAMPLE_PNL,
        rates_by_instrument={
            1001: {"bid": 101.0, "ask": 101.4},
            2002: {"Bid": 49.0, "Ask": 49.2},
        },
    )
    positions = data.all_positions
    assert positions[0]["current_rate"] == pytest.approx(101.2)
    assert positions[1]["current_rate"] == pytest.approx(49.1)


def test_all_positions_current_rate_none_when_no_rate_data_available():
    data = EToroData(pnl_raw=SAMPLE_PNL)
    positions = data.all_positions
    assert positions[0]["current_rate"] is None
    assert positions[1]["current_rate"] is None


def test_all_positions_prefers_embedded_current_rate_over_live_lookup():
    pnl = {
        "clientPortfolio": {
            "positions": [
                {
                    "instrumentId": 1001,
                    "amount": 500.0,
                    "openRate": 100.0,
                    "unrealizedPnL": {"pnL": 1.0, "currentRate": 102.5},
                }
            ]
        }
    }
    data = EToroData(pnl_raw=pnl, rates_by_instrument={1001: {"bid": 1.0, "ask": 1.1}})
    assert data.all_positions[0]["current_rate"] == 102.5


def test_empty_portfolio_does_not_error():
    data = EToroData()
    assert data.equity == 0
    assert data.available_cash == 0
    assert data.all_positions == []
    assert data.realized_pl is None


def test_extract_position_instrument_ids_handles_manual_and_mirror_positions():
    pnl = {
        "clientPortfolio": {
            "positions": [{"instrumentId": 1001}, {"instrumentID": 2002}],
            "mirrors": [
                {"positions": [{"InstrumentId": 3003}, {"instrumentId": 1001}]},
            ],
        }
    }
    ids = EToroCoordinator._extract_position_instrument_ids(pnl)
    assert ids == {1001, 2002, 3003}


def test_extract_position_instrument_ids_handles_missing_and_malformed_data():
    assert EToroCoordinator._extract_position_instrument_ids({}) == set()
    assert EToroCoordinator._extract_position_instrument_ids(
        {"clientPortfolio": {}}
    ) == set()
