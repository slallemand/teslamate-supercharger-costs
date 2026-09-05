#!/usr/bin/env python3
"""
One-time export of TeslaMate supercharger costs to CSV files for Home Assistant.

Reads charging sessions from the TeslaMate PostgreSQL database and writes two
CSVs compatible with the Import Statistics custom integration (HACS):

  - supercharger_session_cost.csv  (per-hour session costs, measurement)
  - supercharger_total_cost.csv    (cumulative total spent, measurement)

Run manually after backfilling costs with importer.py. Requires only TeslaMate
DB credentials (same env vars as the importer).

Example:
  export $(grep -v '^#' .env | xargs)
  python scripts/export_ha_statistics.py --output-dir ./ha_export --since 2023-01-01
"""

import argparse
import csv
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

try:
    import psycopg2
except ImportError:
    print("ERROR: psycopg2 is required. Install with: pip install psycopg2-binary")
    sys.exit(1)


def _cfg(key: str, default: str | None = None, required: bool = False) -> str | None:
    val = os.getenv(key, default)
    if required and not val:
        print(f"ERROR: Required environment variable not set: {key}")
        sys.exit(1)
    return val


DB_HOST = _cfg("TESLAMATE_DB_HOST", "database")
DB_PORT = _cfg("TESLAMATE_DB_PORT", "5432")
DB_NAME = _cfg("TESLAMATE_DB_NAME", "teslamate")
DB_USER = _cfg("TESLAMATE_DB_USER", "teslamate")
DB_PASS = _cfg("TESLAMATE_DB_PASS", required=True)

DEFAULT_UNIT = (_cfg("TARGET_CURRENCY", "") or "EUR").upper().strip()
SESSION_STAT_ID = "tesla:supercharger_session_cost"
TOTAL_STAT_ID = "tesla:supercharger_total_cost"
CSV_COLUMNS = ["statistic_id", "start", "unit", "mean", "min", "max"]


def _round_to_hour(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.replace(minute=0, second=0, microsecond=0)


def _parse_date(value: str) -> datetime:
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(f"Invalid date: {value!r} (use YYYY-MM-DD)")


def fetch_sessions(since: datetime | None, until: datetime | None, exclude_geofences: list[str]) -> list[tuple]:
    conn = psycopg2.connect(
        host=DB_HOST,
        port=int(DB_PORT),
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        connect_timeout=10,
    )
    try:
        cur = conn.cursor()
        query = """
            SELECT cp.start_date,
                   cp.cost,
                   COALESCE(a.display_name, a.name, 'unknown') AS location,
                   g.name AS geofence_name
            FROM   charging_processes cp
            LEFT JOIN addresses a ON a.id = cp.address_id
            LEFT JOIN geofences g ON g.id = cp.geofence_id
            WHERE  cp.cost IS NOT NULL
        """
        params: list = []

        if since is not None:
            query += "  AND  cp.start_date >= %s\n"
            params.append(since)
        if until is not None:
            query += "  AND  cp.start_date < %s\n"
            params.append(until)
        if exclude_geofences:
            query += "  AND  (g.name IS NULL OR g.name NOT IN %s)\n"
            params.append(tuple(exclude_geofences))

        query += "ORDER BY cp.start_date ASC"
        cur.execute(query, params)
        return cur.fetchall()
    finally:
        conn.close()


def aggregate_hourly(rows: list[tuple]) -> list[tuple[datetime, float]]:
    """Sum costs per UTC hour (Import Statistics requires hourly timestamps)."""
    hourly: dict[datetime, float] = defaultdict(float)
    for start_date, cost, _location, _geofence in rows:
        hour = _round_to_hour(start_date)
        hourly[hour] += float(cost)
    return sorted(hourly.items())


def write_session_csv(path: Path, hourly: list[tuple[datetime, float]], unit: str, stat_id: str) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        # Import Statistics requires mean, min, and max together for measurements.
        # Per hour we export the total spent; min=max=mean avoids inconsistent
        # values when multiple sessions fall in the same hour.
        writer.writerow(CSV_COLUMNS)
        for hour, total in hourly:
            writer.writerow([
                stat_id,
                hour.strftime("%Y-%m-%d %H:%M"),
                unit,
                f"{total:.4f}",
                f"{total:.4f}",
                f"{total:.4f}",
            ])


def write_total_csv(path: Path, hourly: list[tuple[datetime, float]], unit: str, stat_id: str) -> None:
    cumulative = 0.0
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        # Import Statistics requires mean, min, and max together (same as session CSV).
        # mean=min=max = cumulative total spent up to that hour.
        writer.writerow(CSV_COLUMNS)
        for hour, total in hourly:
            cumulative += total
            writer.writerow([
                stat_id,
                hour.strftime("%Y-%m-%d %H:%M"),
                unit,
                f"{cumulative:.4f}",
                f"{cumulative:.4f}",
                f"{cumulative:.4f}",
            ])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export TeslaMate supercharger costs to Home Assistant statistics CSV files",
    )
    parser.add_argument(
        "--output-dir", "-o", type=Path, default=Path("."),
        help="Directory for output CSV files (default: current directory)",
    )
    parser.add_argument(
        "--since", type=_parse_date, metavar="DATE",
        help="Include sessions from this date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--until", type=_parse_date, metavar="DATE",
        help="Exclude sessions from this date onward (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--unit", default=DEFAULT_UNIT,
        help=f"Currency unit for HA statistics (default: {DEFAULT_UNIT})",
    )
    parser.add_argument(
        "--exclude-geofence", action="append", default=[],
        metavar="NAME",
        help="Exclude sessions tagged with this geofence name (repeatable)",
    )
    parser.add_argument(
        "--session-statistic-id", default=SESSION_STAT_ID,
        help=f"Statistic ID for per-session costs (default: {SESSION_STAT_ID})",
    )
    parser.add_argument(
        "--total-statistic-id", default=TOTAL_STAT_ID,
        help=f"Statistic ID for cumulative total (default: {TOTAL_STAT_ID})",
    )
    args = parser.parse_args()

    print(f"Export script: {Path(__file__).resolve()}")
    print(f"CSV columns: {','.join(CSV_COLUMNS)}")

    rows = fetch_sessions(args.since, args.until, args.exclude_geofence)
    if not rows:
        print("No charging sessions with cost found.")
        sys.exit(0)

    hourly = aggregate_hourly(rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    session_path = args.output_dir / "supercharger_session_cost.csv"
    total_path = args.output_dir / "supercharger_total_cost.csv"

    write_session_csv(session_path, hourly, args.unit, args.session_statistic_id)
    write_total_csv(total_path, hourly, args.unit, args.total_statistic_id)

    expected_header = ",".join(CSV_COLUMNS)
    for path in (session_path, total_path):
        with path.open(encoding="utf-8") as f:
            header = f.readline().strip()
        if header != expected_header:
            print(f"ERROR: unexpected CSV header in {path.name}: {header!r}", file=sys.stderr)
            sys.exit(1)

    total_cost = sum(total for _, total in hourly)
    print(f"Exported {len(rows)} session(s) -> {len(hourly)} hourly bucket(s)")
    print(f"  CSV header: {expected_header}")
    print(f"  Total cost: {total_cost:.2f} {args.unit}")
    print(f"  Session CSV: {session_path}")
    print(f"  Total CSV:   {total_path}")
    print()
    print("Next: copy both CSV files to your Home Assistant config folder and run")
    print("  import_statistics.import_from_file for each (see docs/HA_HISTORICAL_IMPORT.md)")


if __name__ == "__main__":
    main()
