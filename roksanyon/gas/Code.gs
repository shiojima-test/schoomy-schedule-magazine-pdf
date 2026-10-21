/**
 * ロクサンヨン アップロード v1.0
 *
 * サトエリさん用のアップ画面（ウェブアプリ）。
 * 月号を選んでPDFを送ると、ドライブの「ロクサンヨン公開」フォルダに置き、
 * ホームページが読む掲載一覧シートをその場で作り直す。
 *
 * デプロイ: ウェブアプリ / 次のユーザーとして実行=自分 / アクセス=全員
 */
var VERSION = '1.0';
var FOLDER_ID = '1acenOS-UcYfSbFqtKL_Nt8D8ymrmj6YU';                 // ロクサンヨン公開
var SHEET_ID = '1v5_TuOy0FcOQoDqXcYIV6YqHJTPburmvtccXyNBwsUc';       // ロクサンヨン掲載一覧（自動・さわらない）
var PASSCODE = 'roku634';                                             // アップ画面の合言葉
var HEADER = ['year', 'month', 'label', 'cover_url', 'download_url', 'size_mb', 'file_name', 'updated', 'file_id'];
var MAX_MB = 30;

function doGet() {
  return HtmlService.createHtmlOutputFromFile('Index')
    .setTitle('ロクサンヨン アップロード')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

function checkPass_(pass) {
  if (String(pass || '').trim() !== PASSCODE) throw new Error('合言葉がちがいます。');
}

/** 画面から: 公開中の号の一覧 */
function listIssues(pass) {
  checkPass_(pass);
  return collect_().map(function (it) {
    return { id: it.id, label: it.label, uploaded: it.updated };
  });
}

/** 画面から: アップして公開 */
function uploadIssue(pass, year, month, base64) {
  checkPass_(pass);
  year = Number(year); month = Number(month);
  if (!(year >= 2020 && year <= 2100) || !(month >= 1 && month <= 12)) throw new Error('月号の選び方がおかしいようです。');
  if (!base64) throw new Error('PDFが選ばれていません。');

  var bytes = Utilities.base64Decode(base64);
  if (bytes.length > MAX_MB * 1024 * 1024) throw new Error('PDFが大きすぎます（' + MAX_MB + 'MBまで）。');
  // PDFの先頭は %PDF
  if (!(bytes[0] === 0x25 && bytes[1] === 0x50 && bytes[2] === 0x44 && bytes[3] === 0x46)) throw new Error('PDFではないファイルのようです。');

  var name = 'ロクサンヨン_' + year + '-' + ('0' + month).slice(-2) + '.pdf';
  var folder = DriveApp.getFolderById(FOLDER_ID);

  // 同じ月号があれば差し替え（古いほうはゴミ箱へ。完全には消さない）
  var lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    var file = folder.createFile(Utilities.newBlob(bytes, 'application/pdf', name));
    file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
    var same = folder.getFilesByName(name);
    while (same.hasNext()) {
      var f = same.next();
      if (f.getId() !== file.getId()) f.setTrashed(true);
    }
    rebuild_();
  } finally {
    lock.releaseLock();
  }
  return { label: year + '年' + month + '月号', id: file.getId(), list: listIssues(pass) };
}

/** 画面から: 取り下げ（ゴミ箱へ。ドライブのゴミ箱から戻せる） */
function withdrawIssue(pass, fileId) {
  checkPass_(pass);
  var file = DriveApp.getFileById(fileId);
  var parents = file.getParents(), inFolder = false;
  while (parents.hasNext()) { if (parents.next().getId() === FOLDER_ID) inFolder = true; }
  if (!inFolder) throw new Error('ロクサンヨン公開フォルダのファイルではありません。');
  var lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    file.setTrashed(true);
    rebuild_();
  } finally {
    lock.releaseLock();
  }
  return listIssues(pass);
}

/** フォルダから号を集める（ファイル名に年月が無いものは載せない・同じ号は新しいほう） */
function collect_() {
  var re = /(20\d{2})\s*(?:[-_.年\/ ]\s*)?(\d{1,2})(?!\d)/;
  var picked = {};
  var it = DriveApp.getFolderById(FOLDER_ID).getFilesByType(MimeType.PDF);
  while (it.hasNext()) {
    var f = it.next();
    if (f.isTrashed()) continue;
    var m = f.getName().match(re);
    if (!m) continue;
    var y = Number(m[1]), mo = Number(m[2]);
    if (mo < 1 || mo > 12) continue;
    var key = y * 100 + mo;
    if (!picked[key] || f.getDateCreated() > picked[key].created) {
      picked[key] = { file: f, y: y, mo: mo, created: f.getDateCreated() };
    }
  }
  return Object.keys(picked).map(Number).sort(function (a, b) { return b - a; }).map(function (k) {
    var p = picked[k], id = p.file.getId();
    return {
      id: id, year: p.y, month: p.mo, label: p.y + '年' + p.mo + '月号',
      cover: 'https://drive.google.com/thumbnail?id=' + id + '&sz=w1200',
      download: 'https://drive.usercontent.google.com/download?id=' + id + '&export=download',
      size: Math.round(p.file.getSize() / 1024 / 1024 * 10) / 10,
      name: p.file.getName(),
      updated: Utilities.formatDate(p.created, 'Asia/Tokyo', 'M/d H:mm'),
    };
  });
}

/** 掲載一覧シートを作り直す（組み立ててから書く。先に消さない） */
function rebuild_() {
  var rows = [HEADER].concat(collect_().map(function (i) {
    return [i.year, i.month, i.label, i.cover, i.download, i.size, i.name, i.updated, i.id];
  }));
  var sh = SpreadsheetApp.openById(SHEET_ID).getSheets()[0];
  sh.getRange(1, 1, rows.length, HEADER.length).setValues(rows);
  var extra = sh.getLastRow() - rows.length;
  if (extra > 0) sh.getRange(rows.length + 1, 1, extra, sh.getLastColumn()).clearContent();
  DriveApp.getFileById(SHEET_ID).setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
}

/** エディタから一度だけ実行して、権限の許可と動作確認をする */
function setupTest() {
  rebuild_();
  Logger.log('ロクサンヨン アップロード v' + VERSION + ' / 公開中 ' + collect_().length + '号');
}
