from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware


DB_PATH = Path(__file__).resolve().parents[2] / "data" / "reinfolib.sqlite"
ALLOWED_SORT_FIELDS = {
    "period_code": "period_code",
    "address": "municipality || district_name",
    "nearest_station_name": "nearest_station_name",
    "floor_plan": "floor_plan",
    "trade_price": "trade_price",
    "area_sqm": "area_sqm",
    "area_tsubo": "area_tsubo",
    "price_per_tsubo": "price_per_tsubo",
    "walk_minutes": "walk_minutes",
    "building_year": "building_year",
    "age_years": "age_years",
    "municipality": "municipality",
    "district_name": "district_name",
}
SORT_ORDER_MAP = {"asc": "ASC", "desc": "DESC"}


app = FastAPI(title="Real Estate API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def format_period(period_code: int | None) -> str | None:
    if period_code is None:
        return None
    year = period_code // 10
    quarter = period_code % 10
    return f"{year}-{quarter}Q"


def to_like_pattern(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
    return f"%{escaped}%"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/filter-options")
def filter_options() -> dict[str, object]:
    connection = get_connection()
    try:
        stations = [
            row["nearest_station_name"]
            for row in connection.execute(
                """
                SELECT DISTINCT nearest_station_name
                FROM transactions
                WHERE nearest_station_name IS NOT NULL
                  AND nearest_station_name != ''
                ORDER BY nearest_station_name
                """
            )
        ]
        period_min, period_max = connection.execute(
            "SELECT MIN(period_code), MAX(period_code) FROM transactions"
        ).fetchone()
        return {
            "stations": stations,
            "periodMin": period_min,
            "periodMax": period_max,
            "periodMinLabel": format_period(period_min),
            "periodMaxLabel": format_period(period_max),
        }
    finally:
        connection.close()


@app.get("/api/transactions")
def list_transactions(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    station: str | None = Query(None),
    apartment_name: str | None = Query(None),
    period_from: int | None = Query(None),
    period_to: int | None = Query(None),
    price_min: int | None = Query(None),
    price_max: int | None = Query(None),
    area_min: float | None = Query(None),
    area_max: float | None = Query(None),
    walk_max: int | None = Query(None),
    sort_by: Literal[
        "period_code",
        "address",
        "nearest_station_name",
        "trade_price",
        "area_sqm",
        "area_tsubo",
        "price_per_tsubo",
        "walk_minutes",
        "building_year",
        "age_years",
        "floor_plan",
        "municipality",
        "district_name",
    ] = "period_code",
    sort_order: Literal["asc", "desc"] = "desc",
) -> dict[str, object]:
    where_clauses = []
    params: list[object] = []

    if station:
        where_clauses.append("nearest_station_name = ?")
        params.append(station)
    if apartment_name and apartment_name.strip():
        where_clauses.append(
            """
            EXISTS (
                SELECT 1
                FROM transaction_apartment_matches AS tam
                JOIN apartment_master AS am
                  ON am.id = tam.apartment_master_id
                WHERE tam.transaction_id = transactions.id
                  AND am.apartment_name LIKE ? ESCAPE '\\'
            )
            """
        )
        params.append(to_like_pattern(apartment_name.strip()))
    if period_from is not None:
        where_clauses.append("period_code >= ?")
        params.append(period_from)
    if period_to is not None:
        where_clauses.append("period_code <= ?")
        params.append(period_to)
    if price_min is not None:
        where_clauses.append("trade_price >= ?")
        params.append(price_min)
    if price_max is not None:
        where_clauses.append("trade_price <= ?")
        params.append(price_max)
    if area_min is not None:
        where_clauses.append("area_sqm >= ?")
        params.append(area_min)
    if area_max is not None:
        where_clauses.append("area_sqm <= ?")
        params.append(area_max)
    if walk_max is not None:
        where_clauses.append("walk_minutes IS NOT NULL AND walk_minutes <= ?")
        params.append(walk_max)

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    sort_column = ALLOWED_SORT_FIELDS[sort_by]
    sort_direction = SORT_ORDER_MAP[sort_order]
    offset = (page - 1) * page_size

    connection = get_connection()
    try:
        total = connection.execute(
            f"SELECT COUNT(*) FROM transactions {where_sql}",
            params,
        ).fetchone()[0]

        rows = connection.execute(
            f"""
            SELECT
                id,
                nearest_station_name,
                period_code,
                trade_price,
                area_sqm,
                area_tsubo,
                price_per_tsubo,
                walk_minutes,
                building_year,
                age_years,
                floor_plan,
                municipality,
                district_name
            FROM transactions
            {where_sql}
            ORDER BY
                {sort_column} IS NULL ASC,
                {sort_column} {sort_direction},
                id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        ).fetchall()

        apartment_names_by_transaction: dict[int, list[str]] = {}
        transaction_ids = [int(row["id"]) for row in rows]
        if transaction_ids:
            placeholders = ",".join("?" for _ in transaction_ids)
            match_rows = connection.execute(
                f"""
                SELECT
                    tam.transaction_id,
                    am.apartment_name
                FROM transaction_apartment_matches AS tam
                JOIN apartment_master AS am
                  ON am.id = tam.apartment_master_id
                WHERE tam.transaction_id IN ({placeholders})
                ORDER BY tam.transaction_id, tam.walk_diff, am.apartment_name
                """,
                transaction_ids,
            ).fetchall()
            for row in match_rows:
                apartment_names_by_transaction.setdefault(
                    int(row["transaction_id"]), []
                ).append(str(row["apartment_name"]))
    finally:
        connection.close()

    items = [
        {
            "id": row["id"],
            "station": row["nearest_station_name"],
            "periodCode": row["period_code"],
            "periodLabel": format_period(row["period_code"]),
            "tradePrice": row["trade_price"],
            "areaSqm": row["area_sqm"],
            "areaTsubo": row["area_tsubo"],
            "pricePerTsubo": row["price_per_tsubo"],
            "walkMinutes": row["walk_minutes"],
            "buildingYear": row["building_year"],
            "ageYears": row["age_years"],
            "floorPlan": row["floor_plan"],
            "municipality": row["municipality"],
            "districtName": row["district_name"],
            "apartmentNames": apartment_names_by_transaction.get(int(row["id"]), []),
        }
        for row in rows
    ]

    return {
        "items": items,
        "page": page,
        "pageSize": page_size,
        "total": total,
        "totalPages": (total + page_size - 1) // page_size,
    }
