# TeslaMate Supercharger Cost Importer

[![Docker Image](https://img.shields.io/badge/docker-ghcr.io-blue?logo=docker)](https://github.com/slallemand/teslamate-supercharger-costs/pkgs/container/teslamate-supercharger-costs)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue?logo=python)](https://www.python.org)

Automatically fetches **real Supercharger session costs** from the Tesla ownership API and writes them into your self-hosted [TeslaMate](https://github.com/teslamate-org/teslamate) instance — no manual entry, no fixed per-kWh estimates.

---

## Why this exists

TeslaMate does not natively pull billing data from Tesla. The only built-in option is to set a fixed price per kWh on a geofence — which breaks the moment Tesla changes pricing, when you charge abroad, or when time-of-use rates apply.

This tool solves that by fetching the **actual invoice amount** from the same API your Tesla app uses, then matching it to the correct TeslaMate charging session by timestamp.

```
Tesla API  ──►  importer.py  ──►  TeslaMate PostgreSQL
(real costs)                       (charging_processes.cost)
```

---

## Features

- ✅ Real costs from Tesla — not estimates
- ✅ Handles multiple currencies (CZK, EUR, CHF, USD, …)
- ✅ Includes idle / congestion fees when charged
- ✅ Logs kWh delivered and rate per kWh for each session
- ✅ Safe by default — skips sessions that already have a cost
- ✅ `--dry-run` mode — preview everything before writing
- ✅ Runs as a lightweight Docker container via cron
- ✅ Per-vehicle import via required `TESLA_VIN` (ownership API no longer exposes a vehicle list)
- ✅ Optional MQTT publish to Home Assistant when a session gets its cost for the first time

---

## Prerequisites

- A running **TeslaMate** instance (Docker Compose)
- A **Tesla account** with at least one vehicle
- Docker + Docker Compose on your server
- Pre-built image: `ghcr.io/slallemand/teslamate-supercharger-costs:latest` ([GHCR setup / CI troubleshooting](docs/GHCR_SETUP.md))

---

## Quick start

### 1 — Clone the repository

```bash
git clone https://github.com/kalich5/teslamate-supercharger-costs.git
cd teslamate-supercharger-costs
```

### 2 — Configure

```bash
cp .env.example .env
nano .env   # or your preferred editor
```

And at the end of the file (before networks:) insert:

```dotenv
 suc-importer:
    build: ./teslamate-supercharger-costs
    container_name: teslamate-suc-importer
    restart: "no"
    depends_on:
      - database
    environment:
      TESLA_EMAIL: email@email.cz
      TESLA_VIN: 5YJ3E7EB0KF000000
      TESLA_CACHE_FILE: /data/tesla_cache.json
      TESLAMATE_DB_HOST: database
      TESLAMATE_DB_PORT: 5432
      TESLAMATE_DB_NAME: teslamate
      TESLAMATE_DB_USER: teslamate
      TESLAMATE_DB_PASS: password
      TARGET_CURRENCY: CZK/EUR/CHF/USD (enter only one value here)
      LOOKBACK_DAYS: 30
      TIME_TOLERANCE_S: 600
      OVERWRITE_EXISTING: "false"
      LOG_FILE: /logs/importer.log
    volumes:
      - ./teslamate-supercharger-costs/data:/data
      - ./teslamate-supercharger-costs/logs:/logs
    networks:
      - default
```

Find your DB password in your TeslaMate `docker-compose.yml` under the `database` service (`POSTGRES_PASSWORD`).

### 3 — Connect to the TeslaMate Docker network

The importer must be on the same Docker network as TeslaMate's database. Find your network name:

```bash
docker network ls | grep teslamate
```

Edit `docker-compose.yml` and set the network name:

```yaml
networks:
  teslamate:
    external: true
    name: teslamate_default   # ← replace with your actual network name
```

### 4 — Authorise the Tesla token (one-time)

Run the container interactively the first time. It will ask for your Tesla credentials:

```bash
docker compose run --rm importer
```

You will be prompted for a **refresh token**. Two ways to get one:

**Option A — tesla-info.com (easiest):**
1. Visit [https://tesla-info.com/tesla-token.php](https://tesla-info.com/tesla-token.php)
2. Log in with your Tesla account (the site only brokers the OAuth flow)
3. Copy the `refresh_token` and paste it into the prompt

**Option B — manual OAuth:**
1. Open this URL in your browser and log in:
   ```
   https://auth.tesla.com/oauth2/v3/authorize?client_id=ownerapi&redirect_uri=https://auth.tesla.com/void/callback&response_type=code&scope=openid+email+offline_access+vehicle_device_data+vehicle_charging_cmds&state=state
   ```
2. After login you are redirected to a URL starting with `https://auth.tesla.com/void/callback?code=…`
3. Copy the **entire URL** and paste it into the prompt

The token is saved to `./data/tesla_cache.json` and refreshed automatically — you only do this once.

### 5 — Dry-run (preview)

See exactly what would be written without touching the database:

```bash
docker compose run --rm importer python importer.py --dry-run
```

Example output:

```
2025-11-01 18:15:00  INFO     ═══════════════════════════════════════════════════════
2025-11-01 18:15:00  INFO       TeslaMate Supercharger Cost Importer
2025-11-01 18:15:00  INFO       DB:        teslamate@database:5432/teslamate
2025-11-01 18:15:00  INFO       Lookback:  30 days  |  Tolerance: 120s
2025-11-01 18:15:00  INFO       Mode:      DRY-RUN (no writes)
2025-11-01 18:15:00  INFO     ═══════════════════════════════════════════════════════
2025-11-01 18:15:01  INFO     Using configured VIN: 5YJSA7E52PF497955
2025-11-01 18:15:02  INFO     Retrieved 6 sessions from Tesla API
2025-11-01 18:15:02  INFO       DRY-RUN    #42  2025-11-01 18:13  Humpolec 2   → 75.91 CZK  (75.91  [7.299 kWh @ 10.4 CZK/kWh])
2025-11-01 18:15:02  INFO       DRY-RUN    #43  2025-11-01 18:17  Humpolec 2   → 114.41 CZK (114.41 [11.001 kWh @ 10.4 CZK/kWh])
2025-11-01 18:15:02  INFO       DRY-RUN    #44  2025-11-02 20:39  Pfaffenhofen → 7.98 EUR   (7.98   [22.176 kWh @ 0.36 EUR/kWh])
...
2025-11-01 18:15:02  INFO     ───────────────────────────────────────────────────────
2025-11-01 18:15:02  INFO       DRY-RUN SUMMARY
2025-11-01 18:15:02  INFO       Sessions from Tesla API:    6
2025-11-01 18:15:02  INFO       Would be updated:           6
2025-11-01 18:15:02  INFO     ───────────────────────────────────────────────────────
```

### 6 — Run for real

```bash
docker compose run --rm importer
```

### 7 — Automate with cron

On your server, open the crontab:

```bash
crontab -e
```

Add a line to run the importer daily at 6:00 AM:

```cron
0 6 * * * cd /path/to/teslamate-supercharger-costs && docker compose run --rm importer >> /var/log/tesla_suc_cron.log 2>&1
```

Or twice a day (6:00 and 18:00):

```cron
0 6,18 * * * cd /path/to/teslamate-supercharger-costs && docker compose run --rm importer >> /var/log/tesla_suc_cron.log 2>&1
```

---

## Adding to an existing TeslaMate docker-compose.yml

If you prefer to keep everything in one Compose file, add the importer service directly:

```yaml
services:

  # … your existing teslamate, database, grafana services …

  suc-importer:
    image: ghcr.io/YOUR_USERNAME/teslamate-supercharger-costs:latest
    container_name: teslamate-suc-importer
    restart: "no"
    env_file: ./suc-importer/.env
    volumes:
      - ./suc-importer/data:/data
      - ./suc-importer/logs:/logs
    networks:
      - teslamate   # same network as your database service
```

Then trigger it with:

```bash
docker compose run --rm suc-importer
```

---

## Configuration reference

All settings are environment variables. Set them in your `.env` file.

| Variable | Required | Default | Description |
|---|:---:|---|---|
| `TESLA_EMAIL` | ✅ | — | Tesla account email |
| `TESLAMATE_DB_PASS` | ✅ | — | TeslaMate PostgreSQL password |
| `TESLA_CACHE_FILE` | | `/data/tesla_cache.json` | Path to the OAuth token cache inside the container |
| `TESLA_VIN` | ✅ | — | Vehicle VIN to fetch charging history for |
| `TESLAMATE_DB_HOST` | | `database` | PostgreSQL hostname (Docker service name) |
| `TESLAMATE_DB_PORT` | | `5432` | PostgreSQL port |
| `TESLAMATE_DB_NAME` | | `teslamate` | Database name |
| `TESLAMATE_DB_USER` | | `teslamate` | Database user |
| `LOOKBACK_DAYS` | | `30` | Days of history to fetch from Tesla API per run |
| `TIME_TOLERANCE_S` | | `120` | Max seconds difference for start-time matching |
| `OVERWRITE_EXISTING` | | `false` | Set `true` to overwrite already-set costs |
| `LOG_FILE` | | `/logs/importer.log` | Log file path inside the container |
| `MQTT_ENABLED` | | `false` | Publish new session costs to MQTT |
| `MQTT_HOST` | | — | MQTT broker hostname (required when enabled) |
| `MQTT_PORT` | | `1883` | MQTT broker port |
| `MQTT_USER` | | — | MQTT username (optional) |
| `MQTT_PASSWORD` | | — | MQTT password (optional) |
| `MQTT_TOPIC` | | `teslamate/cars/1/supercharger_cost` | Topic for JSON payload |

---

## CLI reference

```
python importer.py [OPTIONS]

Options:
  -n, --dry-run        Preview changes without writing to the database
  -i, --input FILE     Load sessions from a saved JSON file (for testing)
      --lookback DAYS  Override LOOKBACK_DAYS for this run
  -v, --verbose        Show debug output (skipped/free sessions)
  -h, --help           Show this help message
```

---

## Historical backfill

To import all historical sessions at once:

```bash
docker compose run --rm importer python importer.py --lookback 3650
```

Note: The Tesla API typically returns up to 2 years of history.

---

## How session matching works

The importer matches a Tesla session to a TeslaMate `charging_processes` record by finding the record whose `start_date` is closest to the Tesla API's `chargeStartDateTime`, within `TIME_TOLERANCE_S` seconds (default: 120).

If you see many **NOT FOUND** warnings, try increasing `TIME_TOLERANCE_S` to `300` in your `.env`.

---

## MQTT / Home Assistant

When `MQTT_ENABLED=true` **and** `MQTT_HOST` is set, the importer publishes a JSON message **only when a charging session receives its cost for the first time** (`cost` was previously `NULL`). If MQTT is not configured (default), the importer works exactly as before — TeslaMate import is unaffected.

### Environment

```dotenv
MQTT_ENABLED=true
MQTT_HOST=mosquitto
MQTT_PORT=1883
MQTT_TOPIC=teslamate/cars/1/supercharger_cost
```

Use the hostname of your MQTT broker on the same Docker network as the importer (e.g. Mosquitto or the Home Assistant Mosquitto add-on).

### MQTT payload

Each message is a retained JSON object:

```json
{
  "charging_process_id": 42,
  "cost": 22.02,
  "currency": "EUR",
  "kwh": 55.435,
  "rate": 0.42,
  "location": "Angers Espace Anjou",
  "start_date": "2025-11-01 18:13:00"
}
```

| Field | Source |
|---|---|
| `cost`, `start_date` | `charging_processes` |
| `location` | `addresses.display_name` (TeslaMate geocoding) |
| `kwh` | `charge_energy_added` from TeslaMate; Tesla API billing kWh as fallback |
| `rate` | `cost / kwh` when kWh > 0; else Tesla API rate from import |
| `currency` | `TARGET_CURRENCY` if set; else Tesla API currency (not stored in TeslaMate) |

### Home Assistant sensor

Add to `configuration.yaml`:

```yaml
mqtt:
  sensor:
    - name: "Tesla Last Supercharge"
      unique_id: teslamate_supercharger_last_cost
      state_topic: "teslamate/cars/1/supercharger_cost"
      value_template: "{{ value_json.cost }}"
      unit_of_measurement: "{{ value_json.currency }}"
      device_class: monetary
      icon: mdi:ev-station
      json_attributes_topic: "teslamate/cars/1/supercharger_cost"
```

### Query from TeslaMate database

```sql
SELECT cp.id,
       cp.start_date,
       cp.cost,
       cp.charge_energy_added AS kwh,
       COALESCE(a.display_name, a.name) AS location
FROM   charging_processes cp
LEFT JOIN addresses a ON a.id = cp.address_id
WHERE  cp.cost IS NOT NULL
ORDER BY cp.start_date DESC
LIMIT 1;
```

Currency is not stored in TeslaMate — it is only available in the MQTT message or via `TARGET_CURRENCY`.

### Historical backfill (one-time)

To import **past** session costs into Home Assistant charts and cumulative totals, see [docs/HA_HISTORICAL_IMPORT.md](docs/HA_HISTORICAL_IMPORT.md). This uses a CSV export from TeslaMate and the Import Statistics HACS integration — no SQL writes to the HA database.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Unauthorized` error | Expired or invalid token | Delete `data/tesla_cache.json` and re-run interactively to re-authenticate |
| Many `NOT FOUND` warnings | Clock drift or TeslaMate gap in data | Increase `TIME_TOLERANCE_S` to `300` |
| `Connection refused` on DB | Wrong network or host name | Run `docker network ls` and update the network name in `docker-compose.yml` |
| Sessions with cost already set are skipped | Expected behaviour | Set `OVERWRITE_EXISTING=true` to force re-import |
| No sessions / wrong vehicle | Typo in `TESLA_VIN` | Double-check VIN in Tesla app or TeslaMate, then re-run with `--verbose` |
| MQTT not publishing | `MQTT_ENABLED` false or no new sessions | Enable MQTT; only first-time cost writes trigger publish |
| HA sensor empty after restart | Broker has no retained message | Wait for next new charge, or check `MQTT_HOST` / topic |

---

## 💱 Currency Conversion (NEW)

This importer can automatically convert all charging costs into a single target currency (e.g. CHF).

- Uses European Central Bank (ECB)
- No API key required
- Uses **historical rates based on charging date**
- Cached for performance with fallback to latest rates

Example:

```
228.47 CZK → 9.12 CHF (rate from 2026-04-09)
```

---

## 🔄 Backfill Existing Data (IMPORTANT)

You can convert already stored historical data:

```yaml
LOOKBACK_DAYS: 730
OVERWRITE_EXISTING: "true"
```

Run once:

```bash
docker compose run --rm importer
```

Then revert:

```yaml
OVERWRITE_EXISTING: "false"
LOOKBACK_DAYS: 30
```

This rewrites all past Supercharger costs into your target currency.

---

## 📊 Grafana Analytics (Advanced)

You can now build powerful dashboards in TeslaMate Grafana:

### Cost per km

```sql
SELECT
  d.start_date,
  (d.cost / NULLIF(d.distance, 0)) AS cost_per_km
FROM drives d
WHERE d.distance > 0
```

### Cost per 100 km

```sql
SELECT
  (d.cost / NULLIF(d.distance, 0)) * 100 AS cost_per_100km
FROM drives d
WHERE d.distance > 0
```

### Cost per kWh

```sql
SELECT
  (cp.cost / NULLIF(cp.charge_energy_added, 0)) AS cost_per_kwh
FROM charging_processes cp
WHERE cp.charge_energy_added > 0
```

### Efficiency (kWh/km)

```sql
SELECT
  (d.consumption_kwh / NULLIF(d.distance, 0)) AS kwh_per_km
FROM drives d
WHERE d.distance > 0
```

### 🌍 Map of expensive Superchargers

```sql
SELECT
  cp.latitude,
  cp.longitude,
  (cp.cost / cp.charge_energy_added) AS price
FROM charging_processes cp
WHERE cp.charge_energy_added > 0
```

### 🧠 Anomaly detection

```sql
WITH stats AS (
  SELECT
    AVG(cp.cost / cp.charge_energy_added) AS avg_price,
    STDDEV(cp.cost / cp.charge_energy_added) AS std_price
  FROM charging_processes cp
)
SELECT *
FROM charging_processes cp, stats
WHERE ABS((cp.cost / cp.charge_energy_added) - stats.avg_price) > 2 * stats.std_price
```

---

## 🧠 What this enables

- Unified currency across all sessions
- Accurate historical cost tracking
- Cost/km and cost/kWh analytics
- Detection of expensive charging sessions
- Optimization of charging locations

---

## Project layout

```
.
├── importer.py               # Main script
├── Dockerfile                # Container image definition
├── docker-compose.yml        # Compose file for standalone deployment
├── requirements.txt          # Python dependencies
├── .env.example              # Configuration template
├── .gitignore
├── LICENSE                   # MIT
├── CONTRIBUTING.md
└── README.md
```

---

## Related projects

- [TeslaMate](https://github.com/teslamate-org/teslamate) — the data logger this tool extends
- [TeslaMateAgile](https://github.com/MattJeanes/TeslaMateAgile) — dynamic pricing for home charging (Octopus Agile, Tibber, aWATTar)
- [teslapy](https://github.com/tdorssers/teslapy) — the Python Tesla API client used here

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). All contributions welcome — bug reports, feature requests, and pull requests.

---

## License

[MIT](LICENSE) — use it, fork it, share it.
