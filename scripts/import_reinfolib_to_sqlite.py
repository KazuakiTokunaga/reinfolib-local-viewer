from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
from pathlib import Path


DEFAULT_DB_PATH = Path("data/reinfolib.sqlite")
SQM_PER_TSUBO = 3.3025


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS import_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    route_name TEXT NOT NULL,
    station_name TEXT NOT NULL,
    season_from_code INTEGER NOT NULL,
    season_to_code INTEGER NOT NULL,
    zip_path TEXT,
    csv_path TEXT NOT NULL,
    source_encoding TEXT NOT NULL,
    imported_row_count INTEGER NOT NULL DEFAULT 0,
    inserted_row_count INTEGER NOT NULL DEFAULT 0,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    import_run_id INTEGER NOT NULL,
    row_hash TEXT NOT NULL UNIQUE,
    source_row_number INTEGER NOT NULL,

    property_type TEXT,
    price_category TEXT,
    municipality_code TEXT,
    prefecture TEXT,
    municipality TEXT,
    district_name TEXT,
    nearest_station_name TEXT,
    walk_minutes INTEGER,
    trade_price INTEGER,
    floor_plan TEXT,
    area_sqm REAL,
    area_tsubo REAL,
    price_per_tsubo REAL,
    building_year INTEGER,
    age_years INTEGER,
    structure TEXT,
    usage TEXT,
    future_use TEXT,
    city_planning TEXT,
    coverage_ratio REAL,
    floor_area_ratio REAL,
    period_year INTEGER,
    period_quarter INTEGER,
    period_code INTEGER,
    renovation TEXT,
    remarks TEXT,

    property_type_raw TEXT,
    price_category_raw TEXT,
    building_year_raw TEXT,
    period_raw TEXT,
    walk_minutes_raw TEXT,
    trade_price_raw TEXT,
    area_sqm_raw TEXT,
    coverage_ratio_raw TEXT,
    floor_area_ratio_raw TEXT,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (import_run_id) REFERENCES import_runs(id)
);

CREATE INDEX IF NOT EXISTS idx_transactions_import_run_id
    ON transactions(import_run_id);

CREATE INDEX IF NOT EXISTS idx_transactions_station_period
    ON transactions(nearest_station_name, period_code);

CREATE INDEX IF NOT EXISTS idx_transactions_municipality
    ON transactions(municipality_code);

CREATE INDEX IF NOT EXISTS idx_transactions_walk
    ON transactions(walk_minutes);

CREATE TABLE IF NOT EXISTS apartment_master (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    apartment_name TEXT NOT NULL,
    address TEXT NOT NULL,
    nearest_station_name TEXT,
    walk_minutes INTEGER,
    built_date TEXT,
    building_year INTEGER,
    source_row_number INTEGER NOT NULL,
    row_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS transaction_apartment_matches (
    transaction_id INTEGER NOT NULL,
    apartment_master_id INTEGER NOT NULL,
    walk_diff INTEGER NOT NULL,
    matched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (transaction_id, apartment_master_id),
    FOREIGN KEY (transaction_id) REFERENCES transactions(id),
    FOREIGN KEY (apartment_master_id) REFERENCES apartment_master(id)
);

CREATE INDEX IF NOT EXISTS idx_apartment_master_address_year
    ON apartment_master(address, building_year);

CREATE INDEX IF NOT EXISTS idx_match_transaction
    ON transaction_apartment_matches(transaction_id);
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "不動産情報ライブラリの Web UI から取得した CSV を SQLite に取り込みます。"
        )
    )
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--csv-path", type=Path, required=True)
    parser.add_argument("--route-name", required=True)
    parser.add_argument("--station-name", required=True)
    parser.add_argument("--season-from", required=True)
    parser.add_argument("--season-to", required=True)
    parser.add_argument("--zip-path", type=Path)
    return parser.parse_args()


def decode_csv(csv_path: Path) -> tuple[str, str]:
    raw = csv_path.read_bytes()
    for encoding in ("utf-8-sig", "cp932"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"未対応の文字コードです: {csv_path}")


