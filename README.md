# 不動産情報ライブラリ Web UI 収集 / ビューア

このリポジトリは、不動産情報ライブラリの **Web UI から一覧データをダウンロードし、ローカル SQLite に蓄積する** ための作業用プロジェクトです。

現在は **公開 API は使わず**、次の流れを中心にしています。

1. Playwright で Web UI から zip / CSV を取得
2. 展開した CSV を UTF-8 に変換
3. SQLite に取り込み
4. FastAPI / Next.js でローカル閲覧

## ディレクトリ構成

```text
data/
  reinfolib.sqlite              # ローカル SQLite

scripts/
  download_reinfolib_webui.py   # Web UI ダウンロード専用
  sync_reinfolib_webui.py       # Web UI 取得 + SQLite 取り込み
  import_reinfolib_to_sqlite.py # CSV -> SQLite 取り込み
  import_apartment_master.py    # 物件名マスタ取り込み

backend/
  app/main.py                   # FastAPI バックエンド

frontend/
  app/...                       # Next.js フロントエンド
```

## セットアップ

```bash
uv add playwright
uv run playwright install chromium
```

## Web UI からダウンロード

`scripts/download_reinfolib_webui.py` は不動産情報ライブラリの検索画面を操作して、一覧データを **指定した出力先へダウンロード** します。

実行例:

```bash
uv run python scripts/download_reinfolib_webui.py \
  --route-name "ＪＲ常磐線各駅停車" \
  --station-name 亀有 \
  --season-from "2025年第1四半期" \
  --season-to "2025年第3四半期" \
  --output-dir /tmp/reinfolib-export \
  --extract \
  --headless
```

複数駅をまとめて処理する例:

```bash
uv run python scripts/download_reinfolib_webui.py \
  --target "ＪＲ常磐線各駅停車|綾瀬" \
  --target "ＪＲ常磐線各駅停車|亀有" \
  --target "ＪＲ常磐線各駅停車|金町" \
  --target "ＪＲ常磐線各駅停車|北千住" \
  --target "東京メトロ千代田線|北綾瀬" \
  --season-from "2021年第1四半期" \
  --season-to "2025年第3四半期" \
  --output-dir /tmp/reinfolib-export \
  --headless
```

ポイント:

- `--output-dir` に zip / CSV を保存
- `--extract` を付けるとその場で展開
- 展開した CSV は `cp932` から `UTF-8 with BOM` に変換
- `--target "路線名|駅名"` を複数回指定するとバッチ実行できる

## Web UI から取得してそのまま SQLite へ取り込み

`scripts/sync_reinfolib_webui.py` は **取得 + 一時展開 + 文字コード変換 + SQLite 取り込み** をまとめて実行します。

```bash
uv run python scripts/sync_reinfolib_webui.py \
  --target "ＪＲ常磐線各駅停車|綾瀬" \
  --target "ＪＲ常磐線各駅停車|亀有" \
  --target "ＪＲ常磐線各駅停車|金町" \
  --target "ＪＲ常磐線各駅停車|北千住" \
  --target "東京メトロ千代田線|北綾瀬" \
  --season-from "2021年第1四半期" \
  --season-to "2025年第3四半期" \
  --db-path data/reinfolib.sqlite \
  --headless
```

ポイント:

- 一時ファイルはテンポラリディレクトリで処理し、終了時に削除
- 通常の更新作業はこちらを使う想定

## SQLite へ取り込み

`scripts/import_reinfolib_to_sqlite.py` は、取得済み CSV を `data/reinfolib.sqlite` に取り込みます。

作成されるテーブル:

- `import_runs`
- `transactions`

通常は `scripts/sync_reinfolib_webui.py` から呼ばれる想定です。`import_reinfolib_to_sqlite.py` は既存 CSV を個別に取り込みたいときに使います。

正規化方針:

- `建築年`: `2001年` → `building_year=2001`
- `取引時期`: `period_year`, `period_quarter`, `period_code` に分解
- `最寄駅：距離（分）`, `取引価格（総額）`, `面積（㎡）` などは数値列へ変換
- `最寄駅：距離（分）` が `30分～60分` のような範囲表記なら `walk_minutes` は `NULL` にする
- 元の文字列は `*_raw` 列にも保持

## 注意

- Web UI の DOM 構造が変わると、Playwright スクリプトは調整が必要です。
- SQLite はローカル蓄積用途なので `data/*.sqlite` は Git 管理外です。

## Web アプリ

バックエンドは FastAPI、フロントエンドは Next.js です。  
最小仕様として、一覧表示・フィルター・**列ヘッダクリックでの並び替え**・ページングを実装しています。物件名候補は部分一致で絞り込みできます。

### まとめて起動

```bash
uv run python scripts/run_web_app.py
```

これで FastAPI と Next.js を同時に起動できます。`frontend/.env.local` が無ければ `.env.local.example` から自動作成します。終了は `Ctrl+C` です。

ポート競合を避けたいときや、ビルド済みフロントエンドを起動したいときは次のように指定できます。

```bash
uv run python scripts/run_web_app.py --backend-port 8001 --frontend-port 3001 --frontend-mode start
```

### バックエンド起動

```bash
uv run uvicorn backend.app.main:app --reload
```

### フロントエンド起動

```bash
cd frontend
cp .env.local.example .env.local
npm run dev
```

ブラウザで `http://localhost:3000` を開くと、`data/reinfolib.sqlite` の取引データを閲覧できます。

表示上の派生値:

- 価格は `万円` 表示
- 坪数は `1坪 = 3.3025㎡` で算出
- 坪単価は `万円/坪` 表示
- 築年数は `取引時期の年 - 建築年` で算出

### 物件名マスタの取込と突合

`data/apartment_master.csv` を DB に取り込み、取引データと事前突合します。

```bash
uv run python scripts/import_apartment_master.py
```

突合条件:

- `住所` = `市区町村 + 地区名`
- `建築年` 一致
- `駅徒歩` と `walk_minutes` の差が `±2分`

1件の取引に対して複数の物件名がヒットする場合があるため、Web アプリでは複数の物件名候補を表示します。

### API

- `GET /health`
- `GET /api/filter-options`
- `GET /api/transactions`

`/api/transactions` は次のクエリを受け付けます。

- `page`, `page_size`
- `station`
- `period_from`, `period_to`
- `price_min`, `price_max`
- `area_min`, `area_max`
- `walk_max`
- `sort_by`, `sort_order`
