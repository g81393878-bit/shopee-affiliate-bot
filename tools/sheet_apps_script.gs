// ═══════════════════════════════════════════════════════════════
// ป้าเข็ม ขายของ — เขียนคำถามลูกค้าลง Google ชีทอัตโนมัติ
// ═══════════════════════════════════════════════════════════════
// วิธีติดตั้ง (3 นาที ไม่ต้องเขียนโค้ด):
//  1. เปิด https://sheets.google.com → สร้างชีทใหม่ (หรือเปิดชีทเดิม)
//     ก๊อป **ID ชีท** จาก URL: https://docs.google.com/spreadsheets/d/<ID ตรงนี้>/edit
//  2. เปิด https://script.google.com → "+ โปรเจกต์ใหม่"
//  3. ลบโค้ดเดิมทิ้ง วางโค้ดนี้ทั้งไฟล์ แล้ว **ใส่ ID ชีท** ในบรรทัด SPREADSHEET_ID
//  4. กด 💾 บันทึก → Deploy → New deployment → ประเภท "Web app"
//     → Execute as: Me → เข้าถึง: Anyone → Deploy → ยอมรับสิทธิ์
//  5. ก๊อป URL (https://script.google.com/macros/s/....../exec)
//     ส่งให้ทีมตั้งค่า → ใส่เป็น SHEET_WEBHOOK_URL บน Render
// ═══════════════════════════════════════════════════════════════

// ★ ต้องใส่! ID ของ Google ชีทที่ต้องการ (จาก URL ชีท — ดูวิธีติดตั้งข้อ 1)
var SPREADSHEET_ID = '';   // เช่น '1AbCdEfGhIjKlMnOpQrStUvWxYz1234567890'

var SHEET_NAME = 'คำถามลูกค้า';   // ชื่อชีทในไฟล์ (เปลี่ยนได้)
var MAX_AGE_DAYS = 90;            // เก็บ 90 วันตาม PDPA — ลบของเก่าอัตโนมัติ

function getSheet_() {
  // สคริปต์ standalone (สร้างจาก script.google.com) ใช้ getActiveSpreadsheet()
  // ไม่ได้ (คืน null → พัง 500) — ต้อง openById ด้วย ID ที่กรอกไว้ข้างบน
  var ss = SPREADSHEET_ID
    ? SpreadsheetApp.openById(SPREADSHEET_ID)
    : SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(SHEET_NAME);
  var HEADER = ['เวลา', 'ผู้ใช้', 'ข้อความ', 'ประเภท', 'หมวด', 'ตอบแบบ', 'คำตอบ'];
  if (!sh) {
    sh = ss.insertSheet(SHEET_NAME);
  }
  // ตรวจ/สร้างหัวตารางให้ตรงเสมอ (รองรับชีทที่สร้างด้วยโค้ดเวอร์ชันเก่า 6 คอลัมน์)
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

    // คำสั่ง "ลบข้อมูลฉัน" (PDPA) — ลบทุกแถวของผู้ใช้นี้ออกจากชีท
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

    // เขียนข้อความใหม่
    sh.appendRow([
      data.created_at || new Date().toISOString(),
      data.line_user_id || '',
      data.message_text || '',
      data.intent_label || data.intent || '',
      data.category || '',
      data.reply_kind || 'text',
      data.reply_text || ''
    ]);

    // ลบแถวเก่ากว่า 90 วัน (PDPA — กันชีทโตไม่มีที่สิ้นสุด)
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
