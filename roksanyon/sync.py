"""ロクサンヨン公開 v1.0

Googleドライブの「ロクサンヨン公開」フォルダにあるPDFを読み、
ホームページ（WordPress）が読む掲載一覧シートを作り直す。

- ファイル名に年月（例: ロクサンヨン_2026-10.pdf / 634_2026年10月号.pdf）が無いPDFは載せない
- 同じ年月が複数あるときは、更新日時が新しいほうを載せる
- 載せるPDFには「リンクを知っている全員が閲覧可」を付ける（表紙はドライブのサムネイルで表示）
- 一覧シートは毎回まるごと書き直す（フォルダから消したPDFは一覧からも消える）
"""
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta

from google.oauth2 import service_account
from googleapiclient.discovery import build

VERSION = '1.0'
FOLDER_ID = '1acenOS-UcYfSbFqtKL_Nt8D8ymrmj6YU'   # ロクサンヨン公開
SHEET_ID = '1v5_TuOy0FcOQoDqXcYIV6YqHJTPburmvtccXyNBwsUc'  # ロクサンヨン掲載一覧（自動・さわらない）
SCOPES = ['https://www.googleapis.com/auth/drive',
          'https://www.googleapis.com/auth/spreadsheets']
HEADER = ['year', 'month', 'label', 'cover_url', 'download_url', 'size_mb', 'file_name', 'updated']
JST = timezone(timedelta(hours=9))

# 2026-10 / 2026_10 / 2026.10 / 2026年10月 / 202610
YM = re.compile(r'(20\d{2})\s*(?:[-_.年/ ]\s*)?(\d{1,2})(?!\d)')


def parse_year_month(name):
    for m in YM.finditer(name):
        y, mo = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12:
            return y, mo
    return None


def has_anyone_reader(drive, file_id):
    perms = drive.permissions().list(fileId=file_id, fields='permissions(type,role)').execute()
    return any(p['type'] == 'anyone' for p in perms.get('permissions', []))


def make_public(drive, file_id):
    if not has_anyone_reader(drive, file_id):
        drive.permissions().create(fileId=file_id, body={'type': 'anyone', 'role': 'reader'}).execute()
        print(f'  公開設定を追加: {file_id}')


def main():
    info = json.loads(os.environ['GOOGLE_SERVICE_ACCOUNT_JSON'])
    print(f'ロクサンヨン公開 v{VERSION} / 実行アカウント: {info.get("client_email")}')
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    drive = build('drive', 'v3', credentials=creds)
    sheets = build('sheets', 'v4', credentials=creds)

    # 1) 取得
    files, token = [], None
    while True:
        res = drive.files().list(
            q=f"'{FOLDER_ID}' in parents and mimeType='application/pdf' and trashed=false",
            fields='nextPageToken, files(id,name,size,modifiedTime)',
            pageSize=200, pageToken=token).execute()
        files += res.get('files', [])
        token = res.get('nextPageToken')
        if not token:
            break
    print(f'フォルダのPDF: {len(files)}件')

    # 2) 解析（年月の無いものは外す）
    picked = {}
    for f in files:
        ym = parse_year_month(f['name'])
        if not ym:
            print(f'  載せない（ファイル名に年月なし）: {f["name"]}')
            continue
        cur = picked.get(ym)
        if cur is None or f['modifiedTime'] > cur['modifiedTime']:
            if cur is not None:
                print(f'  同じ号が複数 → 新しいほうを採用: {f["name"]}（外す: {cur["name"]}）')
            picked[ym] = f
        else:
            print(f'  同じ号が複数 → 外す: {f["name"]}')

    # 3) 行の組み立て（新しい号が上）
    rows = [HEADER]
    for (y, mo) in sorted(picked, reverse=True):
        f = picked[(y, mo)]
        make_public(drive, f['id'])
        size_mb = round(int(f.get('size', 0)) / 1024 / 1024, 1)
        rows.append([
            y, mo, f'{y}年{mo}月号',
            f'https://drive.google.com/thumbnail?id={f["id"]}&sz=w1200',
            f'https://drive.usercontent.google.com/download?id={f["id"]}&export=download',
            size_mb, f['name'],
            datetime.now(JST).strftime('%Y-%m-%d %H:%M'),
        ])
        print(f'  掲載: {y}年{mo}月号 ← {f["name"]}')

    # 4) 一覧シートを公開（読み取りのみ）にしてから書き直す
    make_public(drive, SHEET_ID)
    first = sheets.spreadsheets().get(spreadsheetId=SHEET_ID, fields='sheets(properties(title))').execute()
    tab = first['sheets'][0]['properties']['title']
    sheets.spreadsheets().values().clear(spreadsheetId=SHEET_ID, range=f"'{tab}'!A:H").execute()
    sheets.spreadsheets().values().update(
        spreadsheetId=SHEET_ID, range=f"'{tab}'!A1",
        valueInputOption='RAW', body={'values': rows}).execute()
    print(f'一覧シートを更新: {len(rows) - 1}号')


if __name__ == '__main__':
    try:
        main()
    except KeyError as e:
        sys.exit(f'環境変数がありません: {e}')
