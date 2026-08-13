// ═══════════════════════════════════════════════════════════════
// ป้าเข็ม ขายของ — เขียนคำถามลูกค้าลง Google ชีทอัตโนมัติ
// ═══════════════════════════════════════════════════════════════
// วิธีติดตั้ง (2 นาที ไม่ต้องเขียนโค้ด):
//  1. เปิด https://script.google.com → "โปรเจกต์ใหม่" (New project)
//  2. ลบโค้ดเดิมทิ้ง แล้ววางโค้ดนี้ทั้งไฟล์
//  3. กด "บันทึก" (💾) แล้วกด "Deploy" → "New deployment"
//     → ประเภท "Web app" → เข้าถึง "Anyone" (Execute as: Me)
//  4. ก๊อป URL (https://script.google.com/macros/s/....../exec)
//     ส่งให้ทีมตั้งค่า → ใส่เป็น SHEET_WEBHOOK_URL บน Render
//  5. เปิด Google ชีทที่ต้องการ (สร้างชีทใหม่ก็ได้) — บอทจะเขียนแถวใหม่
//     ต่อท้ายอัตโนมัติทุกข้อความที่ลูกค้าพิมพ์
// ═══════════════════════════════════════════════════════════════

var SHEET_NAME = 'คำถามลูกค้า';   // ชื่อชีทในไฟล์ (เปลี่ยนได้)
var MAX_AGE_DAYS = 90;            // เก็บ 90 วันตาม PDPA — ลบของเก่าอัตโนมัติ

function doPost(e) {
  try {
    var data = JSON.parse(e.postData.contents);
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var sh = ss.getSheetByName(SHEET_NAME);
    if (!sh) {
      sh = ss.insertSheet(SHEET_NAME);
      sh.appendRow(['เวลา', 'ผู้ใช้', 'ข้อความ', 'ประเภท', 'หมวด', 'ตอบแบบ']);
      sh.getRange(1, 1, 1, 6).setFontWeight('bold');
    }

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
      data.reply_kind || 'text'
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
