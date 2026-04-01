from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
from pathlib import Path

from import_reinfolib_to_sqlite import DEFAULT_DB_PATH, ensure_schema


DEFAULT_CSV_PATH = Path("data/apartment_master.csv")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "物件名マスタ CSV を SQLite に取り込み、"
            "取引データとの突合テーブルを全洗い替えで再生成します。"
        )
    )
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--csv-path", type=Path, default=DEFAULT_CSV_PATH)
    return parser.parse_args()


def decode_csv(csv_path: Path) -> str:
    raw = csv_path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp932"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"未対応の文字コードです: {csv_path}")


def parse_building_year(value: str) -> int | None:
    normalized = value.strip()
    if not normalized:
        return None
    return int(normalized[:4])


def row_hash_for(row: dict[str, str]) -> str:
    return hashlib.sha256(
        json.dumps(row, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def import_apartment_master(connection: sqlite3.Connection, rows: list[dict[str, str]]) -> int:
    connection.execute("DELETE FROM transaction_apartment_matches")
    connection.execute("DELETE FROM apartment_master")

    inserted_row_count = 0
    for index, row in enumerate(rows, start=1):
        connection.execute(
            """
            INSERT INTO apartment_master (
                apartment_name,
                address,
                nearest_station_name,
                walk_minutes,
                built_date,
                building_year,
                source_row_number,
                row_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row.get("物件名", "").strip(),
                row.get("住所", "").strip(),
                row.get("最寄駅", "").strip(),
                int(row["駅徒歩"]) if row.get("駅徒歩", "").strip() else None,
                row.get("築年月", "").strip(),
                parse_building_year(row.get("築年月", "")),
                index,
                row_hash_for(row),
            ),
        )
        inserted_row_count += 1

    connection.commit()
    return inserted_row_count


def rebuild_matches(connection: sqlite3.Connection) -> int:
    cursor = connection.execute(
        """
        INSERT INTO transaction_apartment_matches (
            transaction_id,
            apartment_master_id,
            walk_diff
        )
        SELECT
            t.id,
            am.id,
            ABS(t.walk_minutes - am.walk_minutes)
        FROM transactions AS t
        JOIN apartment_master AS am
          ON am.address = t.municipality || t.district_name
         AND am.building_year = t.building_year
         AND t.walk_minutes IS NOT NULL
         AND am.walk_minutes IS NOT NULL
         AND ABS(t.walk_minutes - am.walk_minutes) <= 2
        """
    )
    connection.commit()
    return int(cursor.rowcount)


def main() -> None:
    args = parse_args()
    csv_text = decode_csv(args.csv_path)
    reader = csv.DictReader(csv_text.splitlines())
    rows = [dict(row) for row in reader]

    connection = sqlite3.connect(args.db_path)
    try:
        ensure_schema(connection)
        apartment_count = import_apartment_master(connection, rows)
        match_count = rebuild_matches(connection)
    finally:
        connection.close()

    print(f"DB: {args.db_path}")
    print(f"CSV: {args.csv_path}")
    print(f"物件マスタ取込件数: {apartment_count}")
    print(f"突合件数: {match_count}")


if __name__ == "__main__":
    main()
