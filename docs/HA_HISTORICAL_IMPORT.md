# One-time historical Supercharger import into Home Assistant

This guide backfills **past** supercharger costs into Home Assistant for charts and cumulative totals. It is separate from the live MQTT sensor, which only publishes when a **new** session receives its cost for the first time.

**Do not insert SQL directly into the Home Assistant database.** Use the [Import Statistics](https://github.com/klausj1/homeassistant-statistics) custom integration instead.

## Overview

```text
Tesla API  -->  importer.py  -->  TeslaMate PostgreSQL
                                        |
                                        v
                          export_ha_statistics.py  -->  CSV files
                                        |
                                        v
                     import_statistics.import_from_file  -->  HA statistics
```

You get two external statistics:

| Statistic ID | Purpose |
|---|---|
| `tesla:supercharger_session_cost` | Per-hour session cost (history chart) |
| `tesla:supercharger_total_cost` | Cumulative total spent over time |

Live updates for new charges continue via optional MQTT (`MQTT_ENABLED=true` in the importer).

---

## Phase 1 — Backfill TeslaMate (if needed)

Ensure historical costs exist in TeslaMate before exporting.

```bash
docker compose run --rm importer python importer.py --lookback 730
```

- `MQTT_ENABLED` can stay `false` for this step.
- Sessions that already have `cost` are skipped unless `OVERWRITE_EXISTING=true`.
- Tesla API typically returns about two years of billing history.

---

## Phase 2 — Export CSV files from TeslaMate

The helper script reads `charging_processes` where `cost IS NOT NULL`, rounds timestamps to the hour (required by Import Statistics), and sums multiple sessions in the same hour.

### Prerequisites

- Python 3 with `psycopg2-binary` (same as the importer)
- TeslaMate DB credentials in your environment (from `.env`)

### Run the export

Both CSV files use the same columns: `statistic_id,start,unit,mean,min,max`.

#### With Docker (recommended)

The container entrypoint is `importer.py`, so override it to run the export script:

```bash
docker compose run --rm \
  --entrypoint python \
  importer export_ha_statistics.py \
  --output-dir /data/ha_export \
  --since 2022-01-01 \
  --unit EUR
```

(`export_ha_statistics.py` at `/app/` is a symlink to `/app/scripts/export_ha_statistics.py`.)

Or with the GHCR image directly (only DB env vars are required, not Tesla credentials):

```bash
docker pull ghcr.io/slallemand/teslamate-supercharger-costs:latest

docker run --rm --env-file .env \
  -v ./data:/data \
  --entrypoint python \
  ghcr.io/slallemand/teslamate-supercharger-costs:latest \
  export_ha_statistics.py \
  --output-dir /data/ha_export \
  --since 2022-01-01 \
  --unit EUR
```

The script prints its path and the CSV header on success. You should see:

```text
Export script: /app/scripts/export_ha_statistics.py
CSV columns: statistic_id,start,unit,mean,min,max
  CSV header: statistic_id,start,unit,mean,min,max
```

Verify both headers before copying to Home Assistant:

```bash
head -1 /data/ha_export/supercharger_session_cost.csv
head -1 /data/ha_export/supercharger_total_cost.csv
# Expected for both: statistic_id,start,unit,mean,min,max
```

#### Without Docker

```bash
cd teslamate-supercharger-costs
export $(grep -v '^#' .env | xargs)

python scripts/export_ha_statistics.py \
  --output-dir ./ha_export \
  --since 2023-01-01 \
  --unit EUR
```

### Options

| Option | Description |
|---|---|
| `--output-dir` | Where to write the CSV files (default: current directory) |
| `--since` | Only sessions from this date (`YYYY-MM-DD`) |
| `--until` | Exclude sessions from this date onward |
| `--unit` | Currency for HA (default: `TARGET_CURRENCY` or `EUR`) |
| `--exclude-geofence NAME` | Skip home (or other) geofences; repeat for multiple names |
| `--session-statistic-id` | Override default `tesla:supercharger_session_cost` |
| `--total-statistic-id` | Override default `tesla:supercharger_total_cost` |

### Output files

Both files use the same columns: `statistic_id`, `start`, `unit`, `mean`, `min`, `max`.

- `supercharger_session_cost.csv` — `mean` = `min` = `max` = total spent that hour
- `supercharger_total_cost.csv` — `mean` = `min` = `max` = cumulative total spent up to that hour

**Currency:** TeslaMate only stores numeric `cost`, not currency. Use the same unit you configured in the importer (`TARGET_CURRENCY`). Mixed-currency histories must be normalized in TeslaMate first.

**Supercharger filter:** TeslaMate does not label “supercharger” explicitly. The export includes all sessions with `cost` set. Exclude home geofences with `--exclude-geofence "Home"` (use your geofence name from TeslaMate).

### Manual SQL alternative

If you prefer not to use the script:

```sql
SELECT cp.start_date,
       cp.cost,
       cp.charge_energy_added AS kwh,
       COALESCE(a.display_name, a.name, 'unknown') AS location
FROM   charging_processes cp
LEFT JOIN addresses a ON a.id = cp.address_id
WHERE  cp.cost IS NOT NULL
  AND  cp.start_date >= '2023-01-01'
ORDER BY cp.start_date ASC;
```

You still need to aggregate to hourly buckets and format CSV columns as above before importing into HA.

---

## Phase 3 — Install Import Statistics in Home Assistant

1. Install [Import Statistics](https://github.com/klausj1/homeassistant-statistics) from HACS.
2. Add to `configuration.yaml`:

   ```yaml
   import_statistics:
   ```

3. Restart Home Assistant.

---

## Phase 4 — Import the CSV files (one-time)

1. Copy both CSV files from `ha_export/` to your Home Assistant config directory (e.g. `/config/ha_export/`).

2. Open **Developer Tools → Actions**.

3. Import session costs:

   ```yaml
   action: import_statistics.import_from_file
   data:
     filename: ha_export/supercharger_session_cost.csv
     delimiter: ","
     decimal: "."
     datetime_format: "%Y-%m-%d %H:%M"
   ```

4. Import cumulative total:

   ```yaml
   action: import_statistics.import_from_file
   data:
     filename: ha_export/supercharger_total_cost.csv
     delimiter: ","
     decimal: "."
     datetime_format: "%Y-%m-%d %H:%M"
   ```

Re-importing the same file overwrites existing statistic points (safe for corrections).

---

## Phase 5 — View in Home Assistant

1. **Developer Tools → Statistics** — search for `tesla:supercharger_session_cost` and `tesla:supercharger_total_cost`.
2. Add **Statistics graph** cards to a dashboard.
3. These are **external statistics** (`:` in the ID), separate from the MQTT entity `sensor.tesla_last_supercharge`.

### MQTT sensor (live updates only)

For new sessions after the backfill, keep MQTT enabled on the importer:

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

---

## Troubleshooting

| Issue | Fix |
|---|---|
| Import fails on timestamps | Minutes must be `:00`; the export script rounds to the hour |
| `mean`, `min`, `max` columns error | Re-export with the latest image; both CSV files need all three columns |
| Wrong currency in graphs | Re-export with `--unit` matching your `TARGET_CURRENCY` |
| Home charges included | Use `--exclude-geofence` with your home geofence name |
| Gaps in history | Hours without a charge are omitted (expected) |
| MQTT vs statistics | MQTT = latest session live; statistics = full historical charts |

---

## What not to do

| Approach | Why |
|---|---|
| SQL insert into HA `recorder` | Unsupported, version-sensitive, can corrupt HA |
| MQTT replay of old sessions | Timestamps would be “now”, not the real charge date |
| `OVERWRITE_EXISTING` + MQTT | MQTT only fires on first-time `cost` writes |
