// ============================================================
// Pakhem bot - Facebook posts log -> Google Sheet
// (แยกจาก sheet_apps_script.gs ที่เก็บแชทลูกค้า — ชีทคนละแท็บ)
// ============================================================
// Setup (3 min, no coding):
//  1. Open https://sheets.google.com -> create a NEW sheet (or reuse
//     the chat-log sheet) -> copy the SHEET ID from the URL:
//     https://docs.google.com/spreadsheets/d/<SHEET_ID_HERE>/edit
//  2. Open https://script.google.com -> "+ New project"
//  3. Delete ALL default code, paste THIS WHOLE FILE, fill SPREADSHEET_ID
//  4. Save -> Deploy -> New deployment -> type "Web app"
//     -> Execute as: Me -> Who has access: Anyone -> Deploy -> allow permissions
//  5. Copy the URL (https://script.google.com/macros/s/....../exec)
//     and set it as POSTS_SHEET_WEBHOOK_URL on Render
// ============================================================

// REQUIRED: ID of the target Google Sheet (same or different from chat-log sheet)
// = ชีทเดียวกับ sheet_apps_script.gs ของคุณ (แท็บใหม่ 'โพสต์เพจ' — ไม่แตะแท็บ 'คำถามลูกค้า')
var SPREADSHEET_ID = '1UmWfFTkC7PjPV9h32mf639fhaJWraK8Vg_JK5C-Yqmg';

var SHEET_NAME = 'โพสต์เพจ';   // sheet tab name (changeable)
var HEADER = ['เวลา', 'ประเภท', 'หัวข้อ', 'ข้อความ', 'ลิงก์', 'Post ID', 'URL โพสต์'];

function getSheet_() {
  // Standalone script (from script.google.com) CANNOT use getActiveSpreadsheet()
  // (returns null -> 500 error). Use openById instead.
  var ss = SPREADSHEET_ID
    ? SpreadsheetApp.openById(SPREADSHEET_ID)
    : SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(SHEET_NAME);
  if (!sh) {
    sh = ss.insertSheet(SHEET_NAME);
  }
  // Always ensure the header row matches (upgrades old sheets)
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