def normalize_int(value: str) -> int | None:
    normalized = value.replace(",", "").replace("円", "").replace("年", "").strip()
    if not normalized:
        return None
    return int(normalized)


def normalize_float(value: str) -> float | None:
    normalized = (
        value.replace(",", "")
        .replace("㎡", "")
        .replace("％", "")
        .strip()
    )
    if not normalized:
        return None
    return float(normalized)


def parse_walk_minutes(value: str) -> int | None:
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.isdigit():
        return int(normalized)
    return None


def parse_period(period_raw: str) -> tuple[int | None, int | None, int | None]:
    if not period_raw:
        return None, None, None
    normalized = period_raw.replace("年", "").replace("第", "").replace("四半期", "").strip()
    if len(normalized) < 5:
        return None, None, None
    year = int(normalized[:4])
    quarter = int(normalized[4:])
    return year, quarter, int(f"{year}{quarter}")


def season_to_code(season: str) -> int:
    year, quarter, code = parse_period(season)
    if year is None or quarter is None or code is None:
        raise RuntimeError(f"取引時期を解釈できません: {season}")
    return code


def row_hash_for(row: dict[str, str], route_name: str, station_name: str) -> str:
    payload = {
        "route_name": route_name,
        "station_name": station_name,
        "row": row,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA_SQL)
    existing_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(transactions)")
    }
    if "area_tsubo" not in existing_columns:
        connection.execute("ALTER TABLE transactions ADD COLUMN area_tsubo REAL")
    if "price_per_tsubo" not in existing_columns:
        connection.execute("ALTER TABLE transactions ADD COLUMN price_per_tsubo REAL")
    if "age_years" not in existing_columns:
        connection.execute("ALTER TABLE transactions ADD COLUMN age_years INTEGER")
    connection.commit()


def backfill_derived_columns(connection: sqlite3.Connection) -> None:
    connection.execute(
        f"""
        UPDATE transactions
        SET
            area_tsubo = CASE
                WHEN area_sqm IS NULL OR area_sqm <= 0 THEN NULL
                ELSE area_sqm / {SQM_PER_TSUBO}
            END,
            price_per_tsubo = CASE
                WHEN trade_price IS NULL OR area_sqm IS NULL OR area_sqm <= 0 THEN NULL
                ELSE trade_price / (area_sqm / {SQM_PER_TSUBO})
            END,
            age_years = CASE
                WHEN period_year IS NULL OR building_year IS NULL THEN NULL
                ELSE period_year - building_year
            END
        """
    )
    connection.commit()


def insert_import_run(
    connection: sqlite3.Connection,
    *,
    route_name: str,
    station_name: str,
    season_from_code: int,
    season_to_code: int,
    zip_path: Path | None,
    csv_path: Path,
    source_encoding: str,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO import_runs (
            route_name,
            station_name,
            season_from_code,
            season_to_code,
            zip_path,
            csv_path,
            source_encoding
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            route_name,
            station_name,
            season_from_code,
            season_to_code,
            str(zip_path) if zip_path else None,
            str(csv_path),
            source_encoding,
        ),
    )
    connection.commit()
    return int(cursor.lastrowid)


