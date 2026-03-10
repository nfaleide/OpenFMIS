#!/usr/bin/env python
"""Load PLSS townships and sections from CSV files into PostGIS.

Usage:
    python scripts/load_plss.py \
        --db postgresql://faleideairbook@localhost:5432/openfmis \
        --townships "/path/to/Townships.csv" \
        --sections "/path/to/Sections Page 1.csv" ["/path/to/Sections Page 2.csv" ...]

The CSVs have a 'geom' column containing WKT MULTIPOLYGON geometry in WGS84.
"""

import argparse
import csv
import sys
import time
from pathlib import Path

# PLSS geom WKT strings can be very long
csv.field_size_limit(10_000_000)

import psycopg2
import psycopg2.extras

BATCH = 2000


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Load PLSS data into PostGIS")
    p.add_argument("--db", required=True, help="PostgreSQL DSN")
    p.add_argument("--townships", required=True, help="Path to Townships.csv")
    p.add_argument("--sections", nargs="+", required=True, help="Paths to Sections Page N.csv files")
    p.add_argument("--truncate", action="store_true", help="Truncate tables before loading")
    return p.parse_args()


def load_townships(conn: psycopg2.extensions.connection, csv_path: str, truncate: bool) -> int:
    print(f"\n→ Loading townships from {csv_path}")
    cur = conn.cursor()

    if truncate:
        cur.execute("TRUNCATE TABLE plss_townships RESTART IDENTITY")
        conn.commit()
        print("  Truncated plss_townships")

    insert_sql = """
        INSERT INTO plss_townships
            (gid, lndkey, state, primer, town, twnfrt, twndir,
             range_, rngdir, rngfrt, twndup, twntype,
             datecreate, datemodifi, label, source, fips_c, geom)
        VALUES %s
    """

    total = 0
    batch: list[tuple] = []
    t0 = time.time()

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            geom_wkt = row.get("geom", "").strip()
            if not geom_wkt:
                continue

            batch.append((
                _int(row.get("gid")),
                row.get("lndkey", "").strip() or None,
                row.get("state", "").strip() or None,
                _int(row.get("primer")),
                _int(row.get("town")),
                row.get("twnfrt", "").strip() or None,
                row.get("twndir", "").strip() or None,
                _int(row.get("range")),
                row.get("rngdir", "").strip() or None,
                row.get("rngfrt", "").strip() or None,
                row.get("twndup", "").strip() or None,
                row.get("twntype", "").strip() or None,
                _date(row.get("datecreate")),
                _date(row.get("datemodifi")),
                row.get("label", "").strip() or None,
                row.get("source", "").strip() or None,
                row.get("fips_c", "").strip() or None,
                f"SRID=4326;{geom_wkt}",
            ))

            if len(batch) >= BATCH:
                psycopg2.extras.execute_values(cur, insert_sql, batch, page_size=BATCH)
                conn.commit()
                total += len(batch)
                batch = []
                _progress(total, t0)

    if batch:
        psycopg2.extras.execute_values(cur, insert_sql, batch, page_size=BATCH)
        conn.commit()
        total += len(batch)

    elapsed = time.time() - t0
    print(f"\n  ✓ Loaded {total:,} townships in {elapsed:.1f}s")
    cur.close()
    return total


def load_sections(conn: psycopg2.extensions.connection, csv_paths: list[str], truncate: bool) -> int:
    cur = conn.cursor()

    if truncate:
        cur.execute("TRUNCATE TABLE plss_sections RESTART IDENTITY")
        conn.commit()
        print("  Truncated plss_sections")

    insert_sql = """
        INSERT INTO plss_sections
            (gid, lndkey, sectn, secfrt, secdup, sectionkey,
             label, mtrs, mc_density, source, fips_c, geom)
        VALUES %s
    """

    total = 0
    t0 = time.time()

    for csv_path in csv_paths:
        print(f"\n→ Loading sections from {csv_path}")
        batch: list[tuple] = []

        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                geom_wkt = row.get("geom", "").strip()
                if not geom_wkt:
                    continue

                batch.append((
                    _int(row.get("gid")),
                    row.get("lndkey", "").strip() or None,
                    _int(row.get("sectn")),
                    row.get("secfrt", "").strip() or None,
                    row.get("secdup", "").strip() or None,
                    row.get("sectionkey", "").strip() or None,
                    row.get("label", "").strip() or None,
                    row.get("mtrs", "").strip() or None,
                    _float(row.get("mc_density")),
                    row.get("source", "").strip() or None,
                    row.get("fips_c", "").strip() or None,
                    f"SRID=4326;{geom_wkt}",
                ))

                if len(batch) >= BATCH:
                    psycopg2.extras.execute_values(cur, insert_sql, batch, page_size=BATCH)
                    conn.commit()
                    total += len(batch)
                    batch = []
                    _progress(total, t0)

        if batch:
            psycopg2.extras.execute_values(cur, insert_sql, batch, page_size=BATCH)
            conn.commit()
            total += len(batch)
            batch = []

    elapsed = time.time() - t0
    print(f"\n  ✓ Loaded {total:,} sections in {elapsed:.1f}s")
    cur.close()
    return total


# ── Helpers ────────────────────────────────────────────────────────────────

def _int(v: str | None) -> int | None:
    if v is None:
        return None
    v = v.strip()
    if not v:
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


def _float(v: str | None) -> float | None:
    if v is None:
        return None
    v = v.strip()
    if not v:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _date(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    return v or None


def _progress(total: int, t0: float) -> None:
    elapsed = time.time() - t0
    rate = total / elapsed if elapsed > 0 else 0
    print(f"  {total:>10,} rows  ({rate:,.0f}/s)", end="\r", flush=True)


def main() -> None:
    args = parse_args()

    print(f"Connecting to {args.db}")
    conn = psycopg2.connect(args.db)

    try:
        load_townships(conn, args.townships, args.truncate)
        load_sections(conn, args.sections, args.truncate)
    finally:
        conn.close()

    print("\n✓ PLSS load complete.")


if __name__ == "__main__":
    main()
