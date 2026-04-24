# schoomy-schedule-magazine-pdf

スクーミーフェスタ年間スケジュール **デザイン版（縦型雑誌風）** PDF 自動生成。
横長表形式の `shiojima-test/schoomy-schedule-pdf` と並行運用する別レイアウト。

## 既存版との違い

| 観点 | シンプル版 (`schoomy-schedule-pdf`) | デザイン版（このリポ） |
| --- | --- | --- |
| レイアウト | A4横・表形式 | A4縦寄り (210×257mm)・2カラム雑誌風 |
| 生成方式 | reportlab | Playwright (Chromium) で HTML→PDF |
| フォント | Noto Sans JP 同梱 | M PLUS 2（apt `fonts-mplus`） |
| 月の見せ方 | 各行1イベント | 月ヘッダーで束ねたカード群 |

## データソース

- 公開 CSV: <https://docs.google.com/spreadsheets/d/e/2PACX-1vRooWpJWGHr60e039XzbxEbeZ7p6zEL-wuP-xrq4jv1TnZXHSOWjtT8FvScuKsQn05aZx8PfIW14d83/pub?output=csv>
- 出力 Drive フォルダ: <https://drive.google.com/drive/folders/12caVEED6ZAF_g30o3ZWmI67GA3g9aFvz>
- 固定 PDF 直URL (SWELL用): `https://drive.google.com/uc?export=download&id=1c5muRsTSuCQjKRYl9zTXI15CV7AY6ite`

## ローカル実行

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python src/generate_pdf.py --version 1 --update-date 2026-04-24 --output test.pdf
open test.pdf
```

Mac で M PLUS 2 を使うには `~/Library/Fonts/MPLUS2-VariableFont_wght.ttf` を配置（Google Fonts から）。
無くても Hiragino Kaku Gothic ProN にフォールバック。

Drive アップロードを試す場合:

```bash
export GOOGLE_SERVICE_ACCOUNT_JSON="$(cat service-account-key.json)"
.venv/bin/python upload_to_drive.py test.pdf
```

## データフロー

```
スプレッドシート (CSV)
  → GAS「📄 PDF操作 > ① PDFを生成・更新（両方）」
  → GitHub repository_dispatch (シンプル版 + デザイン版を並行起動)
  → GitHub Actions: Python (Playwright) で PDF 生成
  → Google Drive にアップロード（固定ファイルIDで上書き）
  → SWELL のダウンロードボタンから取得
```

## GAS（スプレッドシート側ボタン）

`gas_trigger.gs` を **既存の GAS と置き換えて** 貼り付けます（シンプル版・デザイン版を統合制御するため）。
詳細は `gas_trigger.gs` の冒頭コメント参照。

メニュー構成:
- 📄 PDF操作
  - ① PDFを生成・更新（両方）   ← 1クリックで両リポジトリの Actions を起動
  - ② シンプル版ダウンロードURLを表示
  - ③ デザイン版ダウンロードURLを表示
  - ④ Driveフォルダを開く

## SWELL ダウンロードボタン

```
シンプル版: https://drive.google.com/uc?export=download&id=11MbcUecXNnd1bCroHQr5s117FpouooRj
デザイン版: https://drive.google.com/uc?export=download&id=1c5muRsTSuCQjKRYl9zTXI15CV7AY6ite
```

どちらも固定 URL（PDF 内容が更新されてもリンクは変わらない）。

## トラブルシューティング

- **`Service Accounts do not have storage quota` (403)**: 同名ファイルが Drive に存在しないとき発生。誰かが手動でプレースホルダ（同名）を置けば、以降は SA が `update()` で上書きできる。
- **GitHub Push Protection で OAuth Token がブロック**: `gas_trigger.gs` の `GITHUB_TOKEN` は `PASTE_YOUR_GITHUB_TOKEN_HERE` プレースホルダのままコミットし、貼り付け時に差し替える。
- **PDF が 1ページに収まらない**: 本テンプレでは外周マージンを最小限に圧縮済み。CSV 行数が増えると改ページが起きる可能性あり。`src/generate_pdf.py` の `estimate_block_mm` と `template.html` の row 高さを調整。
