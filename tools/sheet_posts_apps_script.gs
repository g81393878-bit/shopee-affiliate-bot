// ============================================================
// Pakhem bot - combined Google Sheet logger
// Handles BOTH customer chat (tab "คำถามลูกค้า") AND
// Facebook posts (tab "FB Posts") from ONE webhook URL.
// (Replaces tools/sheet_apps_script.gs - use this single script.)
// ============================================================
// Deploy: script.google.com -> paste this whole file -> Deploy
// -> Web app -> Execute as: Me -> Who has access: Anyone.
// Set the SAME URL as both SHEET_WEBHOOK_URL and
// POSTS_SHEET_WEBHOOK_URL on Render.
// ============================================================

var SPREADSHEET_ID = '1UmWfFTkC7PjPV9h32mf639fhaJWraK8Vg_JK5C-Yqmg';

var CHAT_SHEET = 'คำถามลูกค้า';
var POSTS_SHEET = 'FB Posts';
var GROUPS_SHEET = 'กลุ่มผู้สมัคร';
var MAX_AGE_DAYS = 90;

var CHAT_HEADER = ['เวลา', 'ผู้ใช้', 'ข้อความ', 'ประเภท', 'หมวด', 'ตอบแบบ', 'คำตอบ'];
var POSTS_HEADER = ['Time', 'Type', 'Title', 'Message', 'Link', 'Post ID', 'Post URL'];
var GROUPS_HEADER = ['เวลา', 'ชื่อกลุ่ม', 'ลิงก์', 'สิ่งที่ต้องการ', 'โพสต์อยากซื้อ', 'โพสต์ขาย', 'สแกนได้', 'ตัวอย่างโพสต์'];

function getSheet_(name, header) {
  var ss = SPREADSHEET_ID
    ? SpreadsheetApp.openById(SPREADSHEET_ID)
    : SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(name);
  if (!sh) {
    sh = ss.insertSheet(name);
  }
  var lastCol = sh.getLastColumn();
  if (lastCol < 1 || sh.getRange(1, 1, 1, header.length).getValues()[0].join('') !== header.join('')) {
    sh.getRange(1, 1, 1, header.length).setValues([header]);
    sh.getRange(1, 1, 1, header.length).setFontWeight('bold');
  }
  return sh;
}

function doGet() {
  var ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  return json_({ spreadsheet: ss.getName(), id: ss.getId() });
}

function doPost(e) {
  try {
    var data = JSON.parse(e.postData.contents);

    // ---- Group candidate row (kind=group_candidate) -> กลุ่มผู้สมัคร tab ----
    if (data.kind === 'group_candidate') {
      var gsh = getSheet_(GROUPS_SHEET, GROUPS_HEADER);
      gsh.appendRow([
        data.created_at || new Date().toISOString(),
        data.group_name || '',
        data.group_url || '',
        data.want || '',
        data.buyer_signals || 0,
        data.seller_signals || 0,
        data.scannable ? 'ใช่' : 'ไม่',
        (data.sample_post || '').replace(/\r?\n/g, ' ')
      ]);
      return json_({ ok: true, sheet: GROUPS_SHEET, rows: Math.max(0, gsh.getLastRow() - 1) });
    }

    // ---- Facebook post row (has 'kind' field) -> FB Posts tab ----
    if (data.kind) {
      var psh = getSheet_(POSTS_SHEET, POSTS_HEADER);
      var kindLabel = data.kind === 'product' ? 'Sell product'
                    : data.kind === 'intro' ? 'Introduce'
                    : data.kind;
      psh.appendRow([
        data.created_at || new Date().toISOString(),
        kindLabel,
        data.title || '',
        (data.message || '').replace(/\r?\n/g, ' '),
        data.link || '',
        data.post_id || '',
        data.post_url || ''
      ]);
      return json_({ ok: true, sheet: POSTS_SHEET, rows: Math.max(0, psh.getLastRow() - 1) });
    }

    // ---- Customer chat row -> คำถามลูกค้า tab (original behavior) ----
    var csh = getSheet_(CHAT_SHEET, CHAT_HEADER);

    if (data.action === 'delete_user') {
      var uid = String(data.line_user_id || '');
      var last = csh.getLastRow();
      for (var r = last; r >= 2; r--) {
        if (String(csh.getRange(r, 2).getValue()) === uid) {
          csh.deleteRow(r);
        }
      }
      return json_({ ok: true, deleted_rows: last - csh.getLastRow() });
    }

    csh.appendRow([
      data.created_at || new Date().toISOString(),
      data.line_user_id || '',
      data.message_text || '',
      data.intent_label || data.intent || '',
      data.category || '',
      data.reply_kind || 'text',
      data.reply_text || ''
    ]);

    var cutoff = new Date(Date.now() - MAX_AGE_DAYS * 24 * 60 * 60 * 1000);
    var last2 = csh.getLastRow();
    for (var r2 = last2; r2 >= 2; r2--) {
      var v = csh.getRange(r2, 1).getValue();
      if (v instanceof Date && v.getTime() < cutoff.getTime()) {
        csh.deleteRow(r2);
      }
    }
    return json_({ ok: true, sheet: CHAT_SHEET });
  } catch (err) {
    return json_({ ok: false, error: String(err) });
  }
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
