from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from download_reinfolib_webui import (
    DEFAULT_PROPERTY_TYPE,
    DEFAULT_ROUTE_NAME,
    DEFAULT_SEASON_FROM,
    DEFAULT_SEASON_TO,
    DEFAULT_STATION_NAME,
    build_requests,
    run_downloads,
)
from import_reinfolib_to_sqlite import DEFAULT_DB_PATH, import_csv_to_sqlite


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "不動産情報ライブラリの Web UI から一覧データを取得し、"
            "そのまま SQLite に取り込みます。"
        )
    )
    parser.add_argument("--route-name", default=DEFAULT_ROUTE_NAME)
    parser.add_argument("--station-name", default=DEFAULT_STATION_NAME)
    parser.add_argument("--season-from", default=DEFAULT_SEASON_FROM)
    parser.add_argument("--season-to", default=DEFAULT_SEASON_TO)
    parser.add_argument("--property-type", default=DEFAULT_PROPERTY_TYPE)
    parser.add_argument(
        "--target",
        action="append",
        default=[],
        help="路線名と駅名を '路線名|駅名' 形式で指定。複数回指定できます。",
    )
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--slow-mo", type=int, default=0, help="ブラウザ操作の待機ミリ秒")
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=30_000,
        help="各 Playwright 操作で使うタイムアウト（ミリ秒）",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    requests = build_requests(
        route_name=args.route_name,
        station_name=args.station_name,
        season_from=args.season_from,
        season_to=args.season_to,
        property_type=args.property_type,
        targets=args.target,
    )

    with tempfile.TemporaryDirectory(prefix="reinfolib-webui-") as temporary_dir:
        results = run_downloads(
            requests=requests,
            output_dir=Path(temporary_dir),
            headless=args.headless,
            slow_mo=args.slow_mo,
            timeout_ms=args.timeout_ms,
            extract=True,
        )

        for result in results:
            print(
                "ダウンロード完了:"
                f" route={result.request.route_name}"
                f" station={result.request.station_name}"
                f" count={result.result_count}"
            )
            for csv_path in result.converted_files:
                imported_row_count, inserted_row_count, source_encoding = (
                    import_csv_to_sqlite(
                        db_path=args.db_path,
                        csv_path=csv_path,
                        route_name=result.request.route_name,
                        station_name=result.request.station_name,
                        season_from=result.request.season_from,
                        season_to=result.request.season_to,
                        zip_path=result.zip_path,
                    )
                )
                print(
                    "DB取込完了:"
                    f" route={result.request.route_name}"
                    f" station={result.request.station_name}"
                    f" csv={csv_path}"
                    f" encoding={source_encoding}"
                    f" imported={imported_row_count}"
                    f" inserted={inserted_row_count}"
                )


if __name__ == "__main__":
    main()