def insert_transactions(
    connection: sqlite3.Connection,
    *,
    import_run_id: int,
    route_name: str,
    station_name: str,
    rows: list[dict[str, str]],
) -> int:
    inserted_row_count = 0
    for index, row in enumerate(rows, start=1):
        period_year, period_quarter, period_code = parse_period(row.get("取引時期", ""))
        walk_minutes = parse_walk_minutes(row.get("最寄駅：距離（分）", ""))
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO transactions (
                import_run_id,
                row_hash,
                source_row_number,
                property_type,
                price_category,
                municipality_code,
                prefecture,
                municipality,
                district_name,
                nearest_station_name,
                walk_minutes,
                trade_price,
                floor_plan,
                area_sqm,
                building_year,
                structure,
                usage,
                future_use,
                city_planning,
                coverage_ratio,
                floor_area_ratio,
                period_year,
                period_quarter,
                period_code,
                renovation,
                remarks,
                property_type_raw,
                price_category_raw,
                building_year_raw,
                period_raw,
                walk_minutes_raw,
                trade_price_raw,
                area_sqm_raw,
                coverage_ratio_raw,
                floor_area_ratio_raw
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                import_run_id,
                row_hash_for(row, route_name=route_name, station_name=station_name),
                index,
                row.get("種類", ""),
                row.get("価格情報区分", ""),
                row.get("市区町村コード", ""),
                row.get("都道府県名", ""),
                row.get("市区町村名", ""),
                row.get("地区名", ""),
                row.get("最寄駅：名称", ""),
                walk_minutes,
                normalize_int(row.get("取引価格（総額）", "")),
                row.get("間取り", ""),
                normalize_float(row.get("面積（㎡）", "")),
                normalize_int(row.get("建築年", "")),
                row.get("建物の構造", ""),
                row.get("用途", ""),
                row.get("今後の利用目的", ""),
                row.get("都市計画", ""),
                normalize_float(row.get("建ぺい率（％）", "")),
                normalize_float(row.get("容積率（％）", "")),
                period_year,
                period_quarter,
                period_code,
                row.get("改装", ""),
                row.get("取引の事情等", ""),
                row.get("種類", ""),
                row.get("価格情報区分", ""),
                row.get("建築年", ""),
                row.get("取引時期", ""),
                row.get("最寄駅：距離（分）", ""),
                row.get("取引価格（総額）", ""),
                row.get("面積（㎡）", ""),
                row.get("建ぺい率（％）", ""),
                row.get("容積率（％）", ""),
            ),
        )
        if cursor.rowcount > 0:
            inserted_row_count += 1

    connection.commit()
    return inserted_row_count


def update_import_run_counts(
    connection: sqlite3.Connection,
    *,
    import_run_id: int,
    imported_row_count: int,
    inserted_row_count: int,
) -> None:
    connection.execute(
        """
        UPDATE import_runs
        SET imported_row_count = ?, inserted_row_count = ?
        WHERE id = ?
        """,
        (imported_row_count, inserted_row_count, import_run_id),
    )
    connection.commit()


def read_csv_rows(csv_path: Path) -> tuple[list[dict[str, str]], str]:
    csv_text, source_encoding = decode_csv(csv_path)
    reader = csv.DictReader(csv_text.splitlines())
    rows = [dict(row) for row in reader]
    return rows, source_encoding


def import_csv_to_sqlite(
    *,
    db_path: Path,
    csv_path: Path,
    route_name: str,
    station_name: str,
    season_from: str,
    season_to: str,
    zip_path: Path | None = None,
) -> tuple[int, int, str]:
    rows, source_encoding = read_csv_rows(csv_path)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    try:
        ensure_schema(connection)
        import_run_id = insert_import_run(
            connection,
            route_name=route_name,
            station_name=station_name,
            season_from_code=season_to_code(season_from),
            season_to_code=season_to_code(season_to),
            zip_path=zip_path,
            csv_path=csv_path,
            source_encoding=source_encoding,
        )
        inserted_row_count = insert_transactions(
            connection,
            import_run_id=import_run_id,
            route_name=route_name,
            station_name=station_name,
            rows=rows,
        )
        update_import_run_counts(
            connection,
            import_run_id=import_run_id,
            imported_row_count=len(rows),
            inserted_row_count=inserted_row_count,
        )
        backfill_derived_columns(connection)
    finally:
        connection.close()

    return len(rows), inserted_row_count, source_encoding


def main() -> None:
    args = parse_args()
    imported_row_count, inserted_row_count, source_encoding = import_csv_to_sqlite(
        db_path=args.db_path,
        csv_path=args.csv_path,
        route_name=args.route_name,
        station_name=args.station_name,
        season_from=args.season_from,
        season_to=args.season_to,
        zip_path=args.zip_path,
    )

    print(f"DB: {args.db_path}")
    print(f"CSV: {args.csv_path}")
    print(f"文字コード: {source_encoding}")
    print(f"取込行数: {imported_row_count}")
    print(f"新規挿入行数: {inserted_row_count}")


if __name__ == "__main__":
    main()
