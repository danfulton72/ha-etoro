"""Functional tests for etoro.api.EToroApiClient against a mocked aiohttp session."""
import json

import pytest

from etoro.api import EToroApiClient, EToroAuthError, EToroConnectionError


class _FakeResponse:
    def __init__(self, status: int, payload):
        self.status = status
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self):
        return self._payload

    async def text(self):
        return json.dumps(self._payload) if not isinstance(self._payload, str) else self._payload


class _FakeSession:
    """Records the last request and returns a pre-configured response."""

    def __init__(self, status=200, payload=None):
        self.status = status
        self.payload = payload if payload is not None else {}
        self.last_url = None
        self.last_params = None
        self.last_headers = None

    def get(self, url, headers=None, params=None, timeout=None):
        self.last_url = url
        self.last_params = params
        self.last_headers = headers
        return _FakeResponse(self.status, self.payload)


def _client(session, environment="real"):
    return EToroApiClient(
        api_key="pk_test", user_key="uk_test", environment=environment, session=session
    )


@pytest.mark.asyncio
async def test_headers_include_required_auth_fields():
    session = _FakeSession(payload={"ok": True})
    client = _client(session)
    await client.get_pnl()
    headers = session.last_headers
    assert headers["x-api-key"] == "pk_test"
    assert headers["x-user-key"] == "uk_test"
    assert "x-request-id" in headers
    assert len(headers["x-request-id"]) == 36  # uuid4 string length


@pytest.mark.asyncio
async def test_get_pnl_uses_environment_scoped_endpoint():
    session = _FakeSession(payload={"clientPortfolio": {}})
    for env in ("real", "demo"):
        client = _client(session, environment=env)
        await client.get_pnl()
        assert session.last_url.endswith(f"/trading/info/{env}/pnl")


@pytest.mark.asyncio
async def test_auth_error_raised_on_401_403():
    for status in (401, 403):
        session = _FakeSession(status=status, payload={"message": "nope"})
        client = _client(session)
        with pytest.raises(EToroAuthError):
            await client.get_pnl()


@pytest.mark.asyncio
async def test_connection_error_raised_on_5xx():
    session = _FakeSession(status=500, payload={"message": "boom"})
    client = _client(session)
    with pytest.raises(EToroConnectionError):
        await client.get_pnl()


@pytest.mark.asyncio
async def test_validate_credentials_true_on_success():
    session = _FakeSession(status=200, payload=[])
    client = _client(session)
    assert await client.validate_credentials() is True


@pytest.mark.asyncio
async def test_validate_credentials_false_on_auth_error():
    session = _FakeSession(status=401, payload={})
    client = _client(session)
    assert await client.validate_credentials() is False


@pytest.mark.asyncio
async def test_validate_credentials_raises_on_connection_error():
    session = _FakeSession(status=500, payload={})
    client = _client(session)
    with pytest.raises(EToroConnectionError):
        await client.validate_credentials()


@pytest.mark.asyncio
async def test_get_watchlists_handles_list_and_wrapped_dict_shapes():
    session = _FakeSession(payload=[{"watchlistId": 1}])
    client = _client(session)
    assert await client.get_watchlists() == [{"watchlistId": 1}]

    session2 = _FakeSession(payload={"watchlists": [{"watchlistId": 2}]})
    client2 = _client(session2)
    assert await client2.get_watchlists() == [{"watchlistId": 2}]


@pytest.mark.asyncio
async def test_get_rates_parses_multiple_casing_variants_and_keys_by_int():
    session = _FakeSession(payload=[
        {"instrumentID": 1001, "bid": 1.1, "ask": 1.2},
        {"InstrumentId": 2002, "bid": 2.1, "ask": 2.2},
    ])
    client = _client(session)
    rates = await client.get_rates([1001, 2002])
    assert set(rates.keys()) == {1001, 2002}
    assert rates[1001]["bid"] == 1.1
    assert rates[2002]["bid"] == 2.1
    # comma-joined ids sent as query param
    assert session.last_params["instrumentIds"] == "1001,2002"


@pytest.mark.asyncio
async def test_get_rates_returns_empty_dict_for_empty_input():
    session = _FakeSession()
    client = _client(session)
    assert await client.get_rates([]) == {}
    assert session.last_url is None  # no request should have been made


@pytest.mark.asyncio
async def test_get_instruments_parses_metadata_by_instrument_id():
    session = _FakeSession(payload={"instruments": [
        {"instrumentId": 1001, "displayname": "Apple Inc", "internalSymbolFull": "AAPL"}
    ]})
    client = _client(session)
    result = await client.get_instruments([1001])
    assert result[1001]["displayname"] == "Apple Inc"
