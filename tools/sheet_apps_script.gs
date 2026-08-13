// ============================================================
// Pakhem bot - write customer messages to Google Sheet
// ============================================================
// Setup (3 min, no coding):
//  1. Open https://sheets.google.com -> create a new sheet (or open existing)
//     Copy the SHEET ID from the URL:
//     https://docs.google.com/spreadsheets/d/<SHEET_ID_HERE>/edit
//  2. Open https://script.google.com -> "+ New project"
//  3. Delete ALL default code, paste THIS WHOLE FILE, then fill SPREADSHEET_ID below
//  4. Click Save -> Deploy -> New deployment -> type "Web app"
//     -> Execute as: Me -> Who has access: Anyone -> Deploy -> allow permissions
//  5. Copy the URL (https://script.google.com/macros/s/....../exec)
//     and send it to the team -> set as SHEET_WEBHOOK_URL on Render
// ============================================================

// REQUIRED: ID of the target Google Sheet (see setup step 1)
var SPREADSHEET_ID = '';   // e.g. '1AbCdEfGhIjKlMnOpQrStUvWxYz1234567890'

var SHEET_NAME = 'คำถามลูกค้า';   // sheet tab name (changeable)
var MAX_AGE_DAYS = 90;            // keep 90 days per PDPA - auto delete old rows

function getSheet_() {
  // A standalone script (created from script.google.com) CANNOT use
  // getActiveSpreadsheet() (returns null -> 500 error). Use openById instead.
  var ss = SPREADSHEET_ID
    ? SpreadsheetApp.openById(SPREADSHEET_ID)
    : SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(SHEET_NAME);
  var HEADER = ['เวลา', 'ผู้ใช้', 'ข้อความ', 'ประเภท', 'หมวด', 'ตอบแบบ', 'คำตอบ'];
  if (!sh) {
    sh = ss.insertSheet(SHEET_NAME);
  }
  // Always ensure the header row matches (also upgrades old 6-column sheets)
  var lastCol = sh.getLastColumn();
  if (lastCol < 1 || sh.getRange(1, 1, 1, 7).getValues()[0].join('') !== HEADER.join('')) {
    sh.getRange(1, 1, 1, 7).setValues([HEADER]);
    sh.getRange(1, 1, 1, 7).setFontWeight('bold');
  }
  return sh;
}

function doPost(e) {
  try {
    var data = JSON.parse(e.postData.contents);
    var sh = getSheet_();

    // "ลบข้อมูลฉัน" (PDPA) - delete every row of this user from the sheet
    if (data.action === 'delete_user') {
      var uid = String(data.line_user_id || '');
      var last = sh.getLastRow();
      for (var r = last; r >= 2; r--) {
        if (String(sh.getRange(r, 2).getValue()) === uid) {
          sh.deleteRow(r);
        }
      }
      return json_({ ok: true, deleted_rows: last - sh.getLastRow() });
    }

    // Append new row
    sh.appendRow([
      data.created_at || new Date().toISOString(),
      data.line_user_id || '',
      data.message_text || '',
      data.intent_label || data.intent || '',
      data.category || '',
      data.reply_kind || 'text',
      data.reply_text || ''
    ]);

    // Delete rows older than 90 days (PDPA - keep the sheet from growing forever)
    var cutoff = new Date(Date.now() - MAX_AGE_DAYS * 24 * 60 * 60 * 1000);
    var last2 = sh.getLastRow();
    for (var r2 = last2; r2 >= 2; r2--) {
      var v = sh.getRange(r2, 1).getValue();
      if (v instanceof Date && v.getTime() < cutoff.getTime()) {
        sh.deleteRow(r2);
      }
    }
    return json_({ ok: true });
  } catch (err) {
    return json_({ ok: false, error: String(err) });
  }
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
