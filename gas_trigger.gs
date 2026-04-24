/**
 * スクーミーフェスタ年間スケジュール PDF 更新トリガー
 * （シンプル版 + デザイン版の統合制御）
 *
 * 使い方:
 *   1. スプレッドシートを開き「拡張機能」→「Apps Script」
 *   2. 既存のコードを全て削除してこのコード全文を貼り付け
 *   3. GITHUB_TOKEN を実トークンに差し替え
 *   4. 保存 → シートに戻り再読み込み
 *   5. メニュー「📄 PDF操作」→「① PDFを生成・更新（両方）」で両方のPDFが更新される
 *   6. 初回のみ UrlFetch へのアクセス許可を承認
 */

// 共通定数
const GITHUB_OWNER = 'shiojima-test';
const GITHUB_TOKEN = 'PASTE_YOUR_GITHUB_TOKEN_HERE';
const DRIVE_FOLDER_URL = 'https://drive.google.com/drive/folders/12caVEED6ZAF_g30o3ZWmI67GA3g9aFvz';

// シンプル版（既存）
const GITHUB_REPO_SIMPLE = 'schoomy-schedule-pdf';
const PDF_SIMPLE_DIRECT_URL = 'https://drive.google.com/uc?export=download&id=11MbcUecXNnd1bCroHQr5s117FpouooRj';

// デザイン版（新規）
const GITHUB_REPO_DESIGN = 'schoomy-schedule-magazine-pdf';
const PDF_DESIGN_DIRECT_URL = 'https://drive.google.com/uc?export=download&id=1c5muRsTSuCQjKRYl9zTXI15CV7AY6ite';

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('📄 PDF操作')
    .addItem('① PDFを生成・更新（両方）', 'triggerBothPdfGeneration')
    .addSeparator()
    .addItem('② シンプル版ダウンロードURLを表示', 'showSimpleDownloadUrl')
    .addItem('③ デザイン版ダウンロードURLを表示', 'showDesignDownloadUrl')
    .addItem('④ Driveフォルダを開く', 'openDriveFolder')
    .addToUi();
}

/**
 * ボタン1個で両方のPDFを更新する統合トリガー
 * シンプル版・デザイン版のGitHub Actionsを両方起動する
 */
function triggerBothPdfGeneration() {
  const ui = SpreadsheetApp.getUi();
  const results = [];

  // シンプル版
  const r1 = dispatchToRepo(GITHUB_REPO_SIMPLE);
  results.push(`シンプル版: ${r1.ok ? '✅ 起動成功' : '❌ ' + r1.error}`);

  // デザイン版
  const r2 = dispatchToRepo(GITHUB_REPO_DESIGN);
  results.push(`デザイン版: ${r2.ok ? '✅ 起動成功' : '❌ ' + r2.error}`);

  const allOk = r1.ok && r2.ok;
  const title = allOk ? '✅ 両方のPDF生成を開始しました' : '⚠️ 一部エラー';
  const msg =
    results.join('\n') + '\n\n' +
    '両方とも 1-2分後に Google Drive フォルダに最新PDFが作成されます。\n\n' +
    '▼ シンプル版 SWELL用URL:\n' + PDF_SIMPLE_DIRECT_URL + '\n\n' +
    '▼ デザイン版 SWELL用URL:\n' + PDF_DESIGN_DIRECT_URL;

  ui.alert(title, msg, ui.ButtonSet.OK);
}

/**
 * 指定リポジトリにrepository_dispatchイベントを送る
 * @return {{ok: boolean, error?: string}}
 */
function dispatchToRepo(repo) {
  const url = `https://api.github.com/repos/${GITHUB_OWNER}/${repo}/dispatches`;
  try {
    const response = UrlFetchApp.fetch(url, {
      method: 'post',
      headers: {
        'Authorization': `Bearer ${GITHUB_TOKEN}`,
        'Accept': 'application/vnd.github+json',
      },
      contentType: 'application/json',
      payload: JSON.stringify({ event_type: 'generate-pdf' }),
      muteHttpExceptions: true,
    });
    const code = response.getResponseCode();
    if (code === 204) {
      return { ok: true };
    } else {
      return { ok: false, error: `HTTP ${code}: ${response.getContentText()}` };
    }
  } catch (e) {
    return { ok: false, error: e.toString() };
  }
}

function showSimpleDownloadUrl() {
  SpreadsheetApp.getUi().alert(
    'SWELL に貼るシンプル版ダウンロードURL',
    PDF_SIMPLE_DIRECT_URL + '\n\n※このURLは固定なので、PDFを更新してもリンクは変わりません。',
    SpreadsheetApp.getUi().ButtonSet.OK
  );
}

function showDesignDownloadUrl() {
  SpreadsheetApp.getUi().alert(
    'SWELL に貼るデザイン版ダウンロードURL',
    PDF_DESIGN_DIRECT_URL + '\n\n※このURLは固定なので、PDFを更新してもリンクは変わりません。',
    SpreadsheetApp.getUi().ButtonSet.OK
  );
}

function openDriveFolder() {
  SpreadsheetApp.getUi().alert(
    'Google Drive フォルダ',
    DRIVE_FOLDER_URL,
    SpreadsheetApp.getUi().ButtonSet.OK
  );
}
