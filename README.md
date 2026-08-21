# eToro Home Assistant Custom Component

A Home Assistant custom integration that pulls portfolio and account data from the [eToro Public API](https://api-portal.etoro.com/).

---

## Sensors created

| Sensor | Description | Unit |
|---|---|---|
| `sensor.etoro_equity` | Total account equity | USD |
| `sensor.etoro_available_cash` | Available cash balance | USD |
| `sensor.etoro_total_invested` | Total amount invested | USD |
| `sensor.etoro_unrealized_pl` | Open position P&L | USD |
| `sensor.etoro_realized_pl` | Closed trade P&L | USD |
| `sensor.etoro_open_positions` | Number of open positions | count |
| `sensor.etoro_watchlists` | Number of watchlists | count |
| `sensor.etoro_account` | Your eToro username | — |

The `open_positions` and `watchlists` sensors expose full detail in their `extra_state_attributes`, usable in automations and the HA dashboard.

---

## Prerequisites

- Home Assistant 2023.6 or later
- A **verified** eToro account
- An eToro API key (see below)

---

## Getting your API keys

1. Log in to eToro and go to **Settings → Trading**
2. Scroll to **API Key Management** and click **Create New Key**
3. Choose:
   - **Environment**: `Real` or `Demo` (one key per environment)
   - **Permissions**: `Read` is sufficient for this integration
4. Verify with the SMS code sent to your phone
5. Copy both the **Public API Key** (`x-api-key`) and **User Key** (`x-user-key`)

---

## Installation

### HACS (recommended)

1. In HACS, go to **Integrations → Custom repositories**
2. Add this repo URL with category **Integration**
3. Install **eToro** from the HACS store
4. Restart Home Assistant

### Manual

1. Copy the `custom_components/etoro/` folder into your HA config directory:
   ```
   config/
   └── custom_components/
       └── etoro/
           ├── __init__.py
           ├── api.py
           ├── config_flow.py
           ├── const.py
           ├── coordinator.py
           ├── manifest.json
           ├── sensor.py
           └── strings.json
   ```
2. Restart Home Assistant

---

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **eToro**
3. Enter your **Public API Key**, **User Key**, environment, and preferred update interval

You can later change the update interval via the **Configure** button on the integration card.

---

## Example dashboard card

```yaml
type: entities
title: eToro Portfolio
entities:
  - entity: sensor.etoro_real_equity
    name: Equity
  - entity: sensor.etoro_real_available_cash
    name: Available Cash
  - entity: sensor.etoro_real_unrealized_pl
    name: Unrealized P&L
  - entity: sensor.etoro_real_open_positions
    name: Open Positions
```

## Example automation — alert on large P&L swing

```yaml
alias: eToro P&L Alert
trigger:
  - platform: numeric_state
    entity_id: sensor.etoro_real_unrealized_pl
    below: -500
action:
  - service: notify.mobile_app_your_phone
    data:
      message: "⚠️ eToro unrealized loss exceeded $500!"
```

---

## Notes

- The eToro API requires a **verified** account. If the API key section doesn't appear in Settings, complete verification first.
- Each API key is scoped to one environment (Demo or Real). Add the integration twice if you want both.
- Default polling interval is 5 minutes. The API has rate limits; avoid setting below 2 minutes.
- This integration uses only read endpoints. No trades are placed.
