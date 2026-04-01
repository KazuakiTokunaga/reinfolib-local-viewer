from __future__ import annotations

import argparse
import zipfile
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import Download, Locator, Page, sync_playwright


REAL_ESTATE_PRICES_URL = "https://www.reinfolib.mlit.go.jp/realEstatePrices/"
DEFAULT_ROUTE_NAME = "ＪＲ常磐線各駅停車"
DEFAULT_STATION_NAME = "亀有"
DEFAULT_SEASON_FROM = "2025年第1四半期"
DEFAULT_SEASON_TO = "2025年第3四半期"
DEFAULT_PROPERTY_TYPE = "中古マンション等"


@dataclass(frozen=True)
class SearchRequest:
    route_name: str
    station_name: str
    season_from: str
    season_to: str
    property_type: str


@dataclass(frozen=True)
class DownloadResult:
    request: SearchRequest
    result_count: str
    zip_path: Path
    extract_dir: Path | None
    converted_files: list[Path]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "不動産情報ライブラリの Web UI を Playwright で操作し、"
            "駅徒歩を含む一覧データをダウンロードします。"
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
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="zip / CSV を保存する出力先ディレクトリ。",
    )
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--slow-mo", type=int, default=0, help="ブラウザ操作の待機ミリ秒")
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=30_000,
        help="各 Playwright 操作で使うタイムアウト（ミリ秒）",
    )
    parser.add_argument(
        "--extract",
        action="store_true",
        help="ダウンロードした zip を展開します。",
    )
    return parser.parse_args()


def parse_target(target: str) -> tuple[str, str]:
    route_name, separator, station_name = target.partition("|")
    if separator == "" or not route_name.strip() or not station_name.strip():
        raise RuntimeError(
            f"target の形式が不正です: {target}。'路線名|駅名' で指定してください。"
        )
    return route_name.strip(), station_name.strip()


def build_requests(
    *,
    route_name: str,
    station_name: str,
    season_from: str,
    season_to: str,
    property_type: str,
    targets: list[str],
) -> list[SearchRequest]:
    if targets:
        return [
            SearchRequest(
                route_name=target_route_name,
                station_name=target_station_name,
                season_from=season_from,
                season_to=season_to,
                property_type=property_type,
            )
            for target_route_name, target_station_name in (
                parse_target(target) for target in targets
            )
        ]

    return [
        SearchRequest(
            route_name=route_name,
            station_name=station_name,
            season_from=season_from,
            season_to=season_to,
            property_type=property_type,
        )
    ]


def first_visible(locator: Locator) -> Locator:
    for index in range(locator.count()):
        item = locator.nth(index)
        if item.is_visible():
            return item
    raise RuntimeError("表示中の要素が見つかりませんでした。")


def configure_search_conditions(
    page: Page, request: SearchRequest, *, timeout_ms: int
) -> None:
    page.locator("#rdoStation").check(timeout=timeout_ms)
    page.locator("#chkTransactionPrice").uncheck(timeout=timeout_ms)
    page.locator("#chkClosedPrice").check(timeout=timeout_ms)
    page.locator("#cmbKind").select_option(label=request.property_type, timeout=timeout_ms)
    page.locator("#cmbSeasonFrom").select_option(label=request.season_from, timeout=timeout_ms)
    page.locator("#cmbSeasonTo").select_option(label=request.season_to, timeout=timeout_ms)
    page.locator("#cmbRoutes").select_option(label=request.route_name, timeout=timeout_ms)
    page.wait_for_timeout(1500)
    page.locator("#cmbStations").select_option(label=request.station_name, timeout=timeout_ms)
    page.wait_for_timeout(3000)


def current_result_count(page: Page) -> str:
    body_text = page.locator("body").inner_text()
    marker = "現在の条件での検索結果："
    if marker not in body_text:
        return "不明"
    return body_text.split(marker, 1)[1].split("件", 1)[0]


def save_download(
    download: Download,
    *,
    output_dir: Path,
    request: SearchRequest,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_name = "_".join(
        [
            request.route_name.replace("/", "_"),
            request.station_name.replace("/", "_"),
            request.season_from.replace("/", "_"),
            request.season_to.replace("/", "_"),
        ]
    )
    output_path = output_dir / f"reinfolib_webui_{safe_name}.zip"
    download.save_as(str(output_path))
    return output_path


def extract_zip(zip_path: Path) -> Path:
    extract_dir = zip_path.with_suffix("")
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zip_file:
        zip_file.extractall(extract_dir)
    return extract_dir


def convert_csv_encoding_in_place(csv_path: Path) -> None:
    text = csv_path.read_text(encoding="cp932")
    csv_path.write_text(text, encoding="utf-8-sig", newline="")


def convert_extracted_csv_files(extract_dir: Path) -> list[Path]:
    converted_files: list[Path] = []
    for csv_path in sorted(extract_dir.glob("*.csv")):
        convert_csv_encoding_in_place(csv_path)
        converted_files.append(csv_path)
    return converted_files


def download_one(
    page: Page,
    *,
    request: SearchRequest,
    output_dir: Path,
    extract: bool,
    timeout_ms: int,
) -> DownloadResult:
    configure_search_conditions(page, request, timeout_ms=timeout_ms)
    result_count = current_result_count(page)

    with page.expect_download(timeout=timeout_ms) as download_info:
        first_visible(page.locator("#btnDownloadList")).click(timeout=timeout_ms)

    download = download_info.value
    output_path = save_download(download, output_dir=output_dir, request=request)

    extract_dir: Path | None = None
    converted_files: list[Path] = []
    if extract:
        extract_dir = extract_zip(output_path)
        converted_files = convert_extracted_csv_files(extract_dir)

    return DownloadResult(
        request=request,
        result_count=result_count,
        zip_path=output_path,
        extract_dir=extract_dir,
        converted_files=converted_files,
    )


def run_downloads(
    *,
    requests: list[SearchRequest],
    output_dir: Path,
    headless: bool,
    slow_mo: int,
    timeout_ms: int,
    extract: bool,
) -> list[DownloadResult]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless, slow_mo=slow_mo)
        context = browser.new_context(accept_downloads=True, locale="ja-JP")
        page = context.new_page()
        page.goto(REAL_ESTATE_PRICES_URL, wait_until="domcontentloaded", timeout=timeout_ms)
        page.wait_for_load_state("networkidle", timeout=timeout_ms)
        results = [
            download_one(
                page,
                request=request,
                output_dir=output_dir,
                extract=extract,
                timeout_ms=timeout_ms,
            )
            for request in requests
        ]
        context.close()
        browser.close()
        return results


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
    results = run_downloads(
        requests=requests,
        output_dir=args.output_dir,
        headless=args.headless,
        slow_mo=args.slow_mo,
        timeout_ms=args.timeout_ms,
        extract=args.extract,
    )

    for result in results:
        print(
            "ダウンロード完了:"
            f" route={result.request.route_name}"
            f" station={result.request.station_name}"
            f" count={result.result_count}"
            f" zip={result.zip_path}"
        )
        if result.extract_dir is not None:
            print(f"展開先: {result.extract_dir}")
        for converted_file in result.converted_files:
            print(f"UTF-8変換: {converted_file}")


if __name__ == "__main__":
    main()
