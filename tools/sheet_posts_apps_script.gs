// ============================================================
// Pakhem bot - Facebook posts log -> Google Sheet
// (separate tab from the customer-chat sheet)
// ============================================================
// Setup (3 min):
//  1. sheets.google.com -> use the SAME spreadsheet as your chat log
//  2. script.google.com -> "+ New project" (do NOT open the chat project)
//  3. Delete ALL default code, paste THIS WHOLE FILE
//  4. Save -> Deploy -> New deployment -> type "Web app"
//     -> Execute as: Me -> Who has access: Anyone -> Deploy
//  5. Copy the URL and set it as POSTS_SHEET_WEBHOOK_URL on Render
// ============================================================

var SPREADSHEET_ID = '1UmWfFTkC7PjPV9h32mf639fhaJWraK8Vg_JK5C-Yqmg';

var SHEET_NAME = 'โพสต์เพจ';
var HEADER = ['เวลา', 'ประเภท', 'หัวข้อ', 'ข้อความ', 'ลิงก์', 'Post ID', 'URL โพสต์'];

function getSheet_() {
  var ss = SPREADSHEET_ID
    ? SpreadsheetApp.openById(SPREADSHEET_ID)
    : SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(SHEET_NAME);
  if (!sh) {
    sh = ss.insertSheet(SHEET_NAME);
  }
  var lastCol = sh.getLastColumn();
  if (lastCol < 1 || sh.getRange(1, 1, 1, HEADER.length).getValues()[0].join('') !== HEADER.join('')) {
    sh.getRange(1, 1, 1, HEADER.length).setValues([HEADER]);
    sh.getRange(1, 1, 1, HEADER.length).setFontWeight('bold');
  }
  return sh;
}

function doPost(e) {
  try {
    var data = JSON.parse(e.postData.contents);
    var sh = getSheet_();
    var kind = String(data.kind || '');
    var kindLabel = kind === 'product' ? 'ขายสินค้า'
                  : kind === 'intro' ? 'แนะนำตัว'
                  : kind;
    sh.appendRow([
      data.created_at || new Date().toISOString(),
      kindLabel,
      data.title || '',
      (data.message || '').replace(/\r?\n/g, ' '),
      data.link || '',
      data.post_id || '',
      data.post_url || ''
    ]);
    return json_({ ok: true });
  } catch (err) {
    return json_({ ok: false, error: String(err) });
  }
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
