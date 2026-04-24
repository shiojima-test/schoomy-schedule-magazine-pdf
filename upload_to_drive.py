"""Google Drive にPDFをアップロード（同名ファイルがあれば内容上書き）"""
import os
import sys
import json
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account

SCOPES = ['https://www.googleapis.com/auth/drive']
FOLDER_ID = '12caVEED6ZAF_g30o3ZWmI67GA3g9aFvz'
PDF_NAME = 'スクーミーフェスタ年間スケジュール_デザイン版_2026年度.pdf'


def upload_pdf(local_path, credentials_json_str):
    creds_info = json.loads(credentials_json_str)
    creds = service_account.Credentials.from_service_account_info(
        creds_info, scopes=SCOPES)
    drive = build('drive', 'v3', credentials=creds)

    query = f"name='{PDF_NAME}' and '{FOLDER_ID}' in parents and trashed=false"
    results = drive.files().list(q=query, fields='files(id, name)').execute()
    existing = results.get('files', [])

    media = MediaFileUpload(local_path, mimetype='application/pdf')

    if existing:
        file_id = existing[0]['id']
        file = drive.files().update(
            fileId=file_id,
            media_body=media,
            fields='id, webViewLink'
        ).execute()
        print(f'既存ファイル上書き: {file_id}')
    else:
        metadata = {'name': PDF_NAME, 'parents': [FOLDER_ID]}
        file = drive.files().create(
            body=metadata, media_body=media,
            fields='id, webViewLink'
        ).execute()
        print(f'新規作成: {file["id"]}')

    try:
        drive.permissions().create(
            fileId=file['id'],
            body={'type': 'anyone', 'role': 'reader'},
        ).execute()
    except Exception as e:
        print(f'権限設定スキップ（既に公開済みかも）: {e}')

    print(f'Uploaded: {file["webViewLink"]}')
    return file['id']


if __name__ == '__main__':
    local_pdf = sys.argv[1]
    creds = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
    if not creds:
        raise RuntimeError('GOOGLE_SERVICE_ACCOUNT_JSON env var is required')
    upload_pdf(local_pdf, creds)
