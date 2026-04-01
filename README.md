# reinfolib-local-viewer

不動産情報ライブラリの取引データをローカルに蓄積し、SQLite + Web アプリで閲覧するためのリポジトリです。

このリポジトリでは次を行えます。

1. Playwright で不動産情報ライブラリの Web UI から取引データを取得する
2. CSV を SQLite に取り込む
3. 物件名マスタを取り込み、取引データと事前突合する
4. FastAPI + Next.js のローカル Web アプリで一覧表示する

## ディレクトリ構成

```text
data/
  reinfolib.sqlite              # ローカル SQLite
  apartment_master.csv          # 物件名マスタ

scripts/
  download_reinfolib_webui.py   # Web UI ダウンロード専用
  sync_reinfolib_webui.py       # Web UI 取得 + SQLite 取り込み
  import_reinfolib_to_sqlite.py # CSV -> SQLite 取り込み
  import_apartment_master.py    # 物件名マスタ取り込みと突合
  run_web_app.py                # FastAPI / Next.js 同時起動

backend/
  app/main.py                   # FastAPI バックエンド

frontend/
  app/...                       # Next.js フロントエンド
```

## セットアップ

```bash
uv sync
uv run playwright install chromium
```

## 1. データの準備

通常は **`sync_reinfolib_webui.py` で取引データを取得・取込し、その後 `import_apartment_master.py` で物件名マスタを取り込んで突合する** 流れです。

### 取引データを取得して SQLite に取り込む

`scripts/sync_reinfolib_webui.py` は、Web UI からの取得・一時展開・文字コード変換・SQLite 取り込みをまとめて実行します。

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

- 通常のデータ更新はこのコマンドを使います
- 一時ファイルはテンポラリディレクトリで処理し、終了時に削除します
- 同じデータを再投入しても `transactions` は重複登録されません

### 物件名マスタを取り込み、取引データと突合する

`data/apartment_master.csv` を取り込み、SQLite 内で取引データと事前突合します。

```bash
uv run python scripts/import_apartment_master.py
```

突合条件:

- `住所` = `市区町村 + 地区名`
- `建築年` 一致
- `駅徒歩` と `walk_minutes` の差が `±2分`

1件の取引に対して複数の物件名がヒットする場合があるため、Web アプリでは物件名候補を複数表示します。

### 必要に応じて使う補助コマンド

#### CSV を手元に保存したい場合

`scripts/download_reinfolib_webui.py` は、Web UI から一覧データを指定ディレクトリへ保存します。

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

- `--output-dir` に zip / CSV を保存します
- `--extract` を付けるとその場で展開します
- 展開した CSV は `cp932` から `UTF-8 with BOM` に変換します
- `--target "路線名|駅名"` を複数回指定するとバッチ実行できます

#### 既存 CSV を個別に取り込みたい場合

`scripts/import_reinfolib_to_sqlite.py` は、取得済み CSV を SQLite に取り込みます。

```bash
uv run python scripts/import_reinfolib_to_sqlite.py --help
```

このスクリプトでは、取引時期・価格・面積・徒歩分などを正規化し、派生列も更新します。

## 2. アプリケーションの起動

### まとめて起動

FastAPI と Next.js を同時に起動します。

```bash
uv run python scripts/run_web_app.py
```

起動後、ブラウザで `http://localhost:3000` を開くと `data/reinfolib.sqlite` の取引データを閲覧できます。

- `frontend/.env.local` が無ければ `.env.local.example` から自動作成します
- 終了は `Ctrl+C` です

ポートを変えたい場合や、ビルド済みフロントエンドを起動したい場合:

```bash
uv run python scripts/run_web_app.py \
  --backend-port 8001 \
  --frontend-port 3001 \
  --frontend-mode start
```

### 個別に起動

#### バックエンド

```bash
uv run uvicorn backend.app.main:app --reload
```

#### フロントエンド

```bash
cd frontend
cp .env.local.example .env.local
npm run dev
```

## Web アプリでできること

- 一覧表示
- フィルター
- 列ヘッダクリックでの並び替え
- ページング
- 物件名候補の部分一致検索

主な表示項目:

- 価格（万円）
- 面積（㎡）
- 坪数
- 坪単価
- 築年数
- 住所
- 物件名候補

派生値の扱い:

- 坪数は `1坪 = 3.3025㎡` で算出
- 坪単価は `価格 / 坪数` で算出
- 築年数は `取引時期の年 - 建築年` で算出

## API

- `GET /health`
- `GET /api/filter-options`
- `GET /api/transactions`

`/api/transactions` の主なクエリ:

- `page`, `page_size`
- `station`
- `apartment_name`
- `period_from`, `period_to`
- `price_min`, `price_max`
- `area_min`, `area_max`
- `walk_max`
- `sort_by`, `sort_order`

## 注意

- Web UI の DOM 構造が変わると、Playwright スクリプトは調整が必要です
- SQLite はローカル蓄積用途のため、`data/*.sqlite` は Git 管理外です
