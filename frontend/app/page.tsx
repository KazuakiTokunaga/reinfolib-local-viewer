"use client";

import { useEffect, useMemo, useState } from "react";

type FilterOptions = {
  stations: string[];
  periodMin: number | null;
  periodMax: number | null;
  periodMinLabel: string | null;
  periodMaxLabel: string | null;
};

type Transaction = {
  id: number;
  station: string | null;
  periodCode: number | null;
  periodLabel: string | null;
  tradePrice: number | null;
  areaSqm: number | null;
  areaTsubo: number | null;
  pricePerTsubo: number | null;
  walkMinutes: number | null;
  buildingYear: number | null;
  ageYears: number | null;
  floorPlan: string | null;
  municipality: string | null;
  districtName: string | null;
  apartmentNames: string[];
};

type TransactionResponse = {
  items: Transaction[];
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
};

type SortField =
  | "period_code"
  | "address"
  | "nearest_station_name"
  | "trade_price"
  | "area_sqm"
  | "area_tsubo"
  | "price_per_tsubo"
  | "walk_minutes"
  | "building_year"
  | "age_years"
  | "floor_plan"
  | "municipality"
  | "district_name";

type SortOrder = "asc" | "desc";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

const initialResponse: TransactionResponse = {
  items: [],
  page: 1,
  pageSize: 50,
  total: 0,
  totalPages: 0,
};

function formatNumber(value: number | null): string {
  if (value === null) {
    return "-";
  }
  return new Intl.NumberFormat("ja-JP").format(value);
}

function formatDecimal(value: number | null, digits = 1): string {
  if (value === null) {
    return "-";
  }
  return new Intl.NumberFormat("ja-JP", {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits,
  }).format(value);
}

