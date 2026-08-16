// ============================================================
// Lean Stack Bot — LINE OA + Webhook + Google Sheets
// บอทง่าย ตอบตามคีย์เวิร์ด + เก็บข้อมูลลงชีท (ไม่มี AI / ไม่มีฐานข้อมูล)
// ============================================================
// วิธีติดตั้ง 3 ขั้น (อ่านเต็มใน README.md):
//   1) สร้าง Google Sheet ใหม่ → เอา Spreadsheet ID ใส่ด้านล่าง
//   2) สร้าง LINE OA + เปิด Messaging API → เอา Token/Secret ใส่ด้านล่าง
//   3) รันฟังก์ชัน setup() 1 ครั้ง → Deploy เป็น Web app → ตั้ง LINE webhook
// ============================================================

// ===================== ตั้งค่า 3 จุด (แก้ตรงนี้เท่านั้น) =====================
var SPREADSHEET_ID      = 'YOUR_SPREADSHEET_ID';        // ID ของ Google Sheet
var LINE_ACCESS_TOKEN   = 'YOUR_CHANNEL_ACCESS_TOKEN';  // LINE Developers → Messaging API
var LINE_CHANNEL_SECRET = 'YOUR_CHANNEL_SECRET';        // LINE Developers → Messaging API
// ==========================================================================

// แท็บในชีท (setup() สร้างให้อัตโนมัติ)
var RULES_SHEET = 'คำตอบ';      // คอลัมน์ A=คีย์เวิร์ด(คั่นด้วย ,) , B=คำตอบ
var LOG_SHEET   = 'ข้อความ';    // log ทุกข้อความอัตโนมัติ

var RULES_HEADER = ['คีย์เวิร์ด (คั่นด้วย ,)', 'คำตอบ'];
var LOG_HEADER   = ['เวลา', 'LINE userId', 'ข้อความ', 'คีย์เวิร์ดที่ตรง', 'คำตอบ'];

// ข้อความสำเร็จรูป (แก้ได้ตามต้องการ)
var WELCOME_REPLY = '🤗 สวัสดีจ๊ะ! พิมพ์คีย์เวิร์ด เช่น "ราคา" "ค่าส่ง" "ติดต่อ" แล้วจะตอบให้จ๊ะ';
var FALLBACK_REPLY = '💌 รับทราบจ๊ะ ยังไม่มีคำตอบนี้ในระบบ — ข้อความถูกบันทึกไว้แล้ว เจ้าของร้านจะตอบกลับเร็ว ๆ นี้ค่ะ';
var NON_TEXT_REPLY = 'ป้าเข็มรับเฉพาะข้อความตัวอักษรจ๊ะ 😊 (สติกเกอร์/รูป/เสียง ยังตอบไม่ได้)';

var LINE_REPLY_URL = 'https://api.line.me/v2/bot/message/reply';
var RULES_CACHE_SEC = 300; // แคชกติกาคีย์เวิร์ด 5 นาที (แก้ชีทแล้วรอ 5 นาทีเห็นผล)


// ===================== Entry points (doGet/doPost) =====================

function doGet() {
  // Health check — LINE Verify webhook จะยิง GET มาที่นี่
  return json_({ ok: true, bot: 'lean-stack', time: new Date().toISOString() });
}

function doPost(e) {
  try {
    if (!verifySignature_(e)) return json_({ ok: false, error: 'invalid signature' });
    var data = JSON.parse(e.postData.contents);
    var events = data.events || [];
    for (var i = 0; i < events.length; i++) handleEvent_(events[i]);
    return json_({ ok: true });
  } catch (err) {
    return json_({ ok: false, error: String(err) });
  }
}


// ===================== จัดการเหตุการณ์ LINE =====================

function handleEvent_(ev) {
  if (ev.type === 'follow') {           // ลูกค้าแอดไลน์ครั้งแรก
    replyLine_(ev.replyToken, WELCOME_REPLY);
    return;
  }
  if (ev.type !== 'message' || !ev.message || ev.message.type !== 'text') {
    replyLine_(ev.replyToken, NON_TEXT_REPLY);
    return;
  }
  var text = String(ev.message.text || '');
  var userId = (ev.source && ev.source.userId) || '';
  var matched = matchRule_(text);
  var replyText = matched ? matched.reply : FALLBACK_REPLY;
  logMessage_(userId, text, matched ? matched.keyword : '', replyText);
  replyLine_(ev.replyToken, replyText);
}


// ===================== กติกาคีย์เวิร์ด (อ่านจากชีท) =====================

function normalize_(s) {
  return String(s || '').toLowerCase().replace(/\s+/g, '');
}

