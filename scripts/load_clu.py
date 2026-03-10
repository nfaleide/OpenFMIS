#!/usr/bin/env python
"""Load USDA CLU (Common Land Unit) shapefiles into PostGIS.

Usage:
    # Load all states from the three CLU data directories:
    python scripts/load_clu.py \
        --db postgresql://faleideairbook@localhost:5432/openfmis \
        --dirs "/path/to/CLU DATA 1" "/path/to/CLU Data 2" "/path/to/CLU DATA 3"

    # Load a single state only:
    python scripts/load_clu.py --db ... --dirs ... --states nd mn

File structure expected:
    <dir>/<state>/clu/clu_public_a_<state><fips>.zip

Each zip contains a shapefile with:
    - geometry: Polygon (will be cast to MultiPolygon)
    - CALCACRES: float

CRS varies per file (UTM zones) — reprojected to EPSG:4326 on load.
"""

import argparse
import io
import os
import re
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import fiona
import fiona.transform
import psycopg2
import psycopg2.extras
from shapely.geometry import MultiPolygon, Polygon, mapping, shape

BATCH = 500  # Smaller batch — geometries are large


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Load USDA CLU data into PostGIS")
    p.add_argument("--db", required=True, help="PostgreSQL DSN")
    p.add_argument("--dirs", nargs="+", required=True, help="CLU data root directories")
    p.add_argument("--states", nargs="*", help="Limit to these state codes (e.g. nd mn ia)")
    p.add_argument("--truncate", action="store_true", help="Truncate clu table before loading")
    p.add_argument("--workers", type=int, default=1, help="Parallel workers (default 1)")
    return p.parse_args()


def find_zip_files(dirs: list[str], state_filter: list[str] | None) -> list[tuple[str, str, str]]:
    """Return list of (zip_path, state_code, county_fips) tuples."""
    results: list[tuple[str, str, str]] = []
    pattern = re.compile(r"clu_public_a_([a-z]{2})(\d{3})\.zip$", re.IGNORECASE)

    for root_dir in dirs:
        for state_dir in os.listdir(root_dir):
            state = state_dir.lower().strip()
            if state_filter and state not in [s.lower() for s in state_filter]:
                continue
            state_path = os.path.join(root_dir, state_dir)
            if not os.path.isdir(state_path):
                continue

            clu_path = os.path.join(state_path, "clu")
            if not os.path.isdir(clu_path):
                continue

            for fname in os.listdir(clu_path):
                m = pattern.match(fname)
                if m:
                    zip_path = os.path.join(clu_path, fname)
                    state_code = m.group(1).upper()
                    county_fips = f"{state_code}{m.group(2)}"
                    results.append((zip_path, state_code, county_fips))

    results.sort(key=lambda x: (x[1], x[2]))
    return results


def load_zip(
    zip_path: str,
    state: str,
    county_fips: str,
    conn: psycopg2.extensions.connection,
) -> int:
    insert_sql = """
        INSERT INTO clu (state, county_fips, calcacres, geom)
        VALUES %s
    """
    batch: list[tuple] = []
    loaded = 0

    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(tmpdir)
        except zipfile.BadZipFile:
            print(f"  WARN: bad zip {zip_path}", file=sys.stderr)
            return 0

        shp_files = [f for f in os.listdir(tmpdir) if f.endswith(".shp")]
        if not shp_files:
            return 0

        shp_path = os.path.join(tmpdir, shp_files[0])

        try:
            with fiona.open(shp_path) as src:
                src_crs = src.crs_wkt or "EPSG:4326"
                needs_reproject = src.crs is not None and "EPSG:4326" not in str(src.crs).upper()

                cur = conn.cursor()
                for feature in src:
                    try:
                        geom_dict = feature.geometry
                        if geom_dict is None:
                            continue

                        if needs_reproject:
                            geom_dict = fiona.transform.transform_geom(src_crs, "EPSG:4326", geom_dict)

                        geom = shape(geom_dict)
                        if isinstance(geom, Polygon):
                            geom = MultiPolygon([geom])
                        elif not isinstance(geom, MultiPolygon):
                            continue

                        if geom.is_empty:
                            continue

                        calcacres = feature.properties.get("CALCACRES") or feature.properties.get("calcacres")
                        wkt = geom.wkt
                        batch.append((state, county_fips, calcacres, f"SRID=4326;{wkt}"))

                        if len(batch) >= BATCH:
                            psycopg2.extras.execute_values(cur, insert_sql, batch, page_size=BATCH)
                            conn.commit()
                            loaded += len(batch)
                            batch = []

                    except Exception as e:  # noqa: BLE001
                        pass  # skip bad features

                if batch:
                    psycopg2.extras.execute_values(cur, insert_sql, batch, page_size=BATCH)
                    conn.commit()
                    loaded += len(batch)

                cur.close()

        except Exception as e:  # noqa: BLE001
            print(f"  ERROR reading {shp_path}: {e}", file=sys.stderr)

    return loaded


def main() -> None:
    args = parse_args()

    print(f"Connecting to {args.db}")
    conn = psycopg2.connect(args.db)

    if args.truncate:
        cur = conn.cursor()
        cur.execute("TRUNCATE TABLE clu RESTART IDENTITY")
        conn.commit()
        cur.close()
        print("Truncated clu table")

    zip_files = find_zip_files(args.dirs, args.states)
    print(f"Found {len(zip_files):,} county zip files to load\n")

    total = 0
    t0 = time.time()
    state_counts: dict[str, int] = {}

    for i, (zip_path, state, county_fips) in enumerate(zip_files, start=1):
        count = load_zip(zip_path, state, county_fips, conn)
        total += count
        state_counts[state] = state_counts.get(state, 0) + count

        elapsed = time.time() - t0
        rate = total / elapsed if elapsed > 0 else 0
        pct = i / len(zip_files) * 100
        print(
            f"  [{i:>4}/{len(zip_files)}] {state} {county_fips}  "
            f"+{count:>6,}  total={total:>8,}  {rate:>6,.0f}/s  {pct:.1f}%",
            end="\r",
            flush=True,
        )

    elapsed = time.time() - t0
    print(f"\n\n✓ CLU load complete: {total:,} polygons in {elapsed:.1f}s\n")

    print("Records per state:")
    for st, cnt in sorted(state_counts.items()):
        print(f"  {st}: {cnt:>8,}")


if __name__ == "__main__":
    main()