function formatDecimalFixed(value: number | null, digits: number): string {
  if (value === null) {
    return "-";
  }
  return new Intl.NumberFormat("ja-JP", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

function formatManYenFromYen(value: number | null, digits = 0): string {
  if (value === null) {
    return "-";
  }
  return `${formatDecimal(value / 10000, digits)}万円`;
}

function parseSortField(value: string): SortField {
  const candidates: SortField[] = [
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
  ];
  return candidates.includes(value as SortField)
    ? (value as SortField)
    : "period_code";
}

function defaultSortOrder(field: SortField): SortOrder {
  if (
    field === "nearest_station_name" ||
    field === "address" ||
    field === "floor_plan" ||
    field === "municipality" ||
    field === "district_name"
  ) {
    return "asc";
  }
  return "desc";
}

export default function HomePage() {
  const [filterOptions, setFilterOptions] = useState<FilterOptions>({
    stations: [],
    periodMin: null,
    periodMax: null,
    periodMinLabel: null,
    periodMaxLabel: null,
  });
  const [station, setStation] = useState("");
  const [apartmentName, setApartmentName] = useState("");
  const [periodFrom, setPeriodFrom] = useState("");
  const [periodTo, setPeriodTo] = useState("");
  const [priceMin, setPriceMin] = useState("");
  const [priceMax, setPriceMax] = useState("");
  const [areaMin, setAreaMin] = useState("");
  const [areaMax, setAreaMax] = useState("");
  const [ageMin, setAgeMin] = useState("");
  const [ageMax, setAgeMax] = useState("");
  const [walkMax, setWalkMax] = useState("");
  const [sortBy, setSortBy] = useState<SortField>("period_code");
  const [sortOrder, setSortOrder] = useState<SortOrder>("desc");
  const [pageSize, setPageSize] = useState("50");
  const [page, setPage] = useState(1);
  const [response, setResponse] = useState<TransactionResponse>(initialResponse);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadFilterOptions() {
      const filterResponse = await fetch(`${API_BASE_URL}/api/filter-options`);
      if (!filterResponse.ok) {
        throw new Error("フィルター情報の取得に失敗しました。");
      }
      const data = (await filterResponse.json()) as FilterOptions;
      setFilterOptions(data);
      if (data.periodMin !== null) {
        setPeriodFrom(String(data.periodMin));
      }
      if (data.periodMax !== null) {
        setPeriodTo(String(data.periodMax));
      }
    }

    loadFilterOptions().catch((loadError: unknown) => {
      setError(
        loadError instanceof Error
          ? loadError.message
          : "フィルター情報の取得に失敗しました。"
      );
      setIsLoading(false);
    });
  }, []);

  const queryString = useMemo(() => {
    const params = new URLSearchParams({
      page: String(page),
      page_size: pageSize,
      sort_by: sortBy,
      sort_order: sortOrder,
    });
    if (station) params.set("station", station);
    if (apartmentName.trim()) params.set("apartment_name", apartmentName.trim());
    if (periodFrom) params.set("period_from", periodFrom);
    if (periodTo) params.set("period_to", periodTo);
    if (priceMin) {
      params.set("price_min", String(Math.round(Number(priceMin) * 10000)));
    }
    if (priceMax) {
      params.set("price_max", String(Math.round(Number(priceMax) * 10000)));
    }
    if (areaMin) params.set("area_min", areaMin);
    if (areaMax) params.set("area_max", areaMax);
    if (ageMin) params.set("age_min", ageMin);
    if (ageMax) params.set("age_max", ageMax);
    if (walkMax) params.set("walk_max", walkMax);
    return params.toString();
  }, [
    apartmentName,
    ageMax,
    ageMin,
    areaMax,
    areaMin,
    page,
    pageSize,
    periodFrom,
    periodTo,
    priceMax,
    priceMin,
    sortBy,
    sortOrder,
    station,
    walkMax,
  ]);

  useEffect(() => {
    async function loadTransactions() {
      setIsLoading(true);
      setError(null);
      const transactionsResponse = await fetch(
        `${API_BASE_URL}/api/transactions?${queryString}`
      );
      if (!transactionsResponse.ok) {
        throw new Error("取引データの取得に失敗しました。");
      }
      const data = (await transactionsResponse.json()) as TransactionResponse;
      setResponse(data);
      setIsLoading(false);
    }

    loadTransactions().catch((loadError: unknown) => {
      setError(
        loadError instanceof Error
          ? loadError.message
          : "取引データの取得に失敗しました。"
      );
      setIsLoading(false);
    });
  }, [queryString]);

  function resetFilters() {
    setStation("");
    setApartmentName("");
    setPeriodFrom(filterOptions.periodMin ? String(filterOptions.periodMin) : "");
    setPeriodTo(filterOptions.periodMax ? String(filterOptions.periodMax) : "");
    setPriceMin("");
    setPriceMax("");
    setAreaMin("");
    setAreaMax("");
    setAgeMin("");
    setAgeMax("");
    setWalkMax("");
    setSortBy("period_code");
    setSortOrder("desc");
    setPageSize("50");
    setPage(1);
  }

  function onFilterChange<T>(setter: (value: T) => void, value: T) {
    setter(value);
    setPage(1);
  }

  function toggleSort(field: SortField) {
    setPage(1);
    if (sortBy === field) {
      setSortOrder((current) => (current === "desc" ? "asc" : "desc"));
      return;
    }
    setSortBy(field);
    setSortOrder(defaultSortOrder(field));
  }

  function sortIndicator(field: SortField): string {
    if (sortBy !== field) {
      return "↕";
    }
    return sortOrder === "desc" ? "↓" : "↑";
  }

  return (
    <main className="page">
      <section className="header">
        <div>
          <h1>不動産取引ビューア</h1>
          <p>
            SQLite の取引データを一覧表示し、駅名・物件名候補・時期・価格・面積・築年数・徒歩分で
            絞り込みできます。列ヘッダをクリックすると並び替えできます。
          </p>
        </div>
        <div className="summary">
          <span>総件数: {formatNumber(response.total)}</span>
          <span>
            対象期間: {filterOptions.periodMinLabel ?? "-"} 〜{" "}
            {filterOptions.periodMaxLabel ?? "-"}
          </span>
        </div>
      </section>

      <section className="filters">
        <label>
          駅名
          <select
            value={station}
            onChange={(event) => onFilterChange(setStation, event.target.value)}
          >
            <option value="">すべて</option>
            {filterOptions.stations.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>

        <label>
          物件名候補
          <input
            value={apartmentName}
            onChange={(event) =>
              onFilterChange(setApartmentName, event.target.value)
            }
            placeholder="ライオンズ"
          />
        </label>

        <label>
          取引時期From
          <input
            value={periodFrom}
            onChange={(event) => onFilterChange(setPeriodFrom, event.target.value)}
            placeholder="20211"
          />
        </label>

        <label>
          取引時期To
          <input
            value={periodTo}
            onChange={(event) => onFilterChange(setPeriodTo, event.target.value)}
            placeholder="20253"
          />
        </label>

        <label>
          価格下限(万円)
          <input
            value={priceMin}
            onChange={(event) => onFilterChange(setPriceMin, event.target.value)}
            placeholder="3000"
          />
        </label>

        <label>
          価格上限(万円)
          <input
            value={priceMax}
            onChange={(event) => onFilterChange(setPriceMax, event.target.value)}
            placeholder="8000"
          />
        </label>

        <label>
          面積下限
          <input
            value={areaMin}
            onChange={(event) => onFilterChange(setAreaMin, event.target.value)}
            placeholder="50"
          />
        </label>

        <label>
          面積上限
          <input
            value={areaMax}
            onChange={(event) => onFilterChange(setAreaMax, event.target.value)}
            placeholder="80"
          />
        </label>

        <label>
          築年数下限
          <input
            value={ageMin}
            onChange={(event) => onFilterChange(setAgeMin, event.target.value)}
            placeholder="5"
          />
        </label>

        <label>
          築年数上限
          <input
            value={ageMax}
            onChange={(event) => onFilterChange(setAgeMax, event.target.value)}
            placeholder="20"
          />
        </label>

        <label>
          徒歩上限
          <input
            value={walkMax}
            onChange={(event) => onFilterChange(setWalkMax, event.target.value)}
            placeholder="10"
          />
        </label>

        <label>
          1ページ件数
          <select
            value={pageSize}
            onChange={(event) => onFilterChange(setPageSize, event.target.value)}
          >
            <option value="25">25</option>
            <option value="50">50</option>
            <option value="100">100</option>
          </select>
        </label>

        <button type="button" onClick={resetFilters}>
          条件をリセット
        </button>
      </section>

      {error ? <p className="error">{error}</p> : null}

      <section className="tableCard">
        <div className="tableMeta">
          <span>
            {response.page} / {Math.max(response.totalPages, 1)} ページ
          </span>
          <span>{isLoading ? "読み込み中..." : `${formatNumber(response.total)} 件`}</span>
        </div>
        <div className="tableWrapper">
          <table>
            <thead>
              <tr>
                <th>
                  <button
                    type="button"
                    className="sortButton"
                    onClick={() => toggleSort("period_code")}
                  >
                    取引時期 <span>{sortIndicator("period_code")}</span>
                  </button>
                </th>
                <th>
                  <button
                    type="button"
                    className="sortButton"
                    onClick={() => toggleSort("nearest_station_name")}
                  >
                    駅名 <span>{sortIndicator("nearest_station_name")}</span>
                  </button>
                </th>
                <th className="numericHeader">
                  <button
                    type="button"
                    className="sortButton numericSortButton"
                    onClick={() => toggleSort("walk_minutes")}
                  >
                    徒歩分 <span>{sortIndicator("walk_minutes")}</span>
                  </button>
                </th>
                <th className="numericHeader">
                  <button
                    type="button"
                    className="sortButton numericSortButton"
                    onClick={() => toggleSort("trade_price")}
                  >
                    価格(万円) <span>{sortIndicator("trade_price")}</span>
                  </button>
                </th>
                <th className="numericHeader">
                  <button
                    type="button"
                    className="sortButton numericSortButton"
                    onClick={() => toggleSort("area_sqm")}
                  >
                    面積(㎡) <span>{sortIndicator("area_sqm")}</span>
                  </button>
                </th>
                <th className="numericHeader">
                  <button
                    type="button"
                    className="sortButton numericSortButton"
                    onClick={() => toggleSort("area_tsubo")}
                  >
                    坪数 <span>{sortIndicator("area_tsubo")}</span>
                  </button>
                </th>
                <th className="numericHeader">
                  <button
                    type="button"
                    className="sortButton numericSortButton"
                    onClick={() => toggleSort("price_per_tsubo")}
                  >
                    坪単価 <span>{sortIndicator("price_per_tsubo")}</span>
                  </button>
                </th>
                <th>
                  <button
                    type="button"
                    className="sortButton"
                    onClick={() => toggleSort("floor_plan")}
                  >
                    間取り <span>{sortIndicator("floor_plan")}</span>
                  </button>
                </th>
                <th className="numericHeader">
                  <button
                    type="button"
                    className="sortButton numericSortButton"
                    onClick={() => toggleSort("building_year")}
                  >
                    建築年 <span>{sortIndicator("building_year")}</span>
                  </button>
                </th>
                <th className="numericHeader">
                  <button
                    type="button"
                    className="sortButton numericSortButton"
                    onClick={() => toggleSort("age_years")}
                  >
                    築年数 <span>{sortIndicator("age_years")}</span>
                  </button>
                </th>
                <th>
                  <button
                    type="button"
                    className="sortButton"
                    onClick={() => toggleSort("address")}
                  >
                    住所 <span>{sortIndicator("address")}</span>
                  </button>
                </th>
                <th>物件名候補</th>
              </tr>
            </thead>
            <tbody>
              {response.items.map((item) => (
                <tr key={item.id}>
                  <td>{item.periodLabel ?? "-"}</td>
                  <td>{item.station ?? "-"}</td>
                  <td className="numericCell">
                    {item.walkMinutes === null ? "不明" : `${item.walkMinutes}分`}
                  </td>
                  <td className="numericCell">{formatManYenFromYen(item.tradePrice)}</td>
                  <td className="numericCell">
                    {item.areaSqm === null ? "-" : formatDecimal(item.areaSqm, 1)}
                  </td>
                  <td className="numericCell">
                    {formatDecimalFixed(item.areaTsubo, 2)}
                  </td>
                  <td className="numericCell">
                    {formatManYenFromYen(item.pricePerTsubo)}
                  </td>
                  <td>{item.floorPlan ?? "-"}</td>
                  <td className="numericCell">
                    {item.buildingYear === null ? "-" : `${item.buildingYear}年`}
                  </td>
                  <td className="numericCell">
                    {item.ageYears === null ? "-" : `${item.ageYears}年`}
                  </td>
                  <td>{`${item.municipality ?? ""}${item.districtName ?? ""}` || "-"}</td>
                  <td className="apartmentCell">
                    {item.apartmentNames.length === 0 ? (
                      "-"
                    ) : (
                      <div className="nameList">
                        {item.apartmentNames.map((name) => (
                          <span key={`${item.id}-${name}`}>{name}</span>
                        ))}
                      </div>
                    )}
                  </td>
                </tr>
              ))}
              {!isLoading && response.items.length === 0 ? (
                <tr>
                  <td colSpan={12} className="empty">
                    条件に一致するデータがありません。
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
        <div className="pager">
          <button
            type="button"
            onClick={() => setPage((current) => Math.max(current - 1, 1))}
            disabled={page <= 1 || isLoading}
          >
            前へ
          </button>
          <span>
            {response.page} / {Math.max(response.totalPages, 1)}
          </span>
          <button
            type="button"
            onClick={() =>
              setPage((current) =>
                Math.min(current + 1, Math.max(response.totalPages, 1))
              )
            }
            disabled={page >= response.totalPages || isLoading}
          >
            次へ
          </button>
        </div>
      </section>
    </main>
  );
}