function matchRule_(text) {
  var t = normalize_(text);
  var rules = loadRules_();
  for (var i = 0; i < rules.length; i++) {
    for (var j = 0; j < rules[i].keywords.length; j++) {
      var kw = normalize_(rules[i].keywords[j]);
      if (kw && t.indexOf(kw) !== -1) {
        return { keyword: rules[i].keywords[j].trim(), reply: rules[i].reply };
      }
    }
  }
  return null;
}

function loadRules_() {
  var cache = CacheService.getScriptCache();
  var cached = cache.get('rules');
  if (cached) return JSON.parse(cached);
  var rules = [];
  try {
    var sh = getSheet_(RULES_SHEET, RULES_HEADER);
    var last = sh.getLastRow();
    if (last >= 2) {
      var rows = sh.getRange(2, 1, last - 1, 2).getValues();
      for (var i = 0; i < rows.length; i++) {
        var kws = String(rows[i][0] || '').split(',');
        var reply = String(rows[i][1] || '').trim();
        if (kws.length && reply) rules.push({ keywords: kws, reply: reply });
      }
    }
  } catch (e) {
    // แท็บยังไม่มี → rules ว่าง (ตอบ fallback)
  }
  cache.put('rules', JSON.stringify(rules), RULES_CACHE_SEC);
  return rules;
}


// ===================== เขียน log ลงชีท =====================

function logMessage_(userId, text, keyword, replyText) {
  try {
    var sh = getSheet_(LOG_SHEET, LOG_HEADER);
    sh.appendRow([new Date(), userId, text, keyword, replyText]);
  } catch (e) {
    // log พังไม่ควรทำให้บอทไม่ตอบ
  }
}


// ===================== ตัวช่วย =====================

function getSheet_(name, header) {
  var ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  var sh = ss.getSheetByName(name);
  if (!sh) sh = ss.insertSheet(name);
  var lastCol = sh.getLastColumn();
  if (lastCol < 1 || sh.getRange(1, 1, 1, header.length).getValues()[0].join('') !== header.join('')) {
    sh.getRange(1, 1, 1, header.length).setValues([header]);
    sh.getRange(1, 1, 1, header.length).setFontWeight('bold');
  }
  return sh;
}

function replyLine_(replyToken, text) {
  var payload = JSON.stringify({
    replyToken: replyToken,
    messages: [{ type: 'text', text: text }]
  });
  UrlFetchApp.fetch(LINE_REPLY_URL, {
    method: 'post',
    headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + LINE_ACCESS_TOKEN },
    payload: payload,
    muteHttpExceptions: true
  });
}

function verifySignature_(e) {
  if (!LINE_CHANNEL_SECRET) return true; // ยังไม่ตั้ง secret → ข้าม (ไว้ dev)
  var headers = e.postData.headers || {};
  var sig = headers['X-Line-Signature'] || headers['x-line-signature'];
  if (!sig) return false;
  var hash = Utilities.computeHmacSha256Signature(e.postData.contents, LINE_CHANNEL_SECRET);
  return Utilities.base64Encode(hash) === sig;
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}


// ===================== รันครั้งเดียวตอนติดตั้ง =====================

function setup() {
  var ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  // สร้างแท็บคำตอบ + ตัวอย่างกติกา
  var rsh = getSheet_(RULES_SHEET, RULES_HEADER);
  if (rsh.getLastRow() < 2) {
    rsh.getRange(2, 1, 6, 2).setValues([
      ['ราคา,เท่าไหร่,กี่บาท', '💰 ราคาสินค้าดูได้ในร้านเลยจ๊ะ พิมพ์ชื่อสินค้ามา เดี๋ยวบอกให้'],
      ['ค่าส่ง,ส่งฟรี,ขนส่ง', '🚚 ค่าส่งตามร้านค้าใน Shopee จ๊ะ บางร้านส่งฟรี — ดูตอนกดสั่งซื้อได้เลย'],
      ['คืนเงิน,คืนสินค้า,เปลี่ยนสินค้า', '↩️ คืน/เปลี่ยนสินค้าทำในแอป Shopee ตามเงื่อนไขร้านค้าจ๊ะ'],
      ['ติดต่อ,เจ้าของ,แอดมิน,คนจริง', '📞 ติดต่อเจ้าของร้านได้ทางไลน์นี้เลยจ๊ะ ฝากข้อความไว้ จะตอบกลับเร็ว ๆ นี้'],
      ['สวัสดี,hello,hi', '🤗 สวัสดีจ๊ะ มีอะไรให้ช่วยบอกได้เลย'],
      ['ขอบคุณ,ขอบใจ', '😊 ด้วยความยินดีจ๊ะ!'],
    ]);
  }
  getSheet_(LOG_SHEET, LOG_HEADER);
  CacheService.getScriptCache().remove('rules');
  return '✅ setup เสร็จ: สร้างแท็บ "' + RULES_SHEET + '" + "' + LOG_SHEET + '" แล้ว (มีตัวอย่างกติกา 6 ข้อ)';
}
