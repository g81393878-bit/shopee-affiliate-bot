
function recordLeadActivity(senderId, hasOrdered) {
  if (!senderId) return;
  try {
    var props = PropertiesService.getScriptProperties();
    var key = "LEAD_" + senderId;
    var existing = props.getProperty(key);
    var data = existing ? JSON.parse(existing) : { senderId: senderId, firstTime: Date.now(), followedUp: false };
    data.lastTime = Date.now();
    data.ordered = !!hasOrdered;
    props.setProperty(key, JSON.stringify(data));
  } catch (e) {
    Logger.log("recordLeadActivity error: " + e);
  }
}

function autoFollowUpSilentLeads() {
  try {
    var props = PropertiesService.getScriptProperties();
    var allProps = props.getProperties();
    var now = Date.now();
    var count = 0;

    for (var key in allProps) {
      if (key.indexOf("LEAD_") !== 0) continue;
      try {
        var lead = JSON.parse(allProps[key]);
        if (!lead || lead.ordered || lead.followedUp) continue;

        var elapsedHours = (now - lead.lastTime) / (1000 * 60 * 60);
        // ทักตามหลังเงียบไป 1.5 - 20 ชั่วโมง
        if (elapsedHours >= 1.5 && elapsedHours <= 20.0) {
          var followUpMsg = 
            "🐟 [ทีมงานร้านปลาสลิดป้าเข็ม สุพรรณบุรีแท้] 🙏✨\n" +
            "สวัสดีค่ะคุณลูกค้า ขออนุญาตทักสอบถามเพิ่มเติมนะคะ พอดีทีมงานกำลังจะสรุปรอบแพ็กปลาสลิดสดใหม่ตากโดมโซล่าร์สำหรับจัดส่งรอบเช้าค่ะ 🧊🚚\n\n" +
            "คุณลูกค้าสนใจรับเป็นชุดยอดฮิต 1 กิโลกรัม (550.-) หรือชุดพอดีมื้อ 500g (390.-) โอนเงินส่งฟรีถึงหน้าบ้านดีคะ? 😊\n" +
            "(หากรับ พิมพ์แจ้ง 'ชื่อ-ที่อยู่-เบอร์โทร' ในแชทนี้ได้เลยนะคะ เดี๋ยวทีมงานล็อคของรอบสดใหม่ให้ทันทีค่ะ 💕)";

          replyFacebook(lead.senderId, followUpMsg);
          lead.followedUp = true;
          props.setProperty(key, JSON.stringify(lead));
          count++;

          pushAdminAlert(
            "🔄 [ระบบคลาวด์ส่งข้อความทักตามลูกค้าที่เงียบไปเรียบร้อยค่ะ] 🔔\n" +
            "👤 Facebook ID: " + lead.senderId + "\n" +
            "⏰ เวลาที่เงียบไป: " + elapsedHours.toFixed(1) + " ชม."
          );
        } else if (elapsedHours > 24.0) {
          // ลบข้อมูลที่เก่าเกิน 24 ชม. เพื่อประหยัดพื้นที่ ScriptProperties
          props.deleteProperty(key);
        }
      } catch (err) {}
    }
    return count;
  } catch (e) {
    Logger.log("autoFollowUpSilentLeads error: " + e);
    return 0;
  }
}

function setUpFollowUpTrigger() {
  var triggers = ScriptApp.getProjectTriggers();
  var exists = false;
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === "autoFollowUpSilentLeads") {
      exists = true;
      break;
    }
  }
  if (!exists) {
    ScriptApp.newTrigger("autoFollowUpSilentLeads")
      .timeBased()
      .everyHours(1)
      .create();
    return "created";
  }
  return "already_exists";
}

function extractPhoneOnly(text) {
  if (!text) return null;
  var phoneMatch = text.match(/(?:0[689]\d{8}|0[689]\d{1}[-\s]?\d{3}[-\s]?\d{4}|0[689]\d{2}[-\s]?\d{3}[-\s]?\d{3})/);
  if (!phoneMatch) return null;
  var hasAddress = /(?:บ้านเลขที่|ต\.|อ\.|จ\.|ตำบล|อำเภอ|จังหวัด|ถ\.|ถนน|ซอย|แขวง|เขต|\b\d{5}\b)/.test(text);
  if (hasAddress || text.length > 50) {
    return null; // Might be a full order/address, handled by extractOrderDetails
  }
  return phoneMatch[0].replace(/[-\s]/g, "");
}
/**
 * =========================================================================
 * 🐟 ปลาสลิดแดดเดียว สุพรรณบุรีแท้ ป้าเข็ม คัดพิเศษ — LINE OA & Messenger Engine (@137gsref)
 * Google Apps Script Master Unified Engine (100% Direct Fish Storefront & CRM)
 * =========================================================================
 * 1. 🐟 ระบบรับออเดอร์และแนะนำแพ็กเกจปลาสลิดแดดเดียว สุพรรณบุรีแท้ (ไซส์จัมโบ้ 4 ตัวโล คัดพิเศษ)
 * 2. 🧊 มาตรฐานแพ็กเย็น 6 ขั้นตอน (Cold-Chain Packaging) & รับประกันเคลมฟรี 100%
 * 3. 💳 ข้อมูลชำระเงินโอนเงิน (กรุงไทย 038-0-25363-1) & ตรวจสอบสลิปอัตโนมัติ
 * 4. 📦 แจ้งเลขพัสดุและซิงค์บัญชี Google Sheets อัตโนมัติ
 * 5. 🧠 สมองกลทีมงานป้าเข็ม 4 คน AI (Groq Multi-Key Failover)
 */

const LINE_ACCESS_TOKEN = "4FYHfbu8+iE7CaOo+lCEG6pBZuxiOIPXlgKQ3tQSQIxZZOpX63qY/Xp8W+1GGftkB9VXpmb88HtHVmr8BAv5qKmDYgNnaVi322Jj9Bc2g6o3ePUa/R5mX8a+u8HyE7c8g8hLAi20pgHIrnYTV9u9MgdB04t89/1O/w1cDnyilFU=";
const CHANNEL_SECRET = "feab701da4ab774eace8704d7fde1f90";
const ADMIN_LINE_UID = "Uc88eb3896b0e4bcc5fbaa9b78ac1294e";

// Telegram Commander Configurations (แจ้งเตือนลูกค้าทั้งหมดเข้า Telegram ฟรี 100% ไม่กินโควต้า LINE)
const TELEGRAM_BOT_TOKEN = "8939151149:AAGrVkCv0xZrlvtRPO8mzelOYsp5ah5M13U";
const TELEGRAM_CHAT_ID = "6734965582";

// Supabase REST API Configurations
const SUPABASE_URL = "https://usqhvujqmnxqrdoovvnp.supabase.co";
const SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVzcWh2dWpxbW54cXJkb292dm5wIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1NDI5Nzg2MCwiZXhwIjoyMDY5ODczODYwfQ.RXKNfknFfmf86bm1ivri1d7FP0jw0VbUkrb7AXn2Ejo";

// Groq API Keys (หมุนเวียนคีย์อัตโนมัติ)
const GROQ_KEYS = [
  "REDACTED_SECRET",
  "REDACTED_SECRET",
  "REDACTED_SECRET",
  "REDACTED_SECRET",
  "REDACTED_SECRET",
  "REDACTED_SECRET",
  "REDACTED_SECRET",
  "REDACTED_SECRET",
  "REDACTED_SECRET",
  "REDACTED_SECRET"
];

const BOT_NAME = "ป้าเข็ม ปลาสลิดแดดเดียวสุพรรณแท้";

function doPost(e) {
  if (!e || !e.postData || !e.postData.contents) {
    return ContentService.createTextOutput(JSON.stringify({ status: "ok", message: "LINE Ping OK" }))
      .setMimeType(ContentService.MimeType.JSON);
  }
  try {
    const json = JSON.parse(e.postData.contents);
    // 0.1 ตรวจจับ Webhook จาก Facebook Messenger
    if (json.object === "page" && json.entry) {
      handleFacebookMessengerEvents(json);
      return ContentService.createTextOutput("EVENT_RECEIVED");
    }

    // 0.2 ตรวจจับ Webhook จาก Telegram Bot (@pakhem_fish_bot)
    if (json.update_id && (json.message || json.callback_query)) {
      try {
        handleTelegramWebhookUpdate(json);
      } catch (tgErr) {
        Logger.log("Telegram update error: " + tgErr);
      }
      return HtmlService.createHtmlOutput("OK");
    }


    // 0.05 ตรวจสอบรูปสลิปโอนเงินด้วย AI Vision (เรียกจากหน้าเว็บ /fish.html)
    if (json.action === "verify_slip") {
      return handleVerifySlipApi(json);
    }

    // 0.08 แจ้งเลขพัสดุอัตโนมัติกลับไปยังช่องทางที่ลูกค้าสั่ง (LINE OA หรือ Facebook Messenger)
    if (json.action === "notify_tracking") {
      return handleNotifyTrackingApi(json);
    }

    // 0.09 แจ้งเตือนรายการบัญชีจากหน้าเว็บ admin.html เข้า Telegram (@pakhem_fish_bot) + ซิงค์ Google Sheets
    if (json.action === "notify_accounting") {
      try {
        syncSupabaseToGoogleSheet();
      } catch (e) {}
      if (json.message) {
        pushAdminAlert(json.message);
      }
      return ContentService.createTextOutput(JSON.stringify({ status: "ok" }))
        .setMimeType(ContentService.MimeType.JSON);
    }

    // 0. ตรวจจับออเดอร์ปลาแดดเดียวจากหน้าเว็บ Direct Checkout (/fish.html)
    if (json.action === "order_fish" || json.package_code || (json.name && json.phone && json.package)) {
      return handleDirectWebOrder(json);
    }
    const events = json.events || [];

    for (let i = 0; i < events.length; i++) {
      const ev = events[i];
      if (ev.type === "message" && ev.message.type === "text") {
        handleTextMessage(ev);
      } else if (ev.type === "message" && ev.message.type === "image") {
        handleImageMessage(ev);
      } else if (ev.type === "message" && ev.message.type === "location") {
        handleLocationMessage(ev);
      } else if (ev.type === "follow") {
        handleFollowEvent(ev);
      }
    }
    return ContentService.createTextOutput(JSON.stringify({ status: "ok" }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({ error: err.toString() }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}


// Facebook Messenger Configurations & Multi-Agent Router
const FB_PAGE_ACCESS_TOKEN = "REDACTED_SECRET";
const FB_VERIFY_TOKEN = "pakhem_fish_verify_2026";
const COLD_PACK_POSTER_URL = "https://usqhvujqmnxqrdoovvnp.supabase.co/storage/v1/object/public/slips/cold_pack_poster.png";
const COLD_PACK_KEYWORDS = [
  "ต่างจังหวัด", "ตจว", "เสียไหม", "เสียมั้ย", "เสียป่าว", "เสียเปล่า", "จะเสีย",
  "เน่าไหม", "เน่ามั้ย", "เน่าป่าว", "จะเน่า", "บูดไหม", "บูดมั้ย", "จะบูด",
  "ละลายไหม", "ละลายมั้ย", "จะละลาย", "แพ็กยังไง", "แพ็คยังไง", "แพ็กแบบไหน", "แพ็คแบบไหน",
  "เก็บความเย็น", "ซองฟอยล์", "ถุงฟอยล์", "กล่องโฟม",
  "ส่งไกล", "เดินทางไกล", "อากาศร้อน", "ร้อนไหม", "ควบคุมอุณหภูมิ"
];

function getColdPackReplyText() {
  return [
    "📦 เงื่อนไขการจัดส่งและการชำระเงิน",
    "",
    "เพื่อรักษาคุณภาพและความสดใหม่ของปลาสลิด ทางร้านเลือกวิธีจัดส่งให้เหมาะสมกับระยะเวลาขนส่งในแต่ละพื้นที่ ดังนี้ค่ะ",
    "",
    "🚚 แบบที่ 1: พื้นที่จัดส่งถึงภายใน 1–2 วัน",
    "สำหรับกรุงเทพฯ ปริมณฑล และจังหวัดที่สามารถจัดส่งถึงได้ภายใน 1–2 วัน",
    "• จัดส่งสินค้าแช่แข็ง พร้อมบรรจุภัณฑ์ฟอยล์เก็บอุณหภูมิ",
    "• สามารถเลือกชำระเงินปลายทางได้ในพื้นที่ที่ผู้ให้บริการรองรับ",
    "",
    "❄️ แบบที่ 2: พื้นที่จัดส่งใช้เวลา 3–4 วัน",
    "สำหรับจังหวัดที่ใช้ระยะเวลาขนส่งนานกว่า ทางร้านจะจัดส่งด้วยรถควบคุมอุณหภูมิ (รถห้องเย็น) เพื่อช่วยรักษาคุณภาพสินค้าให้เหมาะสมตลอดการขนส่ง",
    "• ขอสงวนสิทธิ์จัดส่งหลังจากได้รับชำระเงินเต็มจำนวนแล้ว",
    "• ไม่สามารถใช้บริการเก็บเงินปลายทางได้ เนื่องจากเป็นรูปแบบการจัดส่งเฉพาะสำหรับพื้นที่ดังกล่าว",
    "",
    "🏦 บัญชีสำหรับโอนชำระเงิน (กรณีโอนเงินส่งฟรี / พื้นที่ที่ไม่มีเก็บเงินปลายทาง)",
    "• ธนาคารกรุงไทย (สาขาท่าพระ) เลขที่บัญชี: 038-0-25363-1 (ชื่อบัญชี: นายจีรวัฒน์ พลอาจ)",
    "",
    "💚 ทางร้านให้ความสำคัญกับคุณภาพสินค้าและความมั่นใจของลูกค้าทุกออเดอร์ ก่อนยืนยันคำสั่งซื้อ ทางร้านจะแจ้งวิธีจัดส่ง ระยะเวลาโดยประมาณ และยอดชำระให้ทราบอย่างชัดเจนค่ะ",
    "ขอบคุณที่ไว้วางใจเลือกซื้อปลาสลิดจากทางร้านนะคะ 🙏",
    "",
    "🔥 แพ็กเกจปลาสลิดแดดเดียวสุพรรณแท้ ป้าเข็ม คัดพิเศษ:",
    "  • ชุดพอดีมื้อ 500 กรัม (ประมาณ 2–3 ตัวใหญ่): โอน 390.- ส่งฟรี! (งดรับ COD)",
    "  • ชุดยอดฮิต 1 กิโลกรัม (ประมาณ 4–6 ตัวใหญ่): โอน 550.- ส่งฟรี! (งดรับ COD)",
    "  • ชุดตุนสุดคุ้ม 2 กิโลกรัม (ประมาณ 8–12 ตัวใหญ่): โอน 1,090.- ส่งฟรีรถห้องเย็น!",
    "",
    "🛒 พิมพ์ชุดที่รับพร้อม ชื่อ-ที่อยู่-เบอร์โทร ในแชทนี้ หรือสั่งผ่านเว็บ https://watt29.github.io/pakhem-shop/ ได้เลยค่ะ 😊"
  ].join("\n");
}

function replyFacebookImage(recipientId, imageUrl) {
  // [DISABLED BY POLICY] ปิดการส่งภาพในแชท Facebook ทุกกรณีตามคำสั่งเจ้าของร้าน
  Logger.log("replyFacebookImage BLOCKED by policy for: " + recipientId);
  return;
  if (!recipientId || !imageUrl) return;
  try {
    var url = "https://graph.facebook.com/v21.0/me/messages?access_token=" + encodeURIComponent(FB_PAGE_ACCESS_TOKEN);
    var payload = {
      recipient: { id: recipientId },
      messaging_type: "RESPONSE",
      message: {
        attachment: {
          type: "image",
          payload: { url: imageUrl, is_reusable: true }
        }
      }
    };
    UrlFetchApp.fetch(url, {
      method: "post",
      contentType: "application/json",
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    });
  } catch (err) {
    Logger.log("Facebook image send error: " + err);
  }
}

function replyFacebook(recipientId, text, quickReplies) {
  try {
    var url = "https://graph.facebook.com/v21.0/me/messages?access_token=" + encodeURIComponent(FB_PAGE_ACCESS_TOKEN);
    var defaultReplies = [
      { content_type: "text", title: "ชุด 500g (390.-)", payload: "QR_PKG_500G" },
      { content_type: "text", title: "ชุด 1 กก. (550.-)", payload: "QR_PKG_1KG" },
      { content_type: "text", title: "ชุด 2 กก. (1,090.-)", payload: "QR_PKG_2KG" }
    ];
    var qrList = (quickReplies !== false) ? ((quickReplies && quickReplies.length) ? quickReplies : defaultReplies) : null;
    if (qrList && qrList.length > 0) {
      var tplButtons = [];
      for (var bi = 0; bi < qrList.length && bi < 3; bi++) {
        if (qrList[bi].title && qrList[bi].payload) {
          tplButtons.push({
            type: "postback",
            title: String(qrList[bi].title).substring(0, 20),
            payload: String(qrList[bi].payload)
          });
        }
      }
      if (tplButtons.length > 0 && text.length <= 600) {
        var tplRes = UrlFetchApp.fetch(url, {
          method: "post",
          contentType: "application/json",
          payload: JSON.stringify({
            recipient: { id: recipientId },
            messaging_type: "RESPONSE",
            message: {
              attachment: {
                type: "template",
                payload: {
                  template_type: "button",
                  text: text,
                  buttons: tplButtons
                }
              },
              quick_replies: qrList
            }
          }),
          muteHttpExceptions: true
        });
        if (tplRes.getResponseCode() === 200) return;
      } else if (tplButtons.length > 0 && text.length > 600) {
        UrlFetchApp.fetch(url, {
          method: "post",
          contentType: "application/json",
          payload: JSON.stringify({
            recipient: { id: recipientId },
            messaging_type: "RESPONSE",
            message: { text: text }
          }),
          muteHttpExceptions: true
        });
        var cardRes = UrlFetchApp.fetch(url, {
          method: "post",
          contentType: "application/json",
          payload: JSON.stringify({
            recipient: { id: recipientId },
            messaging_type: "RESPONSE",
            message: {
              attachment: {
                type: "template",
                payload: {
                  template_type: "button",
                  text: "📦 เลือกชุดสั่งซื้อ (กดปุ่มในกล่องนี้ หรือพิมพ์เลข 1 หรือ 2 ได้เลยค่ะ):",
                  buttons: tplButtons
                }
              },
              quick_replies: qrList
            }
          }),
          muteHttpExceptions: true
        });
        if (cardRes.getResponseCode() === 200) return;
      }
    }
    var messageObj = { text: text };
    if (qrList) {
      messageObj.quick_replies = qrList;
    }
    var payload = {
      recipient: { id: recipientId },
      messaging_type: "RESPONSE",
      message: messageObj
    };
    UrlFetchApp.fetch(url, {
      method: "post",
      contentType: "application/json",
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    });
  } catch (err) {
    Logger.log("Facebook send error: " + err);
  }
}

function handleFacebookMessengerEvents(data) {
  var entries = data.entry || [];
  for (var i = 0; i < entries.length; i++) {
    var entryPageId = String(entries[i].id || "");
    var entryPageLabel = entryPageId === "1323469404180656" ? "เพจ 2: ครัวแม่บ้าน ชี้เป้าของอร่อย" : "เพจ 1: ป้าเข็ม ปลาสลิดแดดเดียวสุพรรณแท้";
    // 0.0 ดักจับคอมเมนต์ใต้โพสต์/แอด Real-time (Feed changes)
    var changes = entries[i].changes || [];
    for (var k = 0; k < changes.length; k++) {
      var ch = changes[k];
      if (ch.field === "feed" && ch.value && ch.value.item === "comment" && ch.value.verb === "add") {
        var commentId = ch.value.comment_id;
        var senderId = ch.value.sender_id || (ch.value.from && ch.value.from.id);
        var senderName = ch.value.sender_name || (ch.value.from && ch.value.from.name) || "ลูกค้า";
        var cMsg = ch.value.message || "";
        handleCommentWebhook(commentId, senderId, senderName, cMsg);
      }
    }
    var messaging = entries[i].messaging || [];
    for (var j = 0; j < messaging.length; j++) {
      var event = messaging[j];
      var senderId = event.sender && event.sender.id;
      if (!senderId || senderId === "1307380735783361" || senderId === "1323469404180656") continue;
      if (event.message && event.message.is_echo) continue;
      if (!event.message && !event.postback) continue;

      // 0.05 หากลูกค้าส่งรูปภาพใน Facebook Messenger
      if (event.message && event.message.attachments && event.message.attachments.length > 0 && !event.message.text) {
        var att = event.message.attachments[0];
        if (att.type === "image" && att.payload && att.payload.url) {
          try {
            var fbImgRes = UrlFetchApp.fetch(att.payload.url, { muteHttpExceptions: true });
            if (fbImgRes.getResponseCode() === 200) {
              var fbBlob = fbImgRes.getBlob();
              var fbVision = analyzeImageWithGroqVision(Utilities.base64Encode(fbBlob.getBytes()), fbBlob.getContentType() || "image/jpeg");
              if (fbVision.is_slip) {
                if (fbVision.receiver_name && !fbVision.receiver_matched) {
                  replyFacebook(senderId,
                    "⚠️ [ทีมงานร้านปลาสลิดป้าเข็ม สุพรรณบุรีแท้ - แจ้งเตือนบัญชีผู้รับไม่ตรงค่ะ]\n" +
                    "สลิปที่ส่งมามีชื่อผู้รับคือ '" + fbVision.receiver_name + "' ซึ่งไม่ตรงกับบัญชีของทางร้านนะคะ\n\n" +
                    "🏦 บัญชีร้านที่ถูกต้อง: ธนาคารกรุงไทย 038-0-25363-1 (นายจีรวัฒน์ พลอาจ) ค่ะ 🙏");
                } else if (fbVision.amount < 390) {
                  var fbDiff = Math.round((390 - fbVision.amount) * 100) / 100;
                  replyFacebook(senderId,
                    "⚠️ [ทีมงานร้านปลาสลิดป้าเข็ม สุพรรณบุรีแท้ - ยอดโอนเงินไม่ครบตามราคาสินค้าค่ะ]\n" +
                    "• 💵 ยอดในสลิปที่ตรวจพบ: " + fbVision.amount.toLocaleString("th-TH") + " บาท\n" +
                    "• 📦 ราคาสินค้าขั้นต่ำ: ชุด 500 กรัม 390 บาท (ส่งฟรี!) / ชุด 1 กก. 550 บาท (ส่งฟรี!) / ชุด 2 กก. 1,090 บาท (ส่งฟรีรถเย็น)\n" +
                    "• ❗ ยอดเงินยังขาดอยู่อีกอย่างน้อย: " + fbDiff.toLocaleString("th-TH") + " บาทค่ะ\n\n" +
                    "⏸️ รบกวนคุณลูกค้าโอนยอดส่วนต่างเพิ่มเติมเข้า ธ.กรุงไทย 038-0-25363-1 (นายจีรวัฒน์ พลอาจ) แล้วส่งสลิปเพิ่มเข้ามาได้เลยนะคะ 🙏💕");
                  pushAdminAlert(
                    "🚨 [เตือนด่วน: ลูกค้าเพจโอนเงินไม่ครบ! โอนมาแค่ " + fbVision.amount.toLocaleString("th-TH") + " บาท]\n" +
                    "━━━━━━━━━━━━━━━━━━\n" +
                    "👤 Facebook ID: " + senderId + "\n" +
                    "💵 ยอดในสลิป: " + fbVision.amount.toLocaleString("th-TH") + " บาท (ขาด " + fbDiff.toLocaleString("th-TH") + " บ.)\n" +
                    "🖼️ รูปสลิป: " + att.payload.url
                  );
                } else {
                  replyFacebook(senderId,
                    "✅ [ทีมงานร้านปลาสลิดป้าเข็ม สุพรรณบุรีแท้]\n" +
                    "ได้รับสลิปโอนเงินจำนวน " + fbVision.amount.toLocaleString("th-TH") + " บาท เรียบร้อยแล้วค่ะ 🙏💕\n" +
                    (fbVision.trans_date ? "⏰ เวลาโอน: " + fbVision.trans_date + "\n" : "") +
                    (fbVision.ref_no ? "🔢 เลขอ้างอิง: " + fbVision.ref_no + "\n" : "") +
                    "━━━━━━━━━━━━━━━━━━\n" +
                    "หากยังไม่ได้แจ้งชื่อ ที่อยู่ และเบอร์โทรศัพท์ รบกวนพิมพ์แจ้งในแชทนี้ได้เลยนะคะ ทางร้านจะรีบลงคิวแพ็กส่งด่วนให้ทันทีค่ะ 😊");
                  pushAdminAlert(
                    "💰 [สลิปโอนเงินถูกต้องผ่าน Facebook Messenger] 🔔\n" +
                    "━━━━━━━━━━━━━━━━━━\n" +
                    "👤 Facebook ID: " + senderId + "\n" +
                    "💵 ยอดเงิน: " + fbVision.amount.toLocaleString("th-TH") + " บาท\n" +
                    (fbVision.trans_date ? "⏰ เวลาโอน: " + fbVision.trans_date + "\n" : "") +
                    (fbVision.ref_no ? "🔢 เลขอ้างอิง: " + fbVision.ref_no + "\n" : "") +
                    "🖼️ รูปสลิป: " + att.payload.url
                  );
                }
              } else {
                replyFacebook(senderId,
                  "📸 ได้รับรูปภาพของคุณลูกค้าเรียบร้อยแล้วค่ะ\n" +
                  "(🔍 ระบบตรวจพบเป็น: " + (fbVision.description || "รูปภาพทั่วไป") + " — ไม่ใช่สลิปโอนเงินธนาคารนะคะ 😊)\n\n" +
                  "• หากต้องการสั่งซื้อปลาสลิดแดดเดียว พิมพ์ ชื่อ-ที่อยู่-เบอร์โทร ในแชทนี้ได้เลยค่ะ\n" +
                  "• หากต้องการสอบถามเพิ่มเติม สามารถพิมพ์ข้อความสอบถามในแชทนี้ได้ตลอด 24 ชม. เลยนะคะ แอดมินดูแลเต็มที่ค่ะ 🙏💕");
              }
            }
          } catch (fbImgErr) {
            Logger.log("FB image check error: " + fbImgErr);
          }
        }
        continue;
      }

      var rawText = (event.message && event.message.text) || (event.postback && (event.postback.title || event.postback.payload)) || "";
      var qrPayload = (event.message && event.message.quick_reply && event.message.quick_reply.payload) || (event.postback && event.postback.payload) || "";
      if (!rawText && !qrPayload) continue;

      var text = rawText.trim();
      var lowerText = text.toLowerCase();
      var nowStr = Utilities.formatDate(new Date(), "Asia/Bangkok", "dd/MM/yyyy HH:mm:ss");
      recordLeadActivity(senderId, false);

      var fbCtxKey = "FB_" + senderId;
      var fbCtx = getUserOrderContext(fbCtxKey);

      // 0. ลูกค้ากดปุ่มเลือกแพ็กเกจ (Quick Reply)
      if (qrPayload === "QR_COD_500G" || qrPayload === "QR_COD_1KG") {
        replyFacebook(senderId,
          "🐟 ขออนุญาตเรียนแจ้งคุณลูกค้าตามตรงนะคะ ทางร้านงดรับเก็บเงินปลายทาง (COD) ทุกชุด 100% ค่ะ 🙏❄️\n" +
          "เนื่องจากปลาสลิดเป็นอาหารสดแช่แข็ง ≤ -18°C ทางร้านจึงจัดส่งหลังได้รับการชำระเงินโอนเต็มจำนวน เพื่อการันตีความสดใหม่และป้องกันสินค้าตกค้างเสียหายค่ะ (โอนเงินจัดส่งฟรีถึงหน้าบ้านทุกชุดเลยจ้า! 🚚)\n\n" +
          "📦 โปรโมชั่นโอนเงินส่งฟรี:\n" +
          "• ชุดพอดีมื้อ 500g (2–3 ตัวใหญ่) = โอน 390.- ส่งฟรี!\n" +
          "• ชุดขายดี 1 กิโลกรัม (4–6 ตัวใหญ่) = โอน 550.- ส่งฟรี! ⭐\n" +
          "• ชุดตุนสุดคุ้ม 2 กิโลกรัม (8–12 ตัวใหญ่) = โอน 1,090.- (ส่งฟรีรถห้องเย็น!)\n\n" +
          "🏦 ธ.กรุงไทย: 038-0-25363-1 (นายจีรวัฒน์ พลอาจ)\n" +
          "👉 รับชุดไหน พิมพ์เลข 1, 2 หรือ 3 ในแชทนี้ได้เลยนะคะ 😊", false);
        continue;
      }
      if (qrPayload === "QR_PKG_500G" || qrPayload === "ORDER_PKG_500G") {
        saveUserOrderContext(fbCtxKey, { packageCode: "SKU-SLID-MD-500G" });
        replyFacebook(senderId,
          "✅ รับชุดพอดีมื้อ 500 กรัม (ประมาณ 2–3 ตัวใหญ่) ค่ะ 🐟✨\n" +
          
          "• 🏦 โอนเงินส่งฟรี: 390 บาท (ธ.กรุงไทย 038-0-25363-1 นายจีรวัฒน์ พลอาจ)\n\n" +
          "👉 รบกวนพิมพ์ 'ชื่อ - ที่อยู่ (ต./อ./จ.) - เบอร์โทร 10 หลัก' แจ้งในแชทนี้ได้เลยนะคะ (หากโอนเงิน ส่งรูปสลิปแนบมาได้เลยค่ะ) 😊",
          [
            { content_type: "text", title: "รับชุด 1กก. (4ตัวจัมโบ้)", payload: "QR_PKG_1KG" },
            { content_type: "text", title: "ชุด 2 กก. (1,090.-)", payload: "QR_PKG_2KG" }
          ]);
        continue;
      }
      if (qrPayload === "QR_PKG_1KG" || qrPayload === "ORDER_PKG_1KG") {
        saveUserOrderContext(fbCtxKey, { packageCode: "SKU-SLID-MD-1KG" });
        replyFacebook(senderId,
          "✅ รับชุดขายดี 1 กิโลกรัม (ประมาณ 4–6 ตัวใหญ่) ค่ะ ⭐🐟\n" +
          
          "• 🏦 โอนเงินส่งฟรี: 550 บาท (ธ.กรุงไทย 038-0-25363-1 นายจีรวัฒน์ พลอาจ)\n\n" +
          "👉 รบกวนพิมพ์ 'ชื่อ - ที่อยู่ (ต./อ./จ.) - เบอร์โทร 10 หลัก' แจ้งในแชทนี้ได้เลยนะคะ (หากโอนเงิน ส่งรูปสลิปแนบมาได้เลยค่ะ) 😊",
          [
            { content_type: "text", title: "รับชุด 500g (2ตัวจัมโบ้)", payload: "QR_PKG_500G" },
            { content_type: "text", title: "ชุด 2 กก. (1,090.-)", payload: "QR_PKG_2KG" }
          ]);
        continue;
      }
      if (qrPayload === "QR_PKG_2KG" || qrPayload === "ORDER_PKG_2KG") {
        saveUserOrderContext(fbCtxKey, { packageCode: "SKU-SLID-MD-2KG", payMode: "TRANSFER" });
        replyFacebook(senderId,
          "✅ รับชุดตุนสุดคุ้ม 2 กิโลกรัม (ประมาณ 8–12 ตัวใหญ่) ยอดโอน 1,090 บาท ส่งฟรีรถห้องเย็นควบคุมอุณหภูมิค่ะ ❄️🚚 (ชุด 2 กก. รับเฉพาะโอนเงินค่ะ)\n\n" +
          "🏦 ธ.กรุงไทย: 038-0-25363-1 (นายจีรวัฒน์ พลอาจ)\n\n" +
          "👉 โอนแล้วส่งรูปสลิป พร้อมพิมพ์ 'ชื่อ - ที่อยู่ (ต./อ./จ.) - เบอร์โทร 10 หลัก' ในแชทนี้ได้เลยนะคะ 😊", false);
        continue;
      }

      // 0.5 กรณีลูกค้ากดปุ่มเลือกตำบล หรือพิมพ์ชื่อตำบลตามหลัง
      if (fbCtx.savedAddress && !hasCompleteThaiAddress(fbCtx.savedAddress)) {
        var fbZipM = String(fbCtx.savedAddress).match(/\b([1-9]\d{4})\b/);
        var fbZipInfo = fbZipM ? lookupThaiZipCodeInfo(fbZipM[1]) : null;
        var pickedTambon = "";
        var tPrefMatch = text.match(/^(?:ต\.|ตำบล|แขวง)\s*([ก-๙A-Za-z0-9]+)/);
        if (tPrefMatch && tPrefMatch[1]) {
          pickedTambon = tPrefMatch[1].trim();
        } else if (fbZipInfo && fbZipInfo.tambons) {
          for (var fti = 0; fti < fbZipInfo.tambons.length; fti++) {
            var candT = fbZipInfo.tambons[fti];
            if (text === candT || text.indexOf(candT) !== -1) {
              pickedTambon = candT;
              break;
            }
          }
        }
        if (pickedTambon) {
          var mergedFbAddr = enrichThaiAddressWithMaps(insertTambonIntoAddress(fbCtx.savedAddress, pickedTambon));
          saveUserOrderContext(fbCtxKey, { savedAddress: mergedFbAddr, waitingTambon: false });
          fbCtx = getUserOrderContext(fbCtxKey);
          text = mergedFbAddr + (fbCtx.savedPhone ? " โทร " + fbCtx.savedPhone : "");
        }
      }

      // 1. ตรวจจับที่อยู่ & สั่งซื้ออัตโนมัติ (Zero-Touch Direct Order - ต้องครบ บ้านเลขที่ + ต./อ./จ. + เบอร์ 10 หลัก 100%)
      var orderDetails = extractOrderDetails(text, fbCtxKey);
      if (orderDetails) {
        var orderCode = "PKF-" + Utilities.formatDate(new Date(), "Asia/Bangkok", "MMddHHmmss");
        var finalFbAddr = orderDetails.fullText || enrichThaiAddressWithMaps(text);
        var supaPayload = {
          order_code: orderCode,
          product_name: "ปลาสลิดแดดเดียว ไซส์จัมโบ้ 4 ตัวโล คัดพิเศษ ป้าเข็ม คัดพิเศษ",
          package_code: orderDetails.packageCode || "SKU-SLID-MD-1KG",
          package_name: orderDetails.package,
          price: orderDetails.price,
          customer_name: orderDetails.recipientName || ("ลูกค้า Facebook (" + senderId.substring(0, 6) + ")"),
          phone: orderDetails.phone,
          address: finalFbAddr,
          payment_method: orderDetails.paymentMethod,
          status: "PENDING",
          note: "สั่งซื้อผ่าน Facebook (" + entryPageLabel + ") [FB_ID:" + senderId + "]",
          created_at: new Date().toISOString()
        };

        try {
          UrlFetchApp.fetch(SUPABASE_URL + "/rest/v1/direct_orders", {
            method: "post",
            headers: {
              "apikey": SUPABASE_KEY,
              "Authorization": "Bearer " + SUPABASE_KEY,
              "Content-Type": "application/json",
              "Prefer": "return=minimal"
            },
            payload: JSON.stringify(supaPayload),
            muteHttpExceptions: true
          });
        } catch (e) {
          Logger.log("Supabase insert FB order error: " + e);
        }
        saveUserOrderContext(fbCtxKey, { savedAddress: null, savedPhone: null, savedName: null, waitingTambon: false });

        var fbConfirm = 
          "📝 [ทีมงานร้านปลาสลิดป้าเข็ม สุพรรณบุรีแท้]\n" +
          "ขอบพระคุณสำหรับคำสั่งซื้อค่ะคุณลูกค้า 🙏💕\n" +
          "ระบบได้บันทึกออเดอร์และส่งต่อฝ่ายจัดส่งเรียบร้อยแล้วค่ะ ✨\n" +
          "━━━━━━━━━━━━━━━━━━\n" +
          "🔖 รหัสคำสั่งซื้อ: " + orderCode + "\n" +
          "📦 แพ็กเกจ: " + orderDetails.package + "\n" +
          "💰 ยอดรวม: " + orderDetails.price + " บาท\n" +
          "💳 วิธีชำระ: " + orderDetails.paymentMethod + "\n" +
          "📞 เบอร์โทร: " + orderDetails.phone + "\n" +
          "🏠 ที่อยู่จัดส่ง: " + finalFbAddr + "\n" +
          "━━━━━━━━━━━━━━━━━━\n" +
          "🚚 ทางร้านจะจัดส่งออกจากร้านภายใน 1–2 วัน (ปลาสดใหม่ ซีลสูญญากาศ แช่แข็งและแพ็กฟอยล์เก็บความเย็นอย่างดี) รอรับความสดอร่อยที่บ้านได้เลยนะคะ 😊\n\n" +
          "🛒 หน้าร้านออนไลน์: https://watt29.github.io/pakhem-shop/fish.html";
        replyFacebook(senderId, fbConfirm);
        recordLeadActivity(senderId, true);

        pushAdminAlert(
          "🐟 [ออเดอร์ใหม่จาก Facebook Messenger] 🔔\n" +
          "━━━━━━━━━━━━━━━━━━\n" +
          "🏠 เพจ: " + entryPageLabel + "\n" +
          "🔖 รหัส: " + orderCode + "\n" +
          "👤 Facebook ID: " + senderId + "\n" +
          "📞 โทร: " + orderDetails.phone + "\n" +
          "📦 สินค้า: " + orderDetails.package + "\n" +
          "💰 ยอดเก็บเงิน: " + orderDetails.price + " บาท (" + orderDetails.paymentMethod + ")\n" +
          "📍 ที่อยู่:\n" + finalFbAddr + "\n" +
          "⏰ เวลา: " + nowStr
        );
        continue;
      }

      // 1.2 กรณีลูกค้าส่งที่อยู่หรือเบอร์โทรมา แต่ข้อมูลยังไม่ครบ (ขาด ตำบล/อำเภอ/จังหวัด หรือเบอร์โทรไม่ครบ 10 หลัก)
      var updatedFbCtx = getUserOrderContext(fbCtxKey);
      var rawDigitsFb = text.replace(/[^\d]/g, "");
      var textForAddrFb = text.replace(/ต่างจังหวัด|(?:ตำบล|อำเภอ|จังหวัด|เขต|แขวง|ถนน|ซอย)\s*(?:ไหน|อะไร|ใด)/g, "");
      var isInquiryFb = ["ไหม", "มั้ย", "ป่าว", "เปล่า", "เหรอ", "หรือคะ", "ทำไม", "ยังไง", "อย่างไร", "เท่าไหร่", "กี่วัน", "กี่ตัว", "ที่ไหน", "จังหวัดไหน", "อำเภอไหน", "อะไร", "?"].some(function(q) { return lowerText.indexOf(q) !== -1; });
      var isBtnChoiceFb = Boolean(qrPayload) || /390/.test(text); var hasAddrAttemptFb = !isBtnChoiceFb && /(?:บ้านเลขที่|ต\.|อ\.|จ\.|ตำบล|อำเภอ|จังหวัด|แขวง|เขต|กทม|กรุงเทพ|ถนน|ถ\.|ซอย|ซ\.|ม\.|หมู่ที่|หมู่|\b[1-9]\d{4}\b|\d+\/\d+)/.test(textForAddrFb) && !isInquiryFb;
      var hasInvalidPhoneAttempt = /0\d{6,12}/.test(rawDigitsFb) && !validateThaiPhoneNumber(rawDigitsFb.match(/0\d{6,12}/)[0]).valid;
      if (hasAddrAttemptFb || hasInvalidPhoneAttempt || (updatedFbCtx.savedAddress && !hasCompleteThaiAddress(updatedFbCtx.savedAddress))) {
        var checkAddr = enrichThaiAddressWithMaps(updatedFbCtx.savedAddress || (hasAddrAttemptFb ? text : ""));
        var checkPhone = updatedFbCtx.savedPhone || "";
        var phoneCandM = text.match(/0[2689]\d[\d\s-]{5,12}/);
        if (phoneCandM) {
          var pClean = phoneCandM[0].replace(/[^\d]/g, "");
          if (validateThaiPhoneNumber(pClean).valid) checkPhone = pClean;
        }
        if (checkAddr || checkPhone) {
          saveUserOrderContext(fbCtxKey, { savedAddress: checkAddr, savedPhone: checkPhone, waitingTambon: !hasCompleteThaiAddress(checkAddr) });
        }
        var missingParts = [];
        var fbQuickTambons = [];
        var zipMFb = String(checkAddr).match(/\b([1-9]\d{4})\b/);
        var zipInfoFb = zipMFb ? lookupThaiZipCodeInfo(zipMFb[1]) : null;
        if (!checkAddr || !hasCompleteThaiAddress(checkAddr)) {
          if (zipInfoFb && zipInfoFb.tambons && zipInfoFb.tambons.length > 0 && !/(?:ต\.|ตำบล|แขวง)/.test(checkAddr)) {
            missingParts.push("📌 ขาด **ตำบล/แขวง** (รหัส " + zipMFb[1] + " " + (zipInfoFb.isBkk ? "เขต" : "อ.") + zipInfoFb.amphoe + " จ." + zipInfoFb.province + " มีตำบลดังนี้ค่ะ: " + zipInfoFb.tambons.map(function(t) { return (zipInfoFb.isBkk ? "แขวง" : "ต.") + t; }).join(", ") + ")");
            for (var qti = 0; qti < zipInfoFb.tambons.length && qti < 10; qti++) {
              var tLabel = (zipInfoFb.isBkk ? "แขวง" : "ต.") + zipInfoFb.tambons[qti];
              fbQuickTambons.push({ content_type: "text", title: tLabel.substring(0, 20), payload: tLabel });
            }
          } else {
            missingParts.push("📌 ขาด **ตำบล/อำเภอ/จังหวัด** หรือ **รหัสไปรษณีย์ 5 หลัก**");
          }
        }
        if (!checkPhone || !validateThaiPhoneNumber(checkPhone).valid) {
          var pReas = phoneCandM ? validateThaiPhoneNumber(phoneCandM[0]).reason : "ยังไม่ได้ระบุเบอร์โทรศัพท์ 10 หลัก";
          missingParts.push("📞 เบอร์โทรศัพท์: **" + pReas + "** (ต้องเป็นเบอร์จริง 10 หลัก เช่น 089-xxx-xxxx)");
        }
        if (missingParts.length > 0) {
          var askCompleteMsg =
            "📋 ป้าเข็มบันทึกข้อมูลเบื้องต้นไว้ให้แล้วจ้ะ:\n" +
            (checkAddr ? "🏠 ที่อยู่: " + checkAddr + "\n" : "") +
            (checkPhone ? "📞 เบอร์โทร: " + checkPhone + "\n" : "") +
            "━━━━━━━━━━━━━━━━━━\n" +
            "⚠️ เพื่อให้ขนส่งจัดส่งถึงหน้าบ้านไม่ตีกลับ รบกวนแจ้งเพิ่มอีกนิดเดียวนะจ๊ะ:\n" +
            missingParts.join("\n") + "\n\n" +
            (fbQuickTambons.length > 0 ? "👇 กดเลือกปุ่มตำบลด้านล่าง หรือพิมพ์แจ้งในแชทได้เลยจ้า" : "👇 พิมพ์ข้อมูลที่ขาดส่งมาในแชทนี้ได้เลยจ้า");
          replyFacebook(senderId, askCompleteMsg, fbQuickTambons.length > 0 ? fbQuickTambons : false);
          continue;
        }
      }

      // 1.5 ลูกค้าทิ้งเบอร์โทรศัพท์ให้ติดต่อกลับ (ไม่มีที่อยู่จัดส่ง)
      var phoneOnly = extractPhoneOnly(text);
      if (phoneOnly) {
        var phoneAckMsg = 
          "🐟 [ทีมงานร้านปลาสลิดป้าเข็ม สุพรรณบุรีแท้] 🙏✨\n" +
          "ขอบพระคุณสำหรับเบอร์โทรติดต่อ (" + phoneOnly + ") นะคะ\n\n" +
          "ทางร้านขออนุญาตเรียนแจ้งว่า ทางร้านรับเรื่องและรับออเดอร์ผ่านแชทข้อความนี้เท่านั้นนะคะ (ไม่มีบริการโทรสั่งซื้อหรือโทรกลับ เพื่อป้องกันการจดที่อยู่และข้อมูลตกหล่นค่ะ) 😊\n" +
          "━━━━━━━━━━━━━━━━━━\n" +
          "👉 คุณลูกค้าต้องการสอบถามเรื่องใด หรือสนใจรับปลาสลิดชุดไหน สามารถพิมพ์แจ้งในแชทนี้ได้เลยนะคะ เดี๋ยวแอดมินดูแลให้ทันทีค่ะ 💕";
        replyFacebook(senderId, phoneAckMsg, false);
        continue;
      }

      // 1.9 ตรวจจับคลังคำถาม-คำตอบมาตรฐาน 20 หมวด (ตรงกับไฟล์ data/fish_faq_rules.csv) เป็นอันดับแรก!
      var isShortPkgGas = ["1", "2", "3", "ชุด1", "ชุด 1", "ชุด2", "ชุด 2", "ชุด3", "ชุด 3", "รับชุด 1", "รับชุด 2", "รับชุด 3"].indexOf(lowerText) !== -1;
      var hasQuestionGas = ["ไหม", "มั้ย", "ป่าว", "เปล่า", "เหรอ", "หรือ", "ทำไม", "ยังไง", "อย่างไร", "เท่าไหร่", "กี่", "ไหน", "อะไร", "ไม่มี", "ไม่ได้", "?"].some(function(q) { return lowerText.indexOf(q) !== -1; });
      var hasExplicitVerbGas = ["รับชุด", "เอาชุด", "สั่งชุด", "รับ 1", "เอา 1", "สั่ง 1", "รับ 500", "เอา 500", "สั่ง 500", "รับ 2", "เอา 2", "สั่ง 2", "สั่งแบบเก็บเงินปลายทาง"].some(function(v) { return lowerText.indexOf(v) !== -1; });
      if (!qrPayload && !isShortPkgGas && (hasQuestionGas || !hasExplicitVerbGas)) {
        var earlyFaqMsg = matchMasterFishFaqGas(text, "");
        if (earlyFaqMsg) {
          var isPostponeEarly = earlyFaqMsg.indexOf("แชทนี้บันทึกไว้ให้แล้ว") !== -1;
          if (isPostponeEarly) {
            recordLeadActivity(senderId, true);
            replyFacebook(senderId, earlyFaqMsg, false);
          } else {
            replyFacebook(senderId, earlyFaqMsg);
          }
          continue;
        }
      }

      // 2. ขอคุยกับเจ้าหน้าที่ / ขอเบอร์โทร / ติดต่อคน (โดยยังไม่ได้ทิ้งเบอร์)
      var humanKeywords = ["ติดต่อคน", "ขอคุยกับคน", "ขอมนุษย์", "พนักงานคนจริง", "แอดมินคน", "ไม่เอาบอท", "คุยไม่รู้เรื่อง", "คนจริง", "โทรหา", "ขอเบอร์โทร", "คุยกับคน", "ติดต่อเจ้าหน้าที่", "ขอคุยกับเจ้าหน้าที่", "มีเบอร์ไหม", "ขอเบอร์", "โทรมาหน่อย"];
      if (qrPayload === "TALK_ADMIN" || humanKeywords.some(function(k) { return lowerText.indexOf(k) !== -1; })) {
        var humanMsg = 
          "🐟 [ทีมงานร้านปลาสลิดป้าเข็ม สุพรรณบุรีแท้] 🙏✨\n" +
          "แอดมินยินดีให้บริการและตอบคำถามผ่านแชทนี้โดยตรงเลยค่ะคุณลูกค้า (ทางร้านรับเรื่องทางแชทเท่านั้น ไม่มีบริการโทรกลับ เพื่อความถูกต้องของข้อมูลและที่อยู่จัดส่งค่ะ) 😊\n" +
          "━━━━━━━━━━━━━━━━━━\n" +
          "👉 คุณลูกค้ามีข้อสงสัยเรื่องใด หรือสนใจรับปลาสลิดแดดเดียวชุดไหน พิมพ์แจ้งแอดมินในแชทนี้ได้เลยนะคะ ยินดีดูแลเต็มที่ค่ะ 💕";
        replyFacebook(senderId, humanMsg, false);
        continue;
      }

      // 2.5 ส่งต่างจังหวัดปลาจะเสียไหม? / มาตรฐานแพ็กเย็น 6 ขั้นตอน & รับประกันเคลมฟรี 100%
      if (COLD_PACK_KEYWORDS.some(function(k) { return lowerText.indexOf(k) !== -1; })) {
        replyFacebookImage(senderId, COLD_PACK_POSTER_URL);
        replyFacebook(senderId, getColdPackReplyText());
        continue;
      }

      // 2.55 ปุ่มแอดใน Messenger: ถาม "กี่ตัวโล" / "ตัวละเท่าไหร่", เลือกชุด "500g" / "1 กก." / "2 กก.", หรือกด "สั่งแบบเก็บเงินปลายทาง (COD)"
      var codBtnKeywords = ["สั่งแบบเก็บเงินปลายทาง", "เก็บเงินปลายทาง", "เก็บปลายทาง", "ปลายทาง", "cod"];
      var pkg500Units = ["รับชุดพอดีมื้อ", "ชุดพอดีมื้อ", "500g", "500 กรัม", "500กรัม", "ครึ่งโล", "ครึ่งกิโล", "2-3 ตัว", "2-3ตัว", "3-4 ตัว", "3-4ตัว", "410"];
      var pkg1kgUnits = ["รับชุดขายดี", "ชุดขายดี", "1 กก", "1กก", "1kg", "1 กิโล", "1กิโล", "หนึ่งกิโล", "โลนึง", "1 โล", "1โล", "4-6 ตัว", "4-6ตัว", "5-7 ตัว", "5-7ตัว", "570"];
      var isCodText = codBtnKeywords.some(function(k) { return lowerText.indexOf(k) !== -1; });
      var has500Unit = pkg500Units.some(function(k) { return lowerText.indexOf(k) !== -1; });
      var has1kgUnit = pkg1kgUnits.some(function(k) { return lowerText.indexOf(k) !== -1; });
      var is500Text = has500Unit || (!has1kgUnit && (lowerText === "1" || lowerText === "ชุด1" || lowerText === "ชุด 1" || lowerText.indexOf("ชุด 1") !== -1 || lowerText.indexOf("ชุด1") !== -1));
      var is1kgText = has1kgUnit || (!has500Unit && (lowerText === "2" || lowerText === "ชุด2" || lowerText === "ชุด 2" || lowerText.indexOf("ชุด 2") !== -1 || lowerText.indexOf("ชุด2") !== -1));

      if (isCodText) {
        replyFacebook(senderId,
          "🐟 ขออนุญาตเรียนแจ้งคุณลูกค้าตามตรงนะคะ ทางร้านงดรับเก็บเงินปลายทาง (COD) ทุกชุด 100% ค่ะ 🙏❄️\n" +
          "เนื่องจากปลาสลิดเป็นอาหารสดแช่แข็ง ≤ -18°C ทางร้านจึงจัดส่งหลังได้รับการชำระเงินโอนเต็มจำนวน เพื่อการันตีความสดใหม่และป้องกันสินค้าตกค้างเสียหายค่ะ (โอนเงินจัดส่งฟรีถึงหน้าบ้านทุกชุดเลยจ้า! 🚚)\n\n" +
          "📦 โปรโมชั่นโอนเงินส่งฟรี:\n" +
          "• พิมพ์ 1 : ชุด 500 กรัม (ประมาณ 2–3 ตัวใหญ่) = โอน 390.- ส่งฟรี!\n" +
          "• พิมพ์ 2 : ชุดขายดี 1 กิโลกรัม (ประมาณ 4–6 ตัวใหญ่) = โอน 550.- ส่งฟรี! ⭐\n" +
          "• พิมพ์ 3 : ชุดคุ้ม 2 กิโลกรัม (ประมาณ 8–12 ตัวใหญ่) = โอน 1,090.- ส่งฟรีรถห้องเย็น!\n\n" +
          "🏦 ธ.กรุงไทย: 038-0-25363-1 (นายจีรวัฒน์ พลอาจ)\n" +
          "👉 รับชุดไหน พิมพ์เลข 1, 2 หรือ 3 ในแชทนี้ได้เลยนะคะ 😊", false);
        continue;
      }

      var originInboxKeywords = ["บางบ่อ", "สุพรรณ", "ที่ไหน", "จังหวัดไหน", "ส่งจากไหน", "แหล่งไหน", "บ่อไหน", "ปลาธรรมชาติ", "ปลาเลี้ยง", "แหล่งธรรมชาติ", "มาจากธรรมชาติ"];
      if (originInboxKeywords.some(function(k) { return lowerText.indexOf(k) !== -1; })) {
        replyFacebook(senderId,
          "🐟 ขออนุญาตเรียนแจ้งตามตรงเลยค่ะ ของร้านป้าเข็มเป็น \"ปลาสลิดสุพรรณบุรีแท้ 100% คัดพิเศษไซส์จัมโบ้ (ไซส์จัมโบ้คัดพิเศษ 4–6 ตัวโล คัดพิเศษ)\" ค่ะ (ไม่ใช่บางบ่อจ้า)\n" +
          "✅ ตัวปลามาจากแหล่งน้ำธรรมชาติแท้ 100% (ไม่ใช่ปลาเลี้ยงหัวอาหาร) ล้างทำความสะอาดอย่างดี ไร้กลิ่นสาบโคลน 100% เนื้อแน่นหนาฟู มันแทรก หมักเกลือสมุทรธรรมชาติเค็มน้อยเพียง 3% อร่อยไม่แพ้บางบ่อเลยค่ะ 😋🍚 (แพ็กส่งตรงจาก อ.บางปะหัน จ.พระนครศรีอยุธยา ค่ะ)\n\n" +
          "📦 โปรโมชั่นส่งตรงถึงบ้าน:\n" +
          "• พิมพ์ 1 : ชุด 500 กรัม (ประมาณ 2–3 ตัวใหญ่) = โอน 390.- ส่งฟรี (งดรับ COD)\n" +
          "• พิมพ์ 2 : ชุดขายดี 1 กิโลกรัม (ประมาณ 4–6 ตัวใหญ่) = โอน 550.- ส่งฟรี (งดรับ COD) ⭐\n" +
          "• พิมพ์ 3 : ชุดคุ้ม 2 กิโลกรัม (ประมาณ 8–12 ตัวใหญ่) = โอน 1,090.- ส่งฟรีรถห้องเย็น!\n\n" +
          "👉 รับชุดไหน พิมพ์เลข 1, 2 หรือ 3 (หรือแจ้ง ชื่อ - ที่อยู่ - เบอร์โทร) ในแชทนี้ได้เลยนะคะ 😊");
        continue;
      }

      var sizeKeywords = ["กี่ตัว", "โลละกี่ตัว", "ตัวละ", "ราคาตัวละ", "ขายเป็นตัว", "แยกตัว", "ตัวใหญ่ไหม", "ตัวใหญ่มั้ย", "ไซส์ไหน", "ขนาดไหน"];
      if (sizeKeywords.some(function(k) { return lowerText.indexOf(k) !== -1; })) {
        replyFacebook(senderId,
          "🐟 ปลาสลิดแดดเดียวสุพรรณแท้ ป้าเข็ม คัดไซส์ใหญ่พิเศษ ไซส์จัมโบ้คัดพิเศษ 4–6 ตัวโล คัดพิเศษค่ะ 🐟✨ (จำหน่ายเป็นแพ็กซีลสูญญากาศ ตัวใหญ่เนื้อหนาฟู เค็มน้อย 3%)\n\n" +
          "• พิมพ์ 1 : ชุด 450–500 กรัม (ประมาณ 2–3 ตัวใหญ่) = โอน 390.- ส่งฟรี (งดรับ COD)\n" +
          "• พิมพ์ 2 : ชุดขายดี 900–1,000 กรัม (ประมาณ 4–6 ตัวใหญ่) = โอน 550.- ส่งฟรี (งดรับ COD) ⭐\n" +
          "• พิมพ์ 3 : ชุดคุ้ม 1.8–2.0 กิโลกรัม (ประมาณ 8–12 ตัวใหญ่) = โอน 1,090.- ส่งฟรีรถห้องเย็น!\n\n" +
          "👉 รับชุดไหน พิมพ์เลข 1, 2 หรือ 3 (หรือแจ้ง ชื่อ - ที่อยู่ - เบอร์โทร) ในแชทนี้ได้เลยนะคะ 😊");
        continue;
      }

      if (is500Text) {
        replyFacebook(senderId,
          "✅ รับชุดพอดีมื้อ 450–500 กรัม (ประมาณ 2–3 ตัวใหญ่) ค่ะ 🐟✨\n" +
          
          "• 🏦 โอนเงินส่งฟรี: 390 บาท (ธ.กรุงไทย 038-0-25363-1 นายจีรวัฒน์ พลอาจ)\n\n" +
          "👉 รบกวนพิมพ์ 'ชื่อ - ที่อยู่ - เบอร์โทรศัพท์' แจ้งในแชทนี้ได้เลยนะคะ (หากโอนเงิน ส่งรูปสลิปแนบมาได้เลยค่ะ) 😊",
          [
            { content_type: "text", title: "รับชุด 1กก. (4ตัวจัมโบ้)", payload: "QR_PKG_1KG" },
            { content_type: "text", title: "ชุด 2 กก. (1,090.-)", payload: "QR_PKG_2KG" }
          ]);
        continue;
      }

      if (is1kgText) {
        replyFacebook(senderId,
          "✅ รับชุดขายดี 900–1,000 กรัม (ประมาณ 4–6 ตัวใหญ่) ค่ะ ⭐🐟\n" +
          
          "• 🏦 โอนเงินส่งฟรี: 550 บาท (ธ.กรุงไทย 038-0-25363-1 นายจีรวัฒน์ พลอาจ)\n\n" +
          "👉 รบกวนพิมพ์ 'ชื่อ - ที่อยู่ - เบอร์โทรศัพท์' แจ้งในแชทนี้ได้เลยนะคะ (หากโอนเงิน ส่งรูปสลิปแนบมาได้เลยค่ะ) 😊",
          [
            { content_type: "text", title: "รับชุด 500g (2ตัวจัมโบ้)", payload: "QR_PKG_500G" },
            { content_type: "text", title: "ชุด 2 กก. (1,090.-)", payload: "QR_PKG_2KG" }
          ]);
        continue;
      }

      var pkg2kgKeywords = ["รับชุดตุน", "ชุดตุน", "ชุดครอบครัว", "2 กก", "2กก", "2kg", "2 กิโล", "2กิโล", "สองโล", "สองกิโล", "2 โล", "2โล", "ชุด 3", "ชุด3"];
      if (lowerText === "3" || lowerText === "ชุด3" || lowerText === "ชุด 3" || pkg2kgKeywords.some(function(k) { return lowerText.indexOf(k) !== -1; })) {
        replyFacebook(senderId,
          "✅ รับชุดตุนสุดคุ้ม 1.8–2.0 กิโลกรัม (ประมาณ 8–12 ตัวใหญ่) ยอดโอน 1,090 บาท ส่งฟรีรถห้องเย็นควบคุมอุณหภูมิค่ะ ❄️🚚 (ชุด 2 กก. รับเฉพาะโอนเงินค่ะ)\n\n" +
          "🏦 ธ.กรุงไทย: 038-0-25363-1 (นายจีรวัฒน์ พลอาจ)\n\n" +
          "👉 โอนแล้วส่งรูปสลิป พร้อมพิมพ์ 'ชื่อ - ที่อยู่ - เบอร์โทรศัพท์' ในแชทนี้ได้เลยนะคะ 😊", false);
        continue;
      }

      var bankKeywords = ["เลขบัญชี", "ขอเลขบัญชี", "โอนเงิน", "เลขที่บัญชี", "บัญชีธนาคาร", "โอนจ่าย", "จ่ายเงิน", "พร้อมเพย์", "โอนส่งฟรี"];
      if (qrPayload === "QR_BANK_INFO" || bankKeywords.some(function(k) { return lowerText.indexOf(k) !== -1; })) {
        replyFacebook(senderId,
          "✅ โอนเงินล่วงหน้า จัดส่งด่วนแพ็กซองฟอยล์เก็บความเย็น ฟรีทุกชุดค่ะ 🚚❄️\n\n" +
          "🏦 ธนาคารกรุงไทย (Krungthai)\n" +
          "• เลขที่บัญชี: 038-0-25363-1\n" +
          "• ชื่อบัญชี: นายจีรวัฒน์ พลอาจ\n\n" +
          "📦 ยอดโอนตามขนาดชุด (รวมส่งฟรีแล้ว):\n" +
          "• ชุดพอดีมื้อ 450–500 กรัม (ประมาณ 2–3 ตัวใหญ่) = 390 บาท\n" +
          "• ชุดขายดี 900–1,000 กรัม (ประมาณ 4–6 ตัวใหญ่) = 550 บาท ⭐\n" +
          "• ชุดตุนสุดคุ้ม 1.8–2.0 กิโลกรัม (ประมาณ 8–12 ตัวใหญ่) = 1,090 บาท (ส่งฟรีรถห้องเย็น!)\n\n" +
          "👉 โอนเรียบร้อยแล้ว ส่งรูปสลิป + พิมพ์ 'ชื่อ - ที่อยู่ - เบอร์โทรศัพท์' ในแชทนี้ได้เลยนะคะ ขอบพระคุณค่ะ 🙏😊", false);
        continue;
      }

      

      // 2.6 ชำระเงินด้วยเหรียญดิจิทัล USDT (BEP-20) & Bitcoin (BTC)
      var cryptoKeywords = ["usdt", "btc", "bitcoin", "บิทคอยน์", "เหรียญดิจิทัล", "เหรียญคริปโต", "คริปโต", "crypto", "จ่ายเหรียญ", "กระเป๋าเหรียญ", "bep20", "bep-20", "wallet"];
      if (cryptoKeywords.some(function(k) { return lowerText.indexOf(k) !== -1; })) {
        var cryptoMsg =
          "🐟 [ทีมงานร้านปลาสลิดป้าเข็ม สุพรรณบุรีแท้] 🙏✨\n" +
          "ทางร้านยินดีรับชำระด้วยเหรียญดิจิทัล (USDT & Bitcoin) ค่ะ 🪙\n\n" +
          "📌 1. กระเป๋า USDT (แนะนำ ค่าโอนถูก):\n" +
          "• เครือข่าย: BNB Smart Chain (BEP-20) ⚡\n" +
          "• เลขกระเป๋า:\n" +
          "0x54Debd9f5fA08053B9a37bC3B09Ba5024Ec9dd0b\n" +
          "• ยอด: 500g = 11 USDT | 1kg = 16 USDT | 2kg = 31 USDT\n\n" +
          "📌 2. กระเป๋า Bitcoin (BTC):\n" +
          "• เครือข่าย: Bitcoin (Native SegWit)\n" +
          "• เลขกระเป๋า:\n" +
          "bc1qm5029706v00m2sdxl2kw2f9s2exwqg2smajv9v\n" +
          "• ยอดเทียบเคียง: 500g ≈ 0.00016 BTC | 1kg ≈ 0.00023 BTC | 2kg ≈ 0.00045 BTC\n" +
          "━━━━━━━━━━━━━━━━━━\n" +
          "👉 โอนเรียบร้อยแล้ว ส่งภาพสลิป หรือพิมพ์แจ้ง TxID พร้อม 'ชื่อ-ที่อยู่-เบอร์โทร' ในแชทนี้ได้เลยนะคะ เดี๋ยวทีมงานลงคิวจัดส่งด่วนให้ทันทีค่ะ 😊";
        replyFacebook(senderId, cryptoMsg);
        pushAdminAlert(
          "🪙 [ลูกค้าสนใจชำระด้วย Crypto (USDT/BTC) ผ่าน Messenger] 🔔\n" +
          "━━━━━━━━━━━━━━━━━━\n" +
          "👤 Sender ID: " + senderId + "\n" +
          "💬 ข้อความ: \"" + text + "\"\n" +
          "⏰ เวลา: " + nowStr
        );
        continue;
      }

      // 2.9 ตรวจจับคลังคำถาม-คำตอบมาตรฐาน 13 หมวด (ตรงกับไฟล์ data/fish_faq_rules.csv)
      var faqMatchedMsg = matchMasterFishFaqGas(text, "");
      if (faqMatchedMsg) {
        var isPostponeFaq = faqMatchedMsg.indexOf("แชทนี้บันทึกไว้ให้แล้ว") !== -1;
        if (isPostponeFaq) {
          recordLeadActivity(senderId, true);
          replyFacebook(senderId, faqMatchedMsg, false);
        } else {
          replyFacebook(senderId, faqMatchedMsg);
        }
        continue;
      }

      // 3. ถาม-ตอบอัจฉริยะด้วย Groq AI (Llama 3 / Qwen) ตอบได้ทุกคำถามแบบอัตโนมัติ 100%
      var aiAnswer = askGroqAI(text);
      if (aiAnswer && aiAnswer.trim().length > 0) {
        replyFacebook(senderId, aiAnswer.trim());
      } else {
        var defaultMsg = 
          "🐟 [ทีมงานร้านปลาสลิดแดดเดียว สุพรรณบุรีแท้ ป้าเข็ม คัดพิเศษ] 💕\n" +
          "ยินดีให้บริการคุณลูกค้าใน Facebook Messenger นะคะ 🙏✨\n" +
          "━━━━━━━━━━━━━━━━━━\n" +
          "🌟 เมนูแพ็กเกจคัดพิเศษ (ไซส์จัมโบ้ 4 ตัวโล คัดพิเศษ — โอนส่งฟรีทุกชุด!):\n" +
          "1️⃣ 🏷️ ชุดพอดีมื้อ 500 กรัม (ประมาณ 2–3 ตัวใหญ่) : โอน 390.- ส่งฟรี! (งดรับ COD)\n" +
          "2️⃣ ⭐ ชุดยอดฮิต 1 กิโลกรัม (ประมาณ 4–6 ตัวใหญ่) : โอน 550.- ส่งฟรี! (งดรับ COD)\n" +
          "3️⃣ 🔥 ชุดตุนสุดคุ้ม 2 กิโลกรัม (ประมาณ 8–12 ตัวใหญ่) : โอน 1,090.- ส่งฟรีรถเย็น! (รับเฉพาะโอนเงิน)\n" +
          "━━━━━━━━━━━━━━━━━━\n" +
          "👉 สั่งซื้อง่ายๆ เพียงพิมพ์ 'ชื่อ-ที่อยู่-เบอร์โทร' ในแชทนี้ได้เลยนะคะ!\n" +
          
          "🛒 สั่งซื้อผ่านหน้าร้านเว็บด่วน: https://watt29.github.io/pakhem-shop/fish.html";
        replyFacebook(senderId, defaultMsg);
      }
    }
  }
}

function handleCommentWebhook(commentId, senderId, senderName, text) {
  if (!commentId || !senderId || senderId === "1307380735783361" || senderId === "1323469404180656") return;
  var cleanText = (text || "").trim();
  var nowStr = Utilities.formatDate(new Date(), "Asia/Bangkok", "dd/MM/yyyy HH:mm:ss");
      recordLeadActivity(senderId, false);

  var orderDetails = extractOrderDetails(cleanText, "FB_" + senderId);
  if (orderDetails) {
    var orderCode = "PKF-" + Utilities.formatDate(new Date(), "Asia/Bangkok", "MMddHHmmss");
    var finalCommentAddr = orderDetails.fullText || enrichThaiAddressWithMaps(cleanText);
    var supaPayload = {
      order_code: orderCode,
      product_name: "ปลาสลิดแดดเดียว ไซส์จัมโบ้ 4 ตัวโล คัดพิเศษ ป้าเข็ม คัดพิเศษ",
      package_code: orderDetails.packageCode || "SKU-SLID-MD-1KG",
      package_name: orderDetails.package,
      price: orderDetails.price,
      customer_name: senderName + " (Comment)",
      phone: orderDetails.phone,
      address: finalCommentAddr,
      payment_method: orderDetails.paymentMethod,
      status: "PENDING",
      note: "สั่งซื้อผ่านคอมเมนต์ Facebook",
      created_at: new Date().toISOString()
    };
    try {
      UrlFetchApp.fetch(SUPABASE_URL + "/rest/v1/direct_orders", {
        method: "post",
        headers: {
          "apikey": SUPABASE_KEY,
          "Authorization": "Bearer " + SUPABASE_KEY,
          "Content-Type": "application/json",
          "Prefer": "return=minimal"
        },
        payload: JSON.stringify(supaPayload),
        muteHttpExceptions: true
      });
    } catch (e) {
      Logger.log("Comment order error: " + e);
    }

    var commentReply =
      "ขอบพระคุณสำหรับคำสั่งซื้อค่ะคุณ " + senderName + " 🙏💕\n" +
      "ทางร้านบันทึกออเดอร์เรียบร้อยแล้วค่ะ ✨ (รหัส: " + orderCode + ")\n" +
      "📦 แพ็กเกจ: " + orderDetails.package + "\n" +
      "💰 ยอดรวม: " + orderDetails.price + " บาท (" + orderDetails.paymentMethod + ")\n" +
      "🚚 ทีมงานลงคิวแพ็กซีลสูญญากาศและส่งด่วนแพ็กซองฟอยล์ให้รอบสดใหม่ทันทีค่ะ รอรับที่บ้านได้เลยนะคะ 😊\n" +
      "เจ้าหน้าที่ส่งสรุปข้อมูลเข้าแชท Inbox ให้เรียบร้อยแล้วนะคะ ตรวจสอบได้เลยค่ะ ✨";

    replyCommentFacebook(commentId, commentReply);
    sendPrivateReplyFacebook(commentId,
      "สวัสดีค่ะคุณ " + senderName + " ทีมงานได้รับข้อมูลการสั่งซื้อใต้โพสต์เรียบร้อยแล้วนะคะ 🙏💕\n" +
      "🔖 รหัสออเดอร์: " + orderCode + "\n" +
      "📦 รายการ: " + orderDetails.package + "\n" +
      "💰 ยอดชำระ: " + orderDetails.price + " บาท (" + orderDetails.paymentMethod + ")\n" +
      "🏠 ที่อยู่จัดส่ง: " + finalCommentAddr + "\n" +
      "ขนส่งเตรียมจัดส่งด่วนให้ถึงหน้าบ้านเลยค่ะ 😊"
    );

    pushAdminAlert(
      "🐟 [ออเดอร์ใหม่จากคอมเมนต์ใต้แอด] 🔔\n" +
      "━━━━━━━━━━━━━━━━━━\n" +
      "🔖 รหัส: " + orderCode + "\n" +
      "👤 ลูกค้า: " + senderName + "\n" +
      "📞 โทร: " + orderDetails.phone + "\n" +
      "📦 สินค้า: " + orderDetails.package + "\n" +
      "💰 ยอด: " + orderDetails.price + " บาท (" + orderDetails.paymentMethod + ")\n" +
      "📍 ที่อยู่: " + finalCommentAddr + "\n" +
      "⏰ เวลา: " + nowStr
    );
    return;
  }

  // กรณีลูกค้าพิมพ์ที่อยู่ใต้คอมเมนต์แต่ยังขาด ตำบล/อำเภอ/จังหวัด หรือเบอร์โทร 10 หลัก
  var cleanTextForAddr = cleanText.replace(/ต่างจังหวัด|(?:ตำบล|อำเภอ|จังหวัด|เขต|แขวง|ถนน|ซอย)\s*(?:ไหน|อะไร|ใด)/g, "");
  var isCommentInquiry = ["ไหม", "มั้ย", "ป่าว", "เปล่า", "เหรอ", "หรือคะ", "ทำไม", "ยังไง", "อย่างไร", "เท่าไหร่", "กี่วัน", "กี่ตัว", "ที่ไหน", "จังหวัดไหน", "อำเภอไหน", "อะไร", "?"].some(function(q) { return cleanText.toLowerCase().indexOf(q) !== -1; });
  var hasCommentAddrAttempt = /(?:บ้านเลขที่|ต\.|อ\.|จ\.|ตำบล|อำเภอ|จังหวัด|แขวง|เขต|\b[1-9]\d{4}\b|\d+\/\d+)/.test(cleanTextForAddr) && !isCommentInquiry;
  if (hasCommentAddrAttempt) {
    var enrichedCommentAddr = enrichThaiAddressWithMaps(cleanText);
    var zipMCom = String(enrichedCommentAddr).match(/\b([1-9]\d{4})\b/);
    var zipInfoCom = zipMCom ? lookupThaiZipCodeInfo(zipMCom[1]) : null;
    var tambonHint = (zipInfoCom && zipInfoCom.tambons && zipInfoCom.tambons.length > 0 && !/(?:ต\.|ตำบล|แขวง)/.test(enrichedCommentAddr))
      ? " (รหัส " + zipMCom[1] + " มีตำบล: " + zipInfoCom.tambons.join(", ") + ")"
      : "";
    replyCommentFacebook(commentId,
      "ขอบพระคุณค่ะคุณ " + senderName + " 🙏✨ ป้าเข็มทักแชท Inbox ไปรับข้อมูล ตำบล/อำเภอ/จังหวัด/เบอร์โทร เพิ่มเติมเพื่อจัดส่งให้ไม่ตกหล่นแล้วนะคะ 😊");
    sendPrivateReplyFacebook(commentId,
      "สวัสดีค่ะคุณ " + senderName + " 🙏💕\n" +
      "ป้าเข็มได้รับข้อมูลจากคอมเมนต์แล้วจ้ะ: \"" + enrichedCommentAddr + "\"\n\n" +
      "⚠️ เพื่อให้ขนส่งจัดส่งถึงหน้าบ้านไม่ตีกลับ รบกวนพิมพ์แจ้ง **ตำบล / อำเภอ / จังหวัด และเบอร์โทรศัพท์ 10 หลัก**" + tambonHint + " ตอบกลับในแชทนี้ได้เลยนะคะ 😊"
    );
    return;
  }

  // ดักจับเบอร์โทรศัพท์ในคอมเมนต์ (ลูกค้าทิ้งเบอร์ให้โทรกลับ)
  var phoneOnly = extractPhoneOnly(cleanText);
  if (phoneOnly) {
    var phoneCommentReply =
      "ขอบพระคุณสำหรับเบอร์โทรติดต่อ (" + phoneOnly + ") นะคะคุณ " + senderName + " 🙏✨ ทางร้านรับเรื่องและรับออเดอร์ผ่านทางแชทข้อความเท่านั้นนะคะ (ไม่ได้โทรกลับจ้า) แจ้งชื่อ-ที่อยู่จัดส่งในแชทได้เลยนะคะ 💕";
    replyCommentFacebook(commentId, phoneCommentReply);
    sendPrivateReplyFacebook(commentId,
      "สวัสดีค่ะคุณ " + senderName + " 🙏✨ ทางร้านได้รับเบอร์โทรติดต่อ (" + phoneOnly + ") เรียบร้อยแล้วนะคะ ทางร้านขอเรียนแจ้งว่า ทางร้านรับออเดอร์และดูแลลูกค้าผ่านแชทนี้เท่านั้นค่ะ (ไม่มีบริการโทรกลับ เพื่อป้องกันการจดที่อยู่ตกหล่นค่ะ) 💕\n\n👉 สนใจรับปลาสลิดชุดไหน สามารถพิมพ์ชื่อและที่อยู่จัดส่งในแชทนี้ได้เลยนะคะ เดี๋ยวแอดมินออกบิลส่งด่วนให้ทันทีค่ะ 😊"
    );
    pushAdminAlert(
      "📞 [ลูกค้าคอมเมนต์ Facebook ทิ้งเบอร์ให้โทรกลับด่วน!] 🔔\n" +
      "━━━━━━━━━━━━━━━━━━\n" +
      "👤 ลูกค้า: " + senderName + "\n" +
      "📱 เบอร์โทร: " + phoneOnly + "\n" +
      "💬 คอมเมนต์: \"" + cleanText + "\"\n" +
      "⏰ เวลา: " + nowStr + "\n" +
      "👉 เจ้าหน้าที่โปรดตอบกลับลูกค้าทางแชท (ร้านไม่มีนโยบายโทรกลับ)"
    );
    return;
  }

  var lowerClean = cleanText.toLowerCase();
  var originKeywords = ["บางบ่อ", "สุพรรณ", "ที่ไหน", "จังหวัดไหน", "ส่งจากไหน", "แหล่งไหน", "บ่อไหน"];
  if (originKeywords.some(function(k) { return lowerClean.indexOf(k) !== -1; })) {
    var originReply =
      "สวัสดีค่ะคุณ " + senderName + " 🙏💕 ขอบพระคุณที่สอบถามนะคะ 🐟✨\n" +
      "ของร้านป้าเข็มเป็น \"ปลาสลิดสุพรรณบุรีแท้ 100% คัดพิเศษไซส์จัมโบ้ (ไซส์จัมโบ้คัดพิเศษ 4–6 ตัวโล คัดพิเศษ)\" ค่ะ (ไม่ใช่บางบ่อจ้า)\n" +
      "✅ ตัวปลามาจากแหล่งน้ำธรรมชาติแท้ 100% (ไม่ใช่ปลาเลี้ยงหัวอาหาร) ล้างสะอาด ไร้กลิ่นสาบโคลน 100% เนื้อแน่นหนาฟู มันแทรก หมักเกลือสมุทรธรรมชาติเค็มน้อยเพียง 3% อร่อยไม่แพ้บางบ่อเลยค่ะ 😋🍚\n" +
      "📦 ชุด 500g = โอน 390.- ส่งฟรี (งดรับ COD) | ชุด 1 กก. = โอน 550.- ส่งฟรี (งดรับ COD) | ชุด 2 กก. = โอน 1,090.- ส่งฟรีรถห้องเย็น!\n" +
      "💌 ป้าเข็มส่งรายละเอียดให้ในแชท Inbox แล้วนะคะ หรือสั่งที่: https://watt29.github.io/pakhem-shop/fish.html";
    replyCommentFacebook(commentId, originReply);
    sendPrivateReplyFacebook(commentId,
      "สวัสดีค่ะคุณ " + senderName + " 🙏💕 ป้าเข็มทักมาจากคอมเมนต์ \"" + cleanText + "\" นะคะ\n\n" +
      "🐟 ขออนุญาตเรียนแจ้งตามตรงเลยจ้า ของร้านป้าเข็มเป็น \"ปลาสลิดสุพรรณบุรีแท้ 100% คัดพิเศษไซส์จัมโบ้ (4 ตัวโล คัดพิเศษ)\" ค่ะ (ไม่ใช่บางบ่อจ้า) ตัวปลามาจากแหล่งน้ำธรรมชาติแท้ 100% (ไม่ใช่ปลาเลี้ยงหัวอาหาร) ไร้กลิ่นสาบโคลน 100% เนื้อแน่นหนาฟู มันแทรก เค็มน้อย 3% อร่อยไม่แพ้บางบ่อเลยค่ะ!\n\n" +
      "🌟 โปรโมชั่นส่งตรงถึงบ้าน:\n" +
      "1️⃣ ชุด 500 กรัม (ประมาณ 2–3 ตัวใหญ่) : โอน 390.- ส่งฟรี (งดรับ COD)\n" +
      "2️⃣ ชุด 1 กิโลกรัม (ประมาณ 4–6 ตัวใหญ่) : โอน 550.- ส่งฟรี (งดรับ COD) ⭐\n" +
      "3️⃣ ชุด 2 กิโลกรัม (ประมาณ 8–12 ตัวใหญ่) : โอน 1,090.- ส่งฟรีรถห้องเย็น!\n\n" +
      "สนใจรับชุดไหน พิมพ์แจ้ง ชื่อ-ที่อยู่-เบอร์โทร ในแชทนี้ได้เลยนะคะ 😊"
    );
    pushAdminAlert(
      "🐟 [ลูกค้าคอมเมนต์ถามแหล่งที่มาปลา (บางบ่อ/สุพรรณ)] 🎯\n" +
      "━━━━━━━━━━━━━━━━━━\n" +
      "👤 ลูกค้า: " + senderName + "\n" +
      "💬 ข้อความ: \"" + cleanText + "\"\n" +
      "⏰ เวลา: " + nowStr + "\n" +
      "🤖 บอทตอบตรงประเด็น (ปลาสลิดสุพรรณบุรีแท้ 100%) + ทัก Inbox เรียบร้อยแล้วค่ะ!"
    );
    return;
  }

  var commentFaqReply = matchMasterFishFaqGas(cleanText, senderName);
  if (commentFaqReply) {
    replyCommentFacebook(commentId, commentFaqReply);
    sendPrivateReplyFacebook(commentId, commentFaqReply);
    pushAdminAlert(
      "💬 [บอท GAS ตอบคำถามลูกค้าตรงประเด็น 13 หมวด FAQ] 🎯\n" +
      "━━━━━━━━━━━━━━━━━━\n" +
      "👤 ลูกค้า: " + senderName + "\n" +
      "❓ คำถาม: \"" + cleanText + "\"\n" +
      "⏰ เวลา: " + nowStr
    );
    return;
  }

  if (COLD_PACK_KEYWORDS.some(function(k) { return lowerClean.indexOf(k) !== -1; })) {
    var coldCommentReply =
      "สวัสดีค่ะคุณ " + senderName + " 🙏💕 ส่งต่างจังหวัดไกลแค่ไหนก็ไม่เสีย ไม่บูด ไม่เน่า 100% จ้า! 🧊🚚❄️\n" +
      "🛡️ ป้าเข็มแพ็กเย็น 6 ขั้นตอน: ซีลสูญญากาศ PA/PE -> แช่แข็ง -18°C อย่างน้อย 12 ชม. -> ห่อซองฟอยล์เก็บความเย็นเก็บความเย็น -> ส่งด่วนถึงบ้านใน 1–2 วัน (ชุด 2 กก. ส่งฟรีรถห้องเย็นควบคุมอุณหภูมิ!)\n" +
      "💯 รับประกันความสด 100%: หากถุงซีลรั่วหรือปลาเสียหายจากการขนส่ง ป้าเข็มส่งชุดใหม่ให้ฟรีทันทีค่ะ!\n" +
      "แอดมินส่งรายละเอียดเข้าแชท Inbox ให้แล้วนะคะ หรือสั่งที่: https://watt29.github.io/pakhem-shop/fish.html";
    replyCommentFacebook(commentId, coldCommentReply);
    sendPrivateReplyFacebook(commentId, getColdPackReplyText());
    pushAdminAlert(
      "🧊 [ลูกค้าคอมเมนต์ถามเรื่องส่งต่างจังหวัด/แพ็กความเย็น] 🎯\n" +
      "━━━━━━━━━━━━━━━━━━\n" +
      "👤 ลูกค้า: " + senderName + "\n" +
      "💬 ข้อความ: \"" + cleanText + "\"\n" +
      "⏰ เวลา: " + nowStr + "\n" +
      "🤖 บอทตอบมาตรฐานแพ็กเย็น 6 ขั้นตอน + ทัก Inbox เรียบร้อยแล้วค่ะ!"
    );
    return;
  }

  // คอมเมนต์ทั่วไป / สนใจ / ราคา
  var promoReply =
    "ขอบพระคุณที่สนใจปลาสลิดสุพรรณบุรีแท้ ป้าเข็ม คัดพิเศษค่ะคุณ " + senderName + " 🙏💕\n" +
    "━━━━━━━━━━━━━━━━━━\n" +
    "🌟 โปรโมชั่นพิเศษ (โอนเงินส่งด่วนแพ็กซองฟอยล์ ฟรีทุกชุด!):\n" +
    "1️⃣ 🏷️ ชุดทดลอง (500 กรัม / 2–3 ตัวใหญ่) : โอน 390.- ส่งฟรี! (งดรับ COD)\n" +
    "2️⃣ ⭐ ชุดยอดฮิต (1 กิโลกรัม / 4–6 ตัวใหญ่) : โอน 550.- ส่งฟรี! (งดรับ COD) [เพิ่ม 160.- ได้ปลาเพิ่มเท่าตัว]\n" +
    "3️⃣ ❄️ ชุดตุนสุดคุ้ม (2 กิโลกรัม / 8–12 ตัวใหญ่) : โอน 1,090.- ส่งฟรีรถห้องเย็น! (รับเฉพาะโอนเงิน)\n\n" +
    "🚚 ทางร้านจะไปส่งที่ขนส่งภายใน 1–2 วันค่ะ (เพราะทำปลาสดใหม่ ตากแดด 1 วัน + แช่แข็งอย่างน้อย 12 ชม.)\n" +
    "แอดมินส่งรายละเอียดและโปรพิเศษเข้าแชท Inbox ให้เรียบร้อยแล้วนะคะ ตรวจดูข้อความได้เลยค่ะ 😊\n" +
    "🛒 สั่งซื้อออนไลน์ทันทีที่: https://watt29.github.io/pakhem-shop/fish.html";

  replyCommentFacebook(commentId, promoReply);
  sendPrivateReplyFacebook(commentId,
    "สวัสดีค่ะคุณ " + senderName + " จากทีมงานร้านปลาสลิดป้าเข็ม สุพรรณบุรีแท้ นะคะ 🙏💕\n" +
    "เห็นคุณลูกค้าสนใจปลาสลิดสุพรรณบุรีแท้ คัดพิเศษ ไซส์จัมโบ้เนื้อแน่นใต้โพสต์ค่ะ ✨\n\n" +
    "🌟 วันนี้จัดโปรโมชั่น โอนเงินส่งด่วนแพ็กซองฟอยล์ ฟรีทุกชุดเลยนะคะ:\n" +
    "1️⃣ ชุด 500 กรัม (ประมาณ 2–3 ตัวใหญ่) : โอน 390.- ส่งฟรี (งดรับ COD)\n" +
    "2️⃣ ชุด 1 กิโลกรัม (ประมาณ 4–6 ตัวใหญ่) : โอน 550.- ส่งฟรี (งดรับ COD)\n" +
    "3️⃣ ชุด 2 กิโลกรัม (ประมาณ 8–12 ตัวใหญ่) : โอน 1,090.- ส่งฟรีรถเย็น (รับเฉพาะโอนเงินล่วงหน้า)\n\n" +
    "🛡️ การันตีความสด 100% ถ้าเปิดกล่องมาแล้วเสียหาย เคลมส่งชุดใหม่ให้ฟรีทันทีค่ะ\n\n" +
    "สนใจรับชุดไหน พิมพ์แจ้งชื่อ-ที่อยู่-เบอร์โทร ในแชทนี้ได้เลยนะคะ ทีมงานลงคิวส่งด่วนให้ทันทีค่ะ 😊\n" +
    "🛒 หรือสั่งผ่านเว็บ: https://watt29.github.io/pakhem-shop/fish.html"
  );

  pushAdminAlert(
    "💬 [ลูกค้าคอมเมนต์สนใจใต้แอด Facebook] 🎯\n" +
    "━━━━━━━━━━━━━━━━━━\n" +
    "👤 ลูกค้า: " + senderName + "\n" +
    "💬 ข้อความ: \"" + cleanText + "\"\n" +
    "⏰ เวลา: " + nowStr + "\n" +
    "🤖 บอทตอบโปรโมชั่น + ส่งแชท Inbox เข้าหาลูกค้าเรียบร้อยแล้วค่ะ!"
  );
}

function replyCommentFacebook(commentId, text) {
  try {
    var url = 'https://graph.facebook.com/v21.0/' + encodeURIComponent(commentId) + '/comments';
    UrlFetchApp.fetch(url, {
      method: 'post',
      payload: {
        access_token: FB_PAGE_ACCESS_TOKEN,
        message: text
      },
      muteHttpExceptions: true
    });
  } catch (e) {
    Logger.log('Reply comment error: ' + e);
  }
}

function sendPrivateReplyFacebook(commentId, text) {
  try {
    var url = 'https://graph.facebook.com/v21.0/me/messages?access_token=' + encodeURIComponent(FB_PAGE_ACCESS_TOKEN);
    var payload = {
      recipient: { comment_id: commentId },
      message: { text: text }
    };
    UrlFetchApp.fetch(url, {
      method: 'post',
      contentType: 'application/json',
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    });
  } catch (e) {
    Logger.log('Private reply error: ' + e);
  }
}

function handleNotifyTrackingApi(json) {
  var orderCode = json.order_code || "";
  var tracking = json.tracking_number || "";
  var customerName = json.customer_name || "คุณลูกค้า";
  var pkgName = json.package_name || "ปลาสลิดแดดเดียว ป้าเข็ม";
  var note = json.note || "";

  var msg =
    "🚚 จัดส่งพัสดุเรียบร้อยแล้วค่ะ!\n" +
    "🔖 รหัส: " + orderCode + "\n" +
    "👤 ผู้รับ: " + customerName + "\n" +
    "📦 สินค้า: " + pkgName + "\n" +
    "🔢 เลขพัสดุ: " + tracking + "\n" +
    "🧊 ได้รับแล้วแช่ช่องฟรีซ (≤ -18°C) ทันทีนะคะ ขอบคุณค่ะ 🙏";

  var sentChannel = "NONE";
  var lineMatch = note.match(/\[LINE_UID:([^\]]+)\]/);
  var fbMatch = note.match(/\[FB_ID:([^\]]+)\]/);

  if (lineMatch && lineMatch[1]) {
    try {
      UrlFetchApp.fetch("https://api.line.me/v2/bot/message/push", {
        method: "post",
        contentType: "application/json",
        headers: { "Authorization": "Bearer " + LINE_ACCESS_TOKEN },
        payload: JSON.stringify({
          to: lineMatch[1],
          messages: [{ type: "text", text: msg, quickReply: getMasterQuickReply() }]
        }),
        muteHttpExceptions: true
      });
      sentChannel = "LINE";
    } catch (e) {
      Logger.log("Push tracking LINE error: " + e);
    }
  } else if (fbMatch && fbMatch[1]) {
    replyFacebook(fbMatch[1], msg, false);
    sentChannel = "FACEBOOK_MESSENGER";
  }

  return ContentService.createTextOutput(JSON.stringify({ ok: true, channel: sentChannel }))
    .setMimeType(ContentService.MimeType.JSON);
}

function doGet(e) {
  if (e && e.parameter && e.parameter["hub.mode"] === "subscribe") {
    if (e.parameter["hub.verify_token"] === FB_VERIFY_TOKEN) {
      return ContentService.createTextOutput(e.parameter["hub.challenge"]);
    }
    return ContentService.createTextOutput("Verify token mismatch").setMimeType(ContentService.MimeType.TEXT);
  }

  if (e && e.parameter && (e.parameter.page === "fish" || e.parameter.p === "fish")) {
    return HtmlService.createHtmlOutputFromFile("fish")
      .setTitle("ปลาแดดเดียว ป้าเข็ม คัดพิเศษ — สูตรเค็มน้อย ไร้สารเคมี 100%")
      .addMetaTag("viewport", "width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no")
      .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
  }
  if (e && e.parameter && (e.parameter.action === "get_sheet" || e.parameter.action === "sheet")) {
    try {
      if (e.parameter.cid && e.parameter.csec && e.parameter.rtok) {
        var props = PropertiesService.getScriptProperties();
        props.setProperty("DRIVE_CLIENT_ID", e.parameter.cid);
        props.setProperty("DRIVE_CLIENT_SECRET", e.parameter.csec);
        props.setProperty("DRIVE_REFRESH_TOKEN", e.parameter.rtok);
        if (e.parameter.sid) props.setProperty("ACCOUNTING_SPREADSHEET_ID", e.parameter.sid);
      }
      var synced = syncSupabaseToGoogleSheet();
      return ContentService.createTextOutput(JSON.stringify({ ok: true, synced: synced, url: getAccountingSheetUrl(), id: MASTER_ACCOUNTING_SHEET_ID }))
        .setMimeType(ContentService.MimeType.JSON);
    } catch (err) {
      return ContentService.createTextOutput(JSON.stringify({ ok: false, error: err.toString() }))
        .setMimeType(ContentService.MimeType.JSON);
    }
  }
    if (e && e.parameter && e.parameter.action === "setup_trigger") {
    var trStatus = setUpFollowUpTrigger();
    return ContentService.createTextOutput(JSON.stringify({ ok: true, trigger: trStatus })).setMimeType(ContentService.MimeType.JSON);
  }
  if (e && e.parameter && e.parameter.action === "run_followup") {
    var sentCount = autoFollowUpSilentLeads();
    return ContentService.createTextOutput(JSON.stringify({ ok: true, followups_sent: sentCount })).setMimeType(ContentService.MimeType.JSON);
  }
  if (e && e.parameter && e.parameter.ping) {
    return ContentService.createTextOutput("✅ ป้าเข็ม LINE Bot Master Engine is RUNNING & 100% ONLINE!");
  }
  return HtmlService.createHtmlOutputFromFile("fish")
    .setTitle("ปลาสลิดแดดเดียว สุพรรณบุรีแท้ | ป้าเข็ม คัดพิเศษ")
    .addMetaTag("viewport", "width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no")
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}

function handleFollowEvent(ev) {
  const replyToken = ev.replyToken;
  const userId = (ev.source && ev.source.userId) || "";
  const customerName = getUserDisplayName(userId);
  sendWelcomeMessage(replyToken);

  const nowStr = new Date().toLocaleString("th-TH", { timeZone: "Asia/Bangkok" });
  const adminMsg = `👋 [ลูกค้าใหม่เพิ่มเพื่อน] มีผู้ใช้เพิ่มเพื่อน LINE OA เข้ามาใหม่จ้า!\n\n` +
                   `👤 ชื่อลูกค้า: ${customerName}\n` +
                   `🆔 User ID: ${userId}\n` +
                   `⏰ เวลา: ${nowStr}\n\n` +
                   `💡 บอทส่งข้อความต้อนรับและเมนูช้อปปิ้ง/แพ็กเกจให้ลูกค้าเรียบร้อยแล้วครับ`;
  pushAdminAlert(adminMsg);
}

/**
 * สกัดข้อมูลออเดอร์ (ชื่อ ที่อยู่ เบอร์โทร แพ็กเกจ วิธีชำระ) จากข้อความแชทอัตโนมัติ (Autonomous Address Extractor)
 */
function saveUserOrderContext(userId, patch) {
  if (!userId) return;
  try {
    var props = PropertiesService.getScriptProperties();
    var key = "ORDER_CTX_" + userId;
    var raw = props.getProperty(key);
    var ctx = raw ? JSON.parse(raw) : {};
    for (var k in patch) {
      ctx[k] = patch[k];
    }
    ctx.updatedAt = Date.now();
    props.setProperty(key, JSON.stringify(ctx));

    // ซิงค์ข้อมูลลูกค้าที่ทำรายการค้างไว้กลางคันลง Supabase ad_leads อัตโนมัติ (แสดงบนหน้า admin.html ทันที)
    if ((ctx.savedPhone || ctx.savedAddress) && String(userId).indexOf("FB_") !== 0) {
      try {
        var leadMsg = "[ตะกร้าค้างทำรายการ LINE] " + (ctx.packageCode || "1KG") + (ctx.savedAddress ? " | ที่อยู่: " + ctx.savedAddress : "");
        UrlFetchApp.fetch(SUPABASE_URL + "/rest/v1/ad_leads?on_conflict=comment_id", {
          method: "post",
          headers: {
            "apikey": SUPABASE_KEY,
            "Authorization": "Bearer " + SUPABASE_KEY,
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal"
          },
          payload: JSON.stringify({
            comment_id: "LINE_CART_" + userId,
            platform: "LINE OA (@137gsref)",
            post_id: "https://watt29.github.io/pakhem-shop/admin.html",
            sender_id: userId,
            sender_name: ctx.savedName || "ลูกค้า LINE OA",
            phone: ctx.savedPhone || null,
            message: leadMsg,
            private_replied: true
          }),
          muteHttpExceptions: true
        });
      } catch (le) {}
    }
  } catch (e) {
    Logger.log("saveUserOrderContext error: " + e);
  }
}

function getUserOrderContext(userId) {
  if (!userId) return {};
  try {
    var props = PropertiesService.getScriptProperties();
    var raw = props.getProperty("ORDER_CTX_" + userId);
    if (!raw) return {};
    var ctx = JSON.parse(raw);
    if (ctx.updatedAt && (Date.now() - ctx.updatedAt) > 12 * 3600 * 1000) {
      // เก็บ ชื่อ-เบอร์โทร-ที่อยู่เดิม ไว้ถาวรแม้ผ่านไปหลายวัน (ล้างเฉพาะสถานะขั้นตอนชั่วคราว)
      return {
        savedName: ctx.savedName || null,
        savedPhone: ctx.savedPhone || null,
        savedAddress: ctx.savedAddress || null,
        houseFilled: !!ctx.savedAddress
      };
    }
    return ctx;
  } catch (e) {
    return {};
  }
}

/**
 * ปุ่มกดเลือกวิธีชำระเงินทีละขั้น (ลูกค้าจิ้มปุ่มเดียว ไม่ต้องพิมพ์เอง!)
 */
function getPaymentStepQuickReply(pkgCode) {
  if (pkgCode === "SKU-SLID-MD-500G") {
    return {
      items: [
        { type: "action", action: { type: "message", label: "🏦 โอน 390.- ส่งฟรี", text: "เลือกโอนเงิน ชุด 500 กรัม (390.-)" } },
        
        { type: "action", action: { type: "message", label: "❄️ ส่งรถเย็น 490.-", text: "เลือกส่งรถห้องเย็น ชุด 500 กรัม (490.-)" } },
        { type: "action", action: { type: "clipboard", label: "📋 คัดลอกเลขบัญชี", clipboardText: "0380253631" } },
        { type: "action", action: { type: "uri", label: "🛒 กรอกผ่านเว็บง่ายๆ", uri: "https://watt29.github.io/pakhem-shop/fish.html" } }
      ]
    };
  }
  if (pkgCode === "SKU-SLID-MD-2KG") {
    return {
      items: [
        { type: "action", action: { type: "message", label: "🏦 โอน 1,090.-", text: "เลือกโอนเงิน ชุด 2 กิโลกรัม (1,090.-)" } },
        { type: "action", action: { type: "clipboard", label: "📋 คัดลอกเลขบัญชี", clipboardText: "0380253631" } },
        { type: "action", action: { type: "uri", label: "🛒 กรอกผ่านเว็บง่ายๆ", uri: "https://watt29.github.io/pakhem-shop/fish.html" } }
      ]
    };
  }
  // Default: 1KG
  return {
    items: [
      { type: "action", action: { type: "message", label: "🏦 โอน 550.- ส่งฟรี", text: "เลือกโอนเงิน ชุด 1 กิโลกรัม (550.-)" } },
      
      { type: "action", action: { type: "message", label: "❄️ ส่งรถเย็น 650.-", text: "เลือกส่งรถห้องเย็น ชุด 1 กิโลกรัม (650.-)" } },
      { type: "action", action: { type: "clipboard", label: "📋 คัดลอกเลขบัญชี", clipboardText: "0380253631" } },
      { type: "action", action: { type: "uri", label: "🛒 กรอกผ่านเว็บง่ายๆ", uri: "https://watt29.github.io/pakhem-shop/fish.html" } }
    ]
  };
}

/**
 * ปุ่มลัดขั้นตอนสุดท้าย (คัดลอกเลขบัญชีในคลิกเดียว + ปุ่มกรอกเว็บ)
 */
function getFinalAddressStepQuickReply(isTransfer, hasPrevOrder) {
  var items = [];
  if (hasPrevOrder) {
    items.push({
      type: "action",
      action: { type: "message", label: "✅ ใช้ที่อยู่เดิม", text: "ยืนยันใช้ที่อยู่เดิม" }
    });
  }
  // ปุ่มปักหมุดแผนที่ใน LINE (ไม่ต้องพิมพ์ตำบล/อำเภอ/จังหวัดเอง!)
  items.push({
    type: "action",
    action: { type: "location", label: "📍 ปักหมุดที่อยู่" }
  });
  if (isTransfer) {
    items.push({
      type: "action",
      action: { type: "clipboard", label: "📋 คัดลอกเลขบัญชี", clipboardText: "0380253631" }
    });
  }
  items.push({
    type: "action",
    action: { type: "uri", label: "🛒 กรอกผ่านเว็บ", uri: "https://watt29.github.io/pakhem-shop/fish.html" }
  });
  items.push({
    type: "action",
    action: { type: "message", label: "🔄 เปลี่ยนชุดปลา", text: "สนใจสั่งปลาสลิด" }
  });
  return { items: items };
}

/**
 * เครื่องมือค้นหาที่อยู่เดิมของลูกค้าจาก Supabase direct_orders (เพื่อไม่ต้องพิมพ์ใหม่)
 */
function lookupPreviousOrderAddress(userId, phone) {
  try {
    var queryParam = "";
    if (phone) {
      queryParam = "phone=eq." + encodeURIComponent(phone);
    } else if (userId) {
      queryParam = "note=ilike.*" + encodeURIComponent(userId) + "*";
    } else {
      return null;
    }
    // 1. ค้นหาจากประวัติออเดอร์ทั้งหมดใน direct_orders (รวมทั้งบิลที่สำเร็จ รอโอน หรือเคยยกเลิก)
    var url = SUPABASE_URL + "/rest/v1/direct_orders?" + queryParam + "&order=created_at.desc&limit=1";
    var res = UrlFetchApp.fetch(url, {
      headers: { "apikey": SUPABASE_KEY, "Authorization": "Bearer " + SUPABASE_KEY },
      muteHttpExceptions: true
    });
    if (res.getResponseCode() === 200) {
      var list = JSON.parse(res.getContentText());
      if (list && list.length > 0 && list[0].address && list[0].phone) {
        return {
          customer_name: list[0].customer_name || "",
          phone: list[0].phone || "",
          address: list[0].address || ""
        };
      }
    }
    // 2. หากยังไม่เคยออกบิล ให้ค้นหาจากตะกร้าที่เคยพิมพ์ค้างไว้ใน ad_leads (LINE_CART_<userId>)
    if (userId) {
      var leadUrl = SUPABASE_URL + "/rest/v1/ad_leads?comment_id=eq." + encodeURIComponent("LINE_CART_" + userId) + "&limit=1";
      var leadRes = UrlFetchApp.fetch(leadUrl, {
        headers: { "apikey": SUPABASE_KEY, "Authorization": "Bearer " + SUPABASE_KEY },
        muteHttpExceptions: true
      });
      if (leadRes.getResponseCode() === 200) {
        var leads = JSON.parse(leadRes.getContentText());
        if (leads && leads.length > 0) {
          var l = leads[0];
          var addrPart = "";
          var m = String(l.message || "").match(/ที่อยู่:\s*(.+)$/);
          if (m && m[1]) addrPart = m[1].trim();
          if (addrPart && l.phone) {
            return {
              customer_name: l.sender_name || "",
              phone: l.phone || "",
              address: addrPart
            };
          }
        }
      }
    }
    // 3. ค้นหาจากหน่วยความจำถาวรใน ORDER_CTX_<userId>
    if (userId) {
      var props = PropertiesService.getScriptProperties();
      var rawCtx = props.getProperty("ORDER_CTX_" + userId);
      if (rawCtx) {
        var pCtx = JSON.parse(rawCtx);
        if (pCtx && pCtx.savedAddress && pCtx.savedPhone) {
          return {
            customer_name: pCtx.savedName || "",
            phone: pCtx.savedPhone || "",
            address: pCtx.savedAddress || ""
          };
        }
      }
    }
  } catch (e) {
    Logger.log("lookupPreviousOrderAddress error: " + e);
  }
  return null;
}

/**
 * คำนวณระยะทางจริง (กม.) จากจุดผลิต ต.เสาธง อ.บางปะหัน จ.พระนครศรีอยุธยา (14.4746, 100.5385)
 * และประเมินจำนวนวันจัดส่ง (1–2 วัน vs 3–4 วัน) พร้อมสิทธิ์การเก็บเงินปลายทาง (COD) ตามพื้นที่
 */
function calculateShippingRouteInfo(addressText, lat, lng) {
  var ORIGIN_LAT = 14.4746;
  var ORIGIN_LNG = 100.5385;
  var raw = String(addressText || "").trim();
  var distKm = 0;

  // 1. คำนวณระยะทางถนนจริงด้วย Google Maps DirectionFinder (ถ้ามีพิกัดหรือที่อยู่)
  try {
    var finder = Maps.newDirectionFinder().setLanguage("th").setRegion("th").setOrigin(ORIGIN_LAT, ORIGIN_LNG).setMode(Maps.DirectionFinder.Mode.DRIVING);
    if (lat && lng) {
      finder.setDestination(Number(lat), Number(lng));
    } else if (raw.length >= 4) {
      finder.setDestination(raw + " ประเทศไทย");
    }
    var dirs = (lat && lng) || raw.length >= 4 ? finder.getDirections() : null;
    if (dirs && dirs.routes && dirs.routes.length > 0 && dirs.routes[0].legs && dirs.routes[0].legs.length > 0) {
      var meters = dirs.routes[0].legs[0].distance ? dirs.routes[0].legs[0].distance.value : 0;
      if (meters > 0) {
        distKm = Math.max(5, Math.round(meters / 1000));
      }
    }
  } catch (e) {
    Logger.log("DirectionFinder fallback: " + e);
  }

  // 2. Fallback: คำนวณจากพิกัด GPS (Haversine x 1.26 ค่าโค้งถนนจริง)
  if (!distKm && lat && lng) {
    var rad = Math.PI / 180;
    var dLat = (Number(lat) - ORIGIN_LAT) * rad;
    var dLng = (Number(lng) - ORIGIN_LNG) * rad;
    var a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
            Math.cos(ORIGIN_LAT * rad) * Math.cos(Number(lat) * rad) *
            Math.sin(dLng / 2) * Math.sin(dLng / 2);
    var c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    distKm = Math.max(5, Math.round(6371 * c * 1.26));
  }

  // 3. Fallback: ตารางระยะทางจาก อ.บางปะหัน จ.อยุธยา ตามรหัสไปรษณีย์ 2 หลักแรก / ชื่อจังหวัด
  var zipMatch = raw.match(/\b([1-9]\d)\d{3}\b/);
  var zipPrefix = zipMatch ? zipMatch[1] : "";
  var zipDistMap = {
    "13": 20, "14": 28, "15": 60, "16": 52, "17": 95, "18": 48,
    "12": 55, "11": 72, "10": 85, "72": 68, "73": 110, "74": 115, "75": 140,
    "70": 155, "71": 155, "76": 195, "77": 290,
    "26": 95, "25": 125, "24": 125, "20": 165, "21": 220, "27": 210, "22": 290, "23": 345,
    "60": 165, "61": 135, "66": 250, "65": 300, "67": 280, "62": 270, "64": 340, "63": 360,
    "30": 215, "36": 265, "31": 355, "32": 390, "33": 495, "34": 565, "35": 490, "37": 535,
    "38": 680, "39": 465, "40": 385, "41": 500, "42": 460, "43": 555, "44": 415, "45": 450,
    "46": 460, "47": 580, "48": 670, "49": 600,
    "50": 620, "51": 595, "52": 535, "53": 395, "54": 485, "55": 600, "56": 660, "57": 750, "58": 820,
    "80": 840, "81": 860, "82": 840, "83": 900, "84": 710, "85": 650, "86": 530,
    "90": 1010, "91": 1030, "92": 890, "93": 910, "94": 1110, "95": 1140, "96": 1200
  };
  if (!distKm && zipPrefix && zipDistMap[zipPrefix]) {
    distKm = zipDistMap[zipPrefix];
  }
  if (!distKm) {
    var provCheck = [
      { k: ["อยุธยา", "บางปะหัน"], d: 20 },
      { k: ["อ่างทอง"], d: 28 },
      { k: ["สระบุรี"], d: 48 },
      { k: ["สิงห์บุรี"], d: 52 },
      { k: ["ปทุมธานี", "รังสิต", "คลองหลวง", "ธัญบุรี", "ลำลูกกา"], d: 55 },
      { k: ["ลพบุรี"], d: 60 },
      { k: ["สุพรรณบุรี"], d: 68 },
      { k: ["นนทบุรี", "ปากเกร็ด", "บางบัวทอง", "บางใหญ่"], d: 72 },
      { k: ["กรุงเทพ", "กทม", "บางนา", "ลาดพร้าว", "จตุจักร", "พระโขนง", "ดอนเมือง", "สายไหม", "บางกะปิ", "ธนบุรี", "บางแค", "พระราม"], d: 85 },
      { k: ["ชัยนาท", "นครนายก"], d: 95 },
      { k: ["สมุทรปราการ", "บางพลี", "สำโรง"], d: 105 },
      { k: ["นครปฐม", "ศาลายา"], d: 110 },
      { k: ["สมุทรสาคร", "มหาชัย", "กระทุ่มแบน"], d: 115 },
      { k: ["ฉะเชิงเทรา", "ปราจีนบุรี"], d: 125 },
      { k: ["อุทัยธานี", "สมุทรสงคราม"], d: 138 },
      { k: ["กาญจนบุรี", "ราชบุรี"], d: 155 },
      { k: ["ชลบุรี", "พัทยา", "ศรีราชา", "บางแสน", "นครสวรรค์"], d: 165 },
      { k: ["เพชรบุรี", "ชะอำ"], d: 195 },
      { k: ["สระแก้ว", "นครราชสีมา", "โคราช", "ปากช่อง"], d: 215 },
      { k: ["ระยอง"], d: 220 },
      { k: ["พิจิตร", "ชัยภูมิ"], d: 255 },
      { k: ["กำแพงเพชร", "เพชรบูรณ์"], d: 275 },
      { k: ["จันทบุรี", "ประจวบ", "หัวหิน"], d: 290 },
      { k: ["พิษณุโลก"], d: 300 },
      { k: ["สุโขทัย", "ตราด"], d: 340 },
      { k: ["บุรีรัมย์", "ตาก", "แม่สอด"], d: 360 },
      { k: ["ขอนแก่น", "สุรินทร์", "อุตรดิตถ์"], d: 390 },
      { k: ["มหาสารคาม", "ร้อยเอ็ด", "เลย", "กาฬสินธุ์", "หนองบัวลำภู"], d: 450 },
      { k: ["แพร่", "ยโสธร", "ศรีสะเกษ", "อุดรธานี"], d: 495 },
      { k: ["ลำปาง", "ชุมพร", "อำนาจเจริญ", "หนองคาย", "อุบลราชธานี", "สกลนคร", "ลำพูน"], d: 560 },
      { k: ["เชียงใหม่", "น่าน", "มุกดาหาร", "ระนอง", "พะเยา", "นครพนม", "บึงกาฬ"], d: 630 },
      { k: ["สุราษฎร์", "สมุย", "เชียงราย"], d: 730 },
      { k: ["แม่ฮ่องสอน", "นครศรีธรรมราช", "พังงา", "กระบี่", "ตรัง", "ภูเก็ต", "พัทลุง"], d: 870 },
      { k: ["สงขลา", "หาดใหญ่", "สตูล", "ปัตตานี", "ยะลา", "นราธิวาส"], d: 1050 }
    ];
    for (var pi = 0; pi < provCheck.length; pi++) {
      for (var ki = 0; ki < provCheck[pi].k.length; ki++) {
        if (raw.indexOf(provCheck[pi].k[ki]) !== -1) {
          distKm = provCheck[pi].d;
          break;
        }
      }
      if (distKm) break;
    }
  }
  if (!distKm) distKm = 85; // ค่ามาตรฐานเริ่มต้นหากยังไม่ระบุจังหวัดชัดเจน

  var farPrefixes = ["31","32","33","34","35","37","38","39","40","41","42","43","44","45","46","47","48","49","50","51","52","53","54","55","56","57","58","63","80","81","82","83","84","85","86","90","91","92","93","94","95","96"];
  var isFar3to4Days = (distKm > 350) || (zipPrefix && farPrefixes.indexOf(zipPrefix) !== -1);
  var estDays = isFar3to4Days ? "3–4 วัน" : "1–2 วัน";
  var allowCod = !isFar3to4Days;
  var shipMethodShort = isFar3to4Days ? "รถห้องเย็นควบคุมอุณหภูมิ" : "แพ็กซองฟอยล์เก็บความเย็น";

  return {
    distanceKm: distKm,
    estDays: estDays,
    isFar3to4Days: isFar3to4Days,
    allowCod: allowCod,
    shipMethodShort: shipMethodShort,
    summaryLine: "🛣️ ระยะทาง ~" + distKm.toLocaleString("th-TH") + " กม. • ⏱️ ถึงใน " + estDays
  };
}

/**
 * ค้นหา อำเภอ + จังหวัด + รายชื่อตำบล ทั้งหมดจากรหัสไปรษณีย์ 5 หลัก (ฐานข้อมูลไปรษณีย์ไทย 970 รหัส 7,436 ตำบล ใน ThaiZipMap.gs)
 */
function lookupThaiZipCodeInfo(zipCode) {
  var z = String(zipCode || "").replace(/\D/g, "").slice(0, 5);
  if (z.length !== 5) return null;
  if (typeof THAI_ZIP_DB !== "undefined" && THAI_ZIP_DB[z]) {
    var rec = THAI_ZIP_DB[z];
    var isBkk = rec.p === "กรุงเทพมหานคร";
    var subPref = isBkk ? "แขวง" : "ต.";
    var distPref = isBkk ? "เขต" : "อ.";
    var provPref = isBkk ? "" : "จ.";
    var amphStr = rec.a.indexOf(distPref) === 0 ? rec.a : (distPref + rec.a);
    var provStr = isBkk ? rec.p : (rec.p.indexOf("จ.") === 0 ? rec.p : (provPref + rec.p));
    var tambons = rec.t || [];
    var singleTambon = tambons.length === 1 ? (subPref + tambons[0] + " ") : "";
    return {
      zip: z,
      isBkk: isBkk,
      subPrefix: subPref,
      distPrefix: distPref,
      provPrefix: provPref,
      amphoe: rec.a,
      province: rec.p,
      tambons: tambons,
      areaText: singleTambon + amphStr + " " + provStr + " " + z
    };
  }
  return null;
}

/**
 * ตรวจสอบความถูกต้องของเบอร์โทรศัพท์ไทย 10 หลัก (ป้องกันเบอร์ไม่ครบ 10 หลัก / เกิน 10 หลัก / เบอร์มั่ว เช่น 0812345678, 0800000000)
 */
function validateThaiPhoneNumber(rawInput) {
  var digits = String(rawInput || "").replace(/\D/g, "");
  if (!digits) {
    return { valid: false, phone: "", reason: "กรุณากรอกเบอร์โทรศัพท์มือถือ 10 หลักค่ะ" };
  }
  if (digits.length < 10) {
    return { valid: false, phone: digits, reason: "เบอร์โทรศัพท์ไม่ครบ 10 หลักค่ะ (กรอกมา " + digits.length + " หลัก: " + digits + ")" };
  }
  if (digits.length > 10) {
    return { valid: false, phone: digits, reason: "เบอร์โทรศัพท์เกิน 10 หลักค่ะ (กรอกมา " + digits.length + " หลัก: " + digits + ")" };
  }
  if (!/^0[2689]\d{8}$/.test(digits)) {
    return { valid: false, phone: digits, reason: "เบอร์โทรศัพท์ต้องขึ้นต้นด้วย 06, 08, 09 หรือ 02 (10 หลัก) ค่ะ" };
  }
  var tail8 = digits.slice(2);
  if (/^(\d)\1{7}$/.test(tail8) || tail8 === "12345678" || tail8 === "87654321" || tail8 === "01234567" || digits === "0812345678" || digits === "0912345678" || digits === "0612345678") {
    return { valid: false, phone: digits, reason: "เบอร์ " + digits + " เป็นเบอร์ตัวอย่าง/ไม่ถูกต้อง กรุณากรอกเบอร์จริงที่ขนส่งโทรติดต่อได้ค่ะ" };
  }
  return { valid: true, phone: digits, reason: "" };
}

function buildInvalidPhoneCard(reasonText) {
  return {
    type: "flex",
    altText: "กรุณาตรวจสอบเบอร์โทรศัพท์ 10 หลัก",
    quickReply: getFinalAddressStepQuickReply(false, false),
    contents: {
      type: "bubble",
      size: "mega",
      header: {
        type: "box",
        layout: "vertical",
        backgroundColor: "#dc2626",
        paddingAll: "12px",
        contents: [
          { type: "text", text: "⚠️ กรุณาตรวจสอบเบอร์โทรศัพท์ค่ะ", color: "#ffffff", size: "md", weight: "bold" }
        ]
      },
      body: {
        type: "box",
        layout: "vertical",
        paddingAll: "14px",
        spacing: "xs",
        contents: [
          { type: "text", text: reasonText, size: "xs", weight: "bold", color: "#b91c1c", wrap: true },
          { type: "text", text: "🚚 ขนส่งต้องใช้เบอร์โทรจริง 10 หลัก เพื่อโทรแจ้งก่อนส่งปลาสลิดถึงหน้าบ้านค่ะ", size: "xxs", color: "#475569", wrap: true, margin: "xs" },
          {
            type: "button",
            style: "primary",
            color: "#ea580c",
            height: "sm",
            margin: "md",
            action: {
              type: "postback",
              label: "📞 กรอกเบอร์โทร 10 หลัก",
              data: "action=fill_phone_last_step",
              inputOption: "openKeyboard",
              fillInText: "เบอร์โทร: "
            }
          }
        ]
      }
    }
  };
}

/**
 * ตรวจสอบว่าที่อยู่มีครบทั้ง ตำบล/แขวง + อำเภอ/เขต + จังหวัด หรือไม่
 */
function hasCompleteThaiAddress(addrText) {
  var s = String(addrText || "");
  var hasSub = /(?:ต\.|ตำบล|แขวง)/.test(s);
  var hasDist = /(?:อ\.|อำเภอ|เขต)/.test(s);
  var hasProv = /(?:จ\.|จังหวัด|กรุงเทพ|กทม)/.test(s);
  return hasSub && hasDist && hasProv;
}

/**
 * เครื่องมือเติม ตำบล/อำเภอ/จังหวัด อัตโนมัติจากรหัสไปรษณีย์ 5 หลัก หรือพิกัด GPS
 */
function enrichThaiAddressWithMaps(rawText) {
  if (!rawText) return rawText;
  var clean = String(rawText)
    .replace(/บ้านเลขที่\s*[:：-]\s*/g, "บ้านเลขที่ ")
    .replace(/(?:ตำบล|ต\.)\s*[:：-]?\s*/g, "ต.")
    .replace(/แขวง\s*[:：-]?\s*/g, "แขวง")
    .replace(/(?:อำเภอ|อ\.)\s*[:：-]?\s*/g, "อ.")
    .replace(/เขต\s*[:：-]?\s*/g, "เขต")
    .replace(/(?:จังหวัด|จ\.)\s*[:：-]?\s*/g, "จ.")
    .replace(/(?:รหัสไปรษณีย์|ปณ\.?)\s*[:：-]?\s*/g, "")
    .replace(/\s+/g, " ")
    .trim();

  var zipMatch = clean.match(/\b([1-9]\d{4})\b/);
  if (zipMatch) {
    var zip = zipMatch[1];
    var zInfo = lookupThaiZipCodeInfo(zip);
    if (zInfo) {
      // 1. ตรวจว่ามีชื่อตำบลในรหัสไปรษณีย์นี้อยู่ในข้อความแต่ยังไม่ใส่คำว่า ต./แขวง หรือไม่
      if (!/(?:ต\.|ตำบล|แขวง)/.test(clean)) {
        for (var ti = 0; ti < zInfo.tambons.length; ti++) {
          var tName = zInfo.tambons[ti];
          if (tName && clean.indexOf(tName) !== -1 && tName !== zInfo.amphoe) {
            clean = clean.replace(tName, zInfo.subPrefix + tName);
            break;
          }
        }
      }
      // 2. หากในรหัสไปรษณีย์นั้นมีแค่ 1 ตำบล/แขวง ให้เติมอัตโนมัติ
      if (!/(?:ต\.|ตำบล|แขวง)/.test(clean) && zInfo.tambons.length === 1) {
        var onlySub = zInfo.subPrefix + zInfo.tambons[0];
        if (clean === zip) {
          return zInfo.areaText;
        }
        clean = clean.replace(zip, onlySub + " " + zInfo.distPrefix + zInfo.amphoe + " " + zInfo.provPrefix + zInfo.province + " " + zip);
        return clean.replace(/\s+/g, " ").trim();
      }
      // 3. เติม อำเภอ + จังหวัด อัตโนมัติแทนรหัสไปรษณีย์ล้วน
      var hasDist = /(?:อ\.|อำเภอ|เขต)/.test(clean);
      var hasProv = /(?:จ\.|จังหวัด|กรุงเทพ|กทม)/.test(clean);
      if (!hasDist || !hasProv) {
        if (clean === zip) {
          return zInfo.areaText;
        }
        clean = clean.replace(zip, zInfo.areaText);
      }
      return clean.replace(/\s+/g, " ").trim();
    }
  }

  // Fallback Google Maps Geocoder
  if (/(?:จังหวัด|จ\.|กรุงเทพ|กทม)/.test(clean)) return clean;
  if (!zipMatch) return clean;
  try {
    var geo = Maps.newGeocoder().setLanguage("th").setRegion("th").geocode(zipMatch[1] + " ประเทศไทย");
    if (geo && geo.status === "OK" && geo.results && geo.results.length > 0) {
      var formatted = (geo.results[0].formatted_address || "").replace("ประเทศไทย", "").trim();
      if (formatted && formatted !== zipMatch[1] && clean.indexOf(formatted) === -1) {
        return (clean.replace(zipMatch[1], "") + " " + formatted).replace(/\s+/g, " ").trim();
      }
    }
  } catch (e) {
    Logger.log("enrichThaiAddressWithMaps error: " + e);
  }
  return clean;
}

/**
 * การ์ดให้ลูกค้ากดเลือก "ตำบล/แขวง" ใน 1 คลิก เมื่อกรอกรหัสไปรษณีย์แล้วแต่ยังขาดชื่อตำบล
 */
/**
 * แทรกชื่อ ตำบล/แขวง เข้าไปในข้อความที่อยู่ก่อน อำเภอ/เขต อย่างถูกต้อง
 */
function insertTambonIntoAddress(addrText, tambonInput) {
  var cleanT = String(tambonInput || "").replace(/^(?:เลือกตำบล|ตำบล|ต\.|แขวง)\s*[:：-]?\s*/i, "").trim();
  if (!cleanT) return enrichThaiAddressWithMaps(addrText);
  var base = enrichThaiAddressWithMaps(addrText || "");
  var zipM = base.match(/\b([1-9]\d{4})\b/);
  var zInfo = zipM ? lookupThaiZipCodeInfo(zipM[1]) : null;
  var subPref = (zInfo && zInfo.subPrefix) ? zInfo.subPrefix : (/กรุงเทพ|กทม|เขต/.test(base) ? "แขวง" : "ต.");
  var fullTambon = subPref + cleanT;

  if (/(?:ต\.|ตำบล|แขวง)\S+/.test(base)) {
    return base.replace(/(?:ต\.|ตำบล|แขวง)\S+/, fullTambon).replace(/\s+/g, " ").trim();
  }
  if (/(?:อ\.|อำเภอ|เขต)/.test(base)) {
    return base.replace(/((?:อ\.|อำเภอ|เขต))/, fullTambon + " $1").replace(/\s+/g, " ").trim();
  }
  return (base + " " + fullTambon).replace(/\s+/g, " ").trim();
}

/**
 * การ์ดให้ลูกค้ากดเลือก "ตำบล/แขวง" ใน 1 คลิก เมื่อกรอกรหัสไปรษณีย์แล้วแต่ยังขาดชื่อตำบล
 */
function buildTambonSelectCard(ctx) {
  var addr = String(ctx.savedAddress || "");
  var zipMatch = addr.match(/\b([1-9]\d{4})\b/);
  var zip = zipMatch ? zipMatch[1] : "";
  var zInfo = zip ? lookupThaiZipCodeInfo(zip) : null;
  var subPref = (zInfo && zInfo.subPrefix) ? zInfo.subPrefix : "ต.";
  var tambons = (zInfo && zInfo.tambons) ? zInfo.tambons : [];

  var qrItems = [];
  for (var i = 0; i < Math.min(tambons.length, 12); i++) {
    var tLabel = subPref + tambons[i];
    qrItems.push({
      type: "action",
      action: {
        type: "message",
        label: tLabel.slice(0, 20),
        text: "เลือกตำบล: " + tLabel
      }
    });
  }
  qrItems.push({
    type: "action",
    action: {
      type: "location",
      label: "📍 ปักหมุดแผนที่แทน"
    }
  });

  var cardBtns = [];
  for (var b = 0; b < Math.min(tambons.length, 3); b++) {
    var bLabel = subPref + tambons[b];
    cardBtns.push({
      type: "button",
      style: "primary",
      color: "#059669",
      height: "sm",
      margin: "xs",
      action: {
        type: "message",
        label: ("📍 " + bLabel).slice(0, 20),
        text: "เลือกตำบล: " + bLabel
      }
    });
  }
  cardBtns.push({
    type: "button",
    style: "primary",
    color: "#0284c7",
    height: "sm",
    margin: "sm",
    action: {
      type: "postback",
      label: "✍️ พิมพ์ชื่อตำบล",
      data: "action=fill_tambon_name",
      inputOption: "openKeyboard",
      fillInText: subPref
    }
  });

  var tambonListHint = tambons.length > 0
    ? ("ตำบลในรหัส " + zip + ": " + tambons.map(function(x) { return subPref + x; }).join(", "))
    : "กรุณาระบุ ตำบล/แขวง เพื่อให้ขนส่งจัดส่งถึงบ้านค่ะ";

  return {
    type: "flex",
    altText: "กรุณาเลือกหรือพิมพ์ ตำบล/แขวง",
    quickReply: { items: qrItems },
    contents: {
      type: "bubble",
      size: "mega",
      header: {
        type: "box",
        layout: "vertical",
        backgroundColor: "#d97706",
        paddingAll: "12px",
        contents: [
          { type: "text", text: "📍 ระบุ ตำบล/แขวง เพิ่มเติมค่ะ", color: "#ffffff", size: "md", weight: "bold" }
        ]
      },
      body: {
        type: "box",
        layout: "vertical",
        paddingAll: "14px",
        spacing: "xs",
        contents: [
          { type: "text", text: "🏠 " + addr, size: "xs", weight: "bold", color: "#0f172a", wrap: true },
          { type: "text", text: tambonListHint, size: "xs", color: "#475569", wrap: true, margin: "xs" },
          { type: "text", text: "👇 กดเลือกตำบลด้านล่าง หรือกดปุ่มพิมพ์ชื่อตำบล:", size: "xs", weight: "bold", color: "#b45309", wrap: true, margin: "xs" }
        ].concat(cardBtns)
      }
    }
  };
}

/**
 * เครื่องมือรับพิกัดแผนที่จากปุ่ม "📍 ปักหมุดที่อยู่" ใน LINE (ดึง ตำบล + อำเภอ + จังหวัด + รหัสไปรษณีย์ ครบ 100%)
 */
function handleLocationMessage(event) {
  const replyToken = event.replyToken;
  const userId = (event.source && event.source.userId) || "";
  const msg = event.message || {};
  const lat = msg.latitude;
  const lng = msg.longitude;
  let mapAddress = (msg.address || msg.title || "").trim();

  // 1. ดึง ตำบล + อำเภอ + จังหวัด + รหัสไปรษณีย์ จาก OpenStreetMap Nominatim + THAI_ZIP_DB
  if (lat && lng) {
    try {
      var nomUrl = "https://nominatim.openstreetmap.org/reverse?format=json&lat=" + encodeURIComponent(lat) + "&lon=" + encodeURIComponent(lng) + "&addressdetails=1&accept-language=th";
      var nomRes = UrlFetchApp.fetch(nomUrl, {
        headers: { "User-Agent": "PakhemFishBot/1.0" },
        muteHttpExceptions: true
      });
      if (nomRes.getResponseCode() === 200) {
        var nomData = JSON.parse(nomRes.getContentText());
        var a = (nomData && nomData.address) || {};
        var road = (a.road || a.soi || "").trim();
        var sub = (a.suburb || a.tambon || a.village || a.quarter || a.hamlet || a.town || "").replace(/^(?:ตำบล|ต\.|แขวง|เทศบาลตำบล|องค์การบริหารส่วนตำบล)\s*/, "").trim();
        var dist = (a.city_district || a.amphoe || a.county || a.municipality || a.city || "").replace(/^(?:อำเภอ|อ\.|เขต|องค์การบริหารส่วนตำบล|เทศบาล)\s*/, "").trim();
        var prov = (a.state || a.province || a.city || "").replace(/^(?:จังหวัด|จ\.)\s*/, "").trim();
        var zip = (a.postcode || "").replace(/\D/g, "").slice(0, 5);
        var zInfo = zip ? lookupThaiZipCodeInfo(zip) : null;
        if (zInfo) {
          dist = zInfo.amphoe;
          prov = zInfo.province;
          if (!sub && zInfo.tambons.length === 1) sub = zInfo.tambons[0];
        }
        var isBkk = prov === "กรุงเทพมหานคร";
        var parts = [];
        if (road) parts.push(road);
        if (sub) parts.push((isBkk ? "แขวง" : "ต.") + sub);
        if (dist) parts.push((isBkk ? "เขต" : "อ.") + dist);
        if (prov) parts.push((isBkk ? "" : "จ.") + prov);
        if (zip) parts.push(zip);
        var builtNom = parts.join(" ").trim();
        if (builtNom.length >= 10) {
          mapAddress = builtNom;
        }
      }
    } catch (ne) {
      Logger.log("Nominatim reverse geocode error: " + ne);
    }

    // 2. Fallback Google Maps Reverse Geocoder หากยังไม่มีตำบล/อำเภอ
    if (!hasCompleteThaiAddress(mapAddress)) {
      try {
        var rev = Maps.newGeocoder().setLanguage("th").reverseGeocode(lat, lng);
        if (rev && rev.status === "OK" && rev.results && rev.results.length > 0) {
          var bestAddr = rev.results[0].formatted_address || "";
          if (bestAddr.length > mapAddress.length) {
            mapAddress = bestAddr;
          }
        }
      } catch (e) {
        Logger.log("Reverse geocode error: " + e);
      }
    }
  }

  if (!mapAddress) {
    mapAddress = "พิกัด GPS (" + lat + ", " + lng + ")";
  }
  const cleanMapAddr = enrichThaiAddressWithMaps(
    mapAddress
      .replace(/[A-Z0-9]{4,8}\+[A-Z0-9]{2,4}\s*/gi, "")
      .replace(/ประเทศไทย/g, "")
      .replace(/^[,\s]+|[,\s]+$/g, "")
      .trim()
  );

  const ctx = getUserOrderContext(userId);
  const routeInfo = calculateShippingRouteInfo(cleanMapAddr, lat, lng);
  const combinedFromPin = ctx.savedHouseNo ? (ctx.savedHouseNo + " " + cleanMapAddr) : cleanMapAddr;
  saveUserOrderContext(userId, {
    savedAddress: combinedFromPin,
    distanceKm: routeInfo.distanceKm,
    estDays: routeInfo.estDays,
    allowCod: routeInfo.allowCod,
    houseFilled: !!ctx.savedHouseNo,
    waitingTambon: false
  });
  const updatedPinCtx = getUserOrderContext(userId);

  // หากลูกค้ากรอกบ้านเลขที่ไว้ก่อนปักหมุดแล้ว ให้ข้ามไปขั้นถัดไปทันที!
  if (ctx.savedHouseNo) {
    event.message.text = combinedFromPin;
    handleTextMessage(event);
    return;
  }

  // ขั้นที่ 2/5 : แจ้งระยะทาง (กม.) + ใช้เวลากี่วันถึง + นำทางกดเลือก "โอนชำระเงิน" หรือ "เก็บเงินปลายทาง" ทันที!
  if (!updatedPinCtx.payMode) {
    replyLine(replyToken, [buildFinalPaymentConfirmCard(updatedPinCtx, "2/5")]);
    return;
  }

  // หากเลือกวิธีชำระเงินไว้แล้ว ให้เด้งการ์ด 3/5 กรอกบ้านเลขที่
  const pinFlexCard = buildHouseNumberStepCard(cleanMapAddr, routeInfo, updatedPinCtx);
  replyLine(replyToken, [pinFlexCard]);
}

function buildHouseNumberStepCard(areaText, routeInfo, ctx) {
  var rInfo = routeInfo || calculateShippingRouteInfo(areaText);
  var hasSubAlready = /(?:ต\.|ตำบล|แขวง)/.test(areaText || "");
  var headerTitle = hasSubAlready ? "🏠 3/5 : กรอกบ้านเลขที่" : "🏠 3/5 : บ้านเลขที่ & ตำบล";
  var btnLabel = hasSubAlready ? "✍️ กดกรอกบ้านเลขที่" : "✍️ กรอกบ้านเลขที่+ตำบล";
  var bodyItems = [
    { type: "text", text: "📍 " + areaText, size: "xs", color: "#0369a1", weight: "bold", wrap: true },
    { type: "text", text: rInfo.summaryLine, size: "xs", color: "#059669", weight: "bold", wrap: true }
  ];
  if (!hasSubAlready) {
    bodyItems.push({
      type: "text",
      text: "💡 พิมพ์บ้านเลขที่ หมู่/ซอย (ระบบมีปุ่มให้เลือกตำบลต่อค่ะ)",
      size: "xxs",
      color: "#64748b",
      wrap: true
    });
  }
  bodyItems.push({
    type: "button",
    style: "primary",
    color: "#059669",
    height: "sm",
    margin: "md",
    action: {
      type: "postback",
      label: btnLabel,
      data: "action=fill_house_after_pin",
      inputOption: "openKeyboard",
      fillInText: "บ้านเลขที่: "
    }
  });
  return {
    type: "flex",
    altText: headerTitle,
    quickReply: getFinalAddressStepQuickReply(ctx && (ctx.payMode === "TRANSFER" || ctx.payMode === "COLD_TRUCK"), false),
    contents: {
      type: "bubble",
      size: "mega",
      header: {
        type: "box",
        layout: "vertical",
        backgroundColor: "#0284c7",
        paddingAll: "12px",
        contents: [
          { type: "text", text: headerTitle, color: "#ffffff", size: "md", weight: "bold" }
        ]
      },
      body: {
        type: "box",
        layout: "vertical",
        paddingAll: "14px",
        spacing: "xs",
        contents: bodyItems
      }
    }
  };
}

function extractOrderDetails(text, userId) {
  if (!text) return null;
  // หากเป็นคำสั่งเลือกตำบล หรือขั้นตอนย่อยที่ไม่มีเบอร์โทร ให้ข้ามไปเข้าตัวจัดการเฉพาะขั้นทันที
  if (/^(?:เลือกตำบล|ตำบล)\s*[:：-]/i.test(text.trim())) {
    return null;
  }
  const ctx = getUserOrderContext(userId);

  // 0. กรณีลูกค้ากดปุ่ม "✅ ใช้ที่อยู่เดิม"
  if (text.trim() === "ยืนยันใช้ที่อยู่เดิม" && ctx.savedAddress && ctx.savedPhone) {
    text = (ctx.savedName ? "ชื่อผู้รับ: " + ctx.savedName + " " : "") + ctx.savedAddress + " โทร " + ctx.savedPhone;
  }

  // 1. ตรวจหาเบอร์โทรศัพท์ในข้อความปัจจุบัน หรือเบอร์ที่ลูกค้าเพิ่งพิมพ์ส่งมาก่อนหน้า (ต้องครบ 10 หลักจริง ไม่ใช่เบอร์ตัวอย่าง/เกินหลัก)
  const phoneMatch = text.match(/(?:^|[^\d])(0[2689]\d{1}[-\s]?\d{3}[-\s]?\d{4}|0[2689]\d{2}[-\s]?\d{3}[-\s]?\d{3}|0[2689]\d{8})(?!\d)/);
  const currentPhone = phoneMatch ? phoneMatch[1].replace(/[-\s]/g, "") : "";
  const phone = currentPhone || ctx.savedPhone || "";

  // หากยังไม่มีเบอร์โทรศัพท์เลย หรือเบอร์โทรไม่ผ่านเกณฑ์มาตรฐาน 10 หลัก ยังไม่ถือเป็นการปิดจบออเดอร์
  if (!phone || !validateThaiPhoneNumber(phone).valid) {
    return null;
  }

  // 2. ตรวจหาชื่อผู้รับในข้อความ หรือจาก ctx.savedName
  let recipientName = ctx.savedName || "";
  if (!recipientName) {
    const namePrefixMatch = text.match(/(?:ชื่อผู้รับ|ชื่อ-นามสกุล|ชื่อ)\s*[:：-]?\s*([^\n0-9,]{1,40})/);
    if (namePrefixMatch && namePrefixMatch[1]) {
      recipientName = namePrefixMatch[1].replace(/(?:บ้านเลขที่|ที่อยู่|โทร|เบอร์).*$/i, "").trim();
    }
  }

  // 3. ตรวจหาคำระบุที่อยู่ในข้อความปัจจุบัน หรือที่อยู่ที่ดึงมาจากหมุดแผนที่ (ctx.savedAddress)
  const hasAddressKeywords = /(?:บ้านเลขที่|ต\.|อ\.|จ\.|ตำบล|อำเภอ|จังหวัด|แขวง|เขต|กทม|กรุงเทพ|ถนน|ถ\.|ซอย|ซ\.|ม\.|หมู่ที่|หมู่|คอนโด|อาคาร|ห้อง|\b\d{5}\b|\d+\/\d+)/.test(text);
  const textWithoutPhone = currentPhone ? text.replace(phoneMatch[0], "").trim() : text.trim();
  const currentHasAddress = hasAddressKeywords || (currentPhone && textWithoutPhone.length >= 10) || (!currentPhone && hasAddressKeywords && text.trim().length >= 8);

  let fullAddressText = "";
  if (ctx.savedAddress && text.indexOf(ctx.savedAddress) !== -1) {
    fullAddressText = ctx.savedAddress;
  } else if (ctx.savedAddress && currentPhone && textWithoutPhone.length > 0 && text.indexOf(ctx.savedAddress) === -1 && !/^(?:เบอร์โทรศัพท์|เบอร์โทร|เบอร์|โทร|ชื่อผู้รับ)/.test(text.trim())) {
    fullAddressText = textWithoutPhone + " " + ctx.savedAddress;
  } else if (currentHasAddress && ctx.savedAddress && !currentPhone && text.indexOf(ctx.savedAddress) === -1) {
    fullAddressText = text.trim() + " " + ctx.savedAddress;
  } else if (currentHasAddress) {
    fullAddressText = text.trim();
  } else if (ctx.savedAddress && currentPhone) {
    fullAddressText = ctx.savedAddress;
  }
  if (fullAddressText) {
    fullAddressText = enrichThaiAddressWithMaps(fullAddressText);
  }

  // บังคับต้องมี ตำบล/แขวง + อำเภอ/เขต + จังหวัด + เบอร์โทร 10 หลัก ครบ 100% ทุกช่องทาง จึงจะเปิดบิลได้!
  const addressIsComplete = hasCompleteThaiAddress(fullAddressText);
  const isLineUser = !!(userId && /^U[0-9a-f]{32}$/i.test(String(userId)));
  if (!phone || !validateThaiPhoneNumber(phone).valid || !fullAddressText || !addressIsComplete || (isLineUser && (!recipientName || (!ctx.payMode && !/(โอน|ปลายทาง|cod|รถเย็น|รถห้องเย็น)/i.test(text) && !ctx.slipUrl)))) {
    if (userId && (phone || fullAddressText || recipientName)) {
      const rInfo = calculateShippingRouteInfo(fullAddressText || "");
      saveUserOrderContext(userId, {
        savedAddress: fullAddressText || ctx.savedAddress || "",
        savedName: recipientName || ctx.savedName || "",
        savedPhone: (phone && validateThaiPhoneNumber(phone).valid) ? phone : (ctx.savedPhone || ""),
        distanceKm: rInfo.distanceKm,
        estDays: rInfo.estDays,
        allowCod: rInfo.allowCod,
        houseFilled: !!fullAddressText,
        waitingTambon: !!(fullAddressText && !addressIsComplete)
      });
    }
    return null;
  }

  if (phone && fullAddressText && addressIsComplete) {
    const combinedText = fullAddressText + " " + text;

    let packageCode = ctx.packageCode || "SKU-SLID-MD-1KG";
    const wantsColdTruck = (ctx.payMode === "COLD_TRUCK") || /(รถเย็น|รถห้องเย็น|scg|inter\s*express)/i.test(combinedText);

    if (/(2\s*(กิโล|กก\.?|kg|โล)|สองกิโล|สองโล|10-14\s*ตัว|1,?090|ตุนสุดคุ้ม)/i.test(combinedText)) {
      packageCode = "SKU-SLID-MD-2KG";
    } else if (/(500\s*(กรัม|g)|ครึ่งกิโล|ครึ่งโล|0\.5|[234]-\d\s*ตัว|390|410|พอดีมื้อ|ชุดเล็ก)/i.test(combinedText)) {
      packageCode = "SKU-SLID-MD-500G";
    } else if (/(1\s*(กิโล|กก\.?|kg|โล)|หนึ่งกิโล|โลนึง|[4567]-\d\s*ตัว|550|570|ยอดฮิต)/i.test(combinedText)) {
      packageCode = "SKU-SLID-MD-1KG";
    }

    let packageChosen = "";
    let price = 550;
    if (packageCode === "SKU-SLID-MD-2KG") {
      packageChosen = "ชุดตุนสุดคุ้ม 2 กิโลกรัม (ประมาณ 8–12 ตัวใหญ่) - 1,090.- (ส่งฟรีรถห้องเย็นควบคุมอุณหภูมิ)";
      price = 1090;
    } else if (packageCode === "SKU-SLID-MD-500G") {
      if (wantsColdTruck) {
        packageChosen = "ชุดพอดีมื้อ 500 กรัม (ประมาณ 2–3 ตัวใหญ่) - 390.- (+อัปเกรดรถห้องเย็น 100.- รวม 490.-)";
        price = 490;
      } else {
        packageChosen = "ชุดพอดีมื้อ 500 กรัม (ประมาณ 2–3 ตัวใหญ่) - 390.- (ส่งฟรีแพ็กซองฟอยล์เก็บอุณหภูมิ)";
        price = 390;
      }
    } else {
      if (wantsColdTruck) {
        packageChosen = "ชุดยอดฮิต 1 กิโลกรัม (ประมาณ 4–6 ตัวใหญ่) - 550.- (+อัปเกรดรถห้องเย็น 100.- รวม 650.-)";
        price = 650;
      } else {
        packageChosen = "ชุดยอดฮิต 1 กิโลกรัม (ประมาณ 4–6 ตัวใหญ่) - 550.- (ส่งฟรีแพ็กซองฟอยล์เก็บอุณหภูมิ)";
        price = 550;
      }
    }

    const explicitCOD = (ctx.payMode === "COD") || /(ปลายทาง|เก็บเงินปลายทาง|cod|จ่ายหน้าบ้าน)/i.test(combinedText);
    const explicitTransfer = (ctx.payMode === "TRANSFER" || ctx.payMode === "COLD_TRUCK") || /(โอน|สลิป|พร้อมเพย์|จ่ายแล้ว)/i.test(combinedText) || !!ctx.slipUrl;
    let isTransfer = explicitTransfer || !explicitCOD;
    if (explicitCOD && !/(โอน|สลิป)/i.test(text) && ctx.payMode === "COD") {
      isTransfer = false;
    }

    let paymentMethod = isTransfer ? "โอนเงินผ่านธนาคาร 🏦 (ส่งฟรี!)" : "เก็บเงินปลายทาง (COD +20.-) 💵";
    if (packageCode === "SKU-SLID-MD-2KG" || wantsColdTruck) {
      isTransfer = true;
      paymentMethod = "โอนเงินผ่านธนาคาร 🏦 (จัดส่งรถห้องเย็น — รับเฉพาะโอนเงินล่วงหน้า)";
    } else if (!isTransfer) {
      price += 20;
      packageChosen = packageChosen + " [+ค่าบริการ COD 20.- รวม " + price + ".-]";
    }

    return {
      packageCode: packageCode,
      recipientName: recipientName,
      phone: phone,
      package: packageChosen,
      price: price,
      paymentMethod: paymentMethod,
      slipUrl: ctx.slipUrl || "",
      fullText: fullAddressText
    };
  }
  return null;
}

function handleOrderStatusLookup(queryText, replyToken, userId) {
  var clean = queryText.trim();
  var orderMatch = clean.match(/PKF-?[A-Za-z0-9]+/i);
  var phoneMatch = clean.match(/0[2689]\d{1}[-\s]?\d{3}[-\s]?\d{4}|0[2689]\d{8}/);
  var trackInputMatch = clean.match(/(?:เช็คเลขพัสดุ|เลขพัสดุ|รหัสพัสดุ)\s*[:：-]?\s*([A-Za-z0-9-]{5,30})/i);
  var isAskTracking = ["เช็คพัสดุ", "ติดตามพัสดุ", "เลขพัสดุ", "ของถึงไหน", "สถานะพัสดุ", "เช็คสถานะ", "ทวง", "ทวงปลา", "ทวงของ", "ตามปลา", "ตามของ", "ยังไม่ได้ปลา", "ยังไม่ได้ของ", "ยังไม่ได้รับ", "ปลาถึงไหน", "ของยังไม่ถึง", "ปลายังไม่ถึง"].some(function(k) {
    return clean.toLowerCase().indexOf(k) !== -1;
  });

  var searchParam = "";
  var explicitQuery = "";
  if (orderMatch) {
    var rawCode = orderMatch[0].toUpperCase();
    if (!rawCode.startsWith("PKF-")) rawCode = "PKF-" + rawCode.replace("PKF", "");
    searchParam = "order_code=ilike." + encodeURIComponent(rawCode);
    explicitQuery = rawCode;
  } else if (phoneMatch) {
    var cleanPhoneLookup = phoneMatch[0].replace(/[-\s]/g, "");
    var dashedPhoneLookup = cleanPhoneLookup.slice(0, 3) + "-" + cleanPhoneLookup.slice(3, 6) + "-" + cleanPhoneLookup.slice(6);
    searchParam = "or=(phone.eq." + encodeURIComponent(cleanPhoneLookup) + ",phone.eq." + encodeURIComponent(dashedPhoneLookup) + ")";
    explicitQuery = cleanPhoneLookup;
  } else if (trackInputMatch && trackInputMatch[1]) {
    var tCode = trackInputMatch[1].trim();
    searchParam = "or=(tracking_number.ilike.*" + encodeURIComponent(tCode) + "*,order_code.ilike.*" + encodeURIComponent(tCode) + "*)";
    explicitQuery = tCode;
  } else if (isAskTracking && userId) {
    searchParam = "note=ilike.*" + encodeURIComponent("LINE_UID:" + userId) + "*";
  }

  if (searchParam) {
    try {
      var url = SUPABASE_URL + "/rest/v1/direct_orders?" + searchParam + "&order=created_at.desc&limit=1";
      var res = UrlFetchApp.fetch(url, {
        headers: { "apikey": SUPABASE_KEY, "Authorization": "Bearer " + SUPABASE_KEY },
        muteHttpExceptions: true
      });
      if (res.getResponseCode() === 200) {
        var list = JSON.parse(res.getContentText());
        if (list && list.length > 0) {
          var o = list[0];
          var statusBadge = "⏳ กำลังเตรียมจัดส่ง";
          if (o.status === "CONFIRMED") statusBadge = "✅ ยืนยันแล้ว (กำลังแพ็คซีลสูญญากาศ)";
          else if (o.status === "SHIPPED") statusBadge = "🚚 จัดส่งแล้ว";
          else if (o.status === "DELIVERED") statusBadge = "🎉 จัดส่งสำเร็จ";
          else if (o.status === "CANCELLED") statusBadge = "❌ ยกเลิกออเดอร์";

          var trackText = o.tracking_number ? ("🚚 เลขพัสดุ: " + o.tracking_number) : "📦 รอตัดรอบขนส่ง (แจ้งเลขพัสดุอัตโนมัติเมื่อส่งออก)";
          var cardBtns = [];
          if (o.tracking_number) {
            cardBtns.push({
              type: "button",
              style: "primary",
              color: "#0284c7",
              height: "sm",
              margin: "sm",
              action: {
                type: "clipboard",
                label: "📋 คัดลอกเลขพัสดุ",
                clipboardText: String(o.tracking_number)
              }
            });
          }
          if (o.payment_method === "TRANSFER" && !o.slip_verified) {
            cardBtns.push({
              type: "button",
              style: "primary",
              color: "#2563eb",
              height: "sm",
              margin: "sm",
              action: {
                type: "clipboard",
                label: "📋 คัดลอกเลขบัญชี",
                clipboardText: "0380253631"
              }
            });
          }
          cardBtns.push({
            type: "button",
            style: "secondary",
            height: "sm",
            margin: "sm",
            action: {
              type: "postback",
              label: "📞 เช็คด้วยเบอร์โทร",
              data: "action=check_tracking_phone",
              inputOption: "openKeyboard",
              fillInText: "เช็คพัสดุ เบอร์โทร: "
            }
          });
          cardBtns.push({
            type: "button",
            style: "secondary",
            height: "sm",
            margin: "sm",
            action: {
              type: "postback",
              label: "📦 เช็คด้วยเลขพัสดุ",
              data: "action=check_tracking_code",
              inputOption: "openKeyboard",
              fillInText: "เช็คเลขพัสดุ: "
            }
          });

          var statusCard = {
            type: "flex",
            altText: "สถานะคำสั่งซื้อ " + o.order_code,
            quickReply: getMasterQuickReply(),
            contents: {
              type: "bubble",
              size: "mega",
              header: {
                type: "box",
                layout: "vertical",
                backgroundColor: "#0f172a",
                paddingAll: "12px",
                contents: [
                  { type: "text", text: "📦 สถานะคำสั่งซื้อ " + o.order_code, color: "#34d399", size: "sm", weight: "bold" }
                ]
              },
              body: {
                type: "box",
                layout: "vertical",
                paddingAll: "14px",
                spacing: "xs",
                contents: [
                  { type: "text", text: "👤 ผู้รับ: " + (o.customer_name || "-") + " (" + (o.phone || "-") + ")", size: "xs", weight: "bold", color: "#0f172a", wrap: true },
                  { type: "text", text: "🐟 " + (o.package_name || "-"), size: "xs", color: "#334155", wrap: true },
                  { type: "text", text: "📊 สถานะ: " + statusBadge, size: "xs", weight: "bold", color: "#059669", wrap: true, margin: "xs" },
                  { type: "text", text: trackText, size: "xs", weight: "bold", color: "#0284c7", wrap: true }
                ].concat(cardBtns)
              }
            }
          };

          replyLine(replyToken, [statusCard]);
          return true;
        } else if (explicitQuery) {
          var notFoundCard = {
            type: "flex",
            altText: "ไม่พบคำสั่งซื้อของ " + explicitQuery,
            quickReply: getMasterQuickReply(),
            contents: {
              type: "bubble",
              size: "mega",
              header: {
                type: "box",
                layout: "vertical",
                backgroundColor: "#b91c1c",
                paddingAll: "12px",
                contents: [
                  { type: "text", text: "❌ ไม่พบออเดอร์ของ " + explicitQuery, color: "#ffffff", size: "sm", weight: "bold" }
                ]
              },
              body: {
                type: "box",
                layout: "vertical",
                paddingAll: "14px",
                spacing: "sm",
                contents: [
                  { type: "text", text: "เลือกเช็คด้วย เบอร์โทรศัพท์ผู้รับ หรือ เลขพัสดุ/รหัสสั่งซื้อ:", size: "xs", color: "#334155", wrap: true },
                  {
                    type: "button",
                    style: "primary",
                    color: "#0284c7",
                    height: "sm",
                    action: {
                      type: "postback",
                      label: "📞 เช็คด้วยเบอร์โทร",
                      data: "action=check_tracking_phone",
                      inputOption: "openKeyboard",
                      fillInText: "เช็คพัสดุ เบอร์โทร: "
                    }
                  },
                  {
                    type: "button",
                    style: "secondary",
                    height: "sm",
                    action: {
                      type: "postback",
                      label: "📦 เช็คด้วยเลขพัสดุ",
                      data: "action=check_tracking_code",
                      inputOption: "openKeyboard",
                      fillInText: "เช็คเลขพัสดุ: "
                    }
                  },
                  {
                    type: "button",
                    style: "primary",
                    color: "#059669",
                    height: "sm",
                    action: {
                      type: "message",
                      label: "🐟 สั่งปลาสลิด 1 กก.",
                      text: "สั่งซื้อปลาแดดเดียว 1 กิโลกรัม"
                    }
                  }
                ]
              }
            }
          };
          replyLine(replyToken, [notFoundCard]);
          return true;
        }
      }
    } catch (e) {
      Logger.log("Order status lookup error: " + e);
    }
  }

  if (isAskTracking) {
    var trackingPromptCard = {
      type: "flex",
      altText: "เช็คพัสดุ & บัญชีโอนเงิน",
      quickReply: getMasterQuickReply(),
      contents: {
        type: "bubble",
        size: "mega",
        header: {
          type: "box",
          layout: "vertical",
          backgroundColor: "#0f172a",
          paddingAll: "12px",
          contents: [
            { type: "text", text: "📦 เช็คพัสดุ & บัญชีโอนเงิน", color: "#ffffff", size: "md", weight: "bold" }
          ]
        },
        body: {
          type: "box",
          layout: "vertical",
          paddingAll: "14px",
          spacing: "sm",
          contents: [
            { type: "text", text: "🏦 ธ.กรุงไทย 038-0-25363-1 (นายจีรวัฒน์ พลอาจ)", size: "xs", weight: "bold", color: "#1d4ed8", wrap: true },
            { type: "text", text: "📸 โอนแล้วส่งรูปสลิปในแชทนี้ได้เลยค่ะ", size: "xs", color: "#475569", wrap: true },
            {
              type: "button",
              style: "primary",
              color: "#0284c7",
              height: "sm",
              margin: "sm",
              action: {
                type: "postback",
                label: "📞 เช็คด้วยเบอร์โทร",
                data: "action=check_tracking_phone",
                inputOption: "openKeyboard",
                fillInText: "เช็คพัสดุ เบอร์โทร: "
              }
            },
            {
              type: "button",
              style: "secondary",
              height: "sm",
              margin: "sm",
              action: {
                type: "postback",
                label: "📦 เช็คด้วยเลขพัสดุ",
                data: "action=check_tracking_code",
                inputOption: "openKeyboard",
                fillInText: "เช็คเลขพัสดุ: "
              }
            },
            {
              type: "button",
              style: "primary",
              color: "#2563eb",
              height: "sm",
              margin: "sm",
              action: {
                type: "clipboard",
                label: "📋 คัดลอกเลขบัญชี",
                clipboardText: "0380253631"
              }
            }
          ]
        }
      }
    };

    replyLine(replyToken, [trackingPromptCard]);
    return true;
  }

  return false;
}

function handleTextMessage(event) {
  const userText = (event.message.text || "").trim();
  const lowerText = userText.toLowerCase();
  const replyToken = event.replyToken;
  const userId = (event.source && event.source.userId) || "";
  const customerName = getUserDisplayName(userId);
  const nowStr = new Date().toLocaleString("th-TH", { timeZone: "Asia/Bangkok" });

  // 0. ตรวจสอบคำสั่งรายงานสถานะระบบแบบ Bullet Points (สำหรับแอดมิน/เจ้าของร้าน)
  const statusKeywords = ["สถานะ", "เช็คระบบ", "รายงาน", "status", "/status", "ตรวจระบบ", "เช็คบอท", "บอททำงานไหม"];
  if (statusKeywords.some(k => lowerText === k || lowerText === "/" + k)) {
    const statusMsg = 
      "📊 [รายงานสถานะระบบป้าเข็ม D2C 24/7]\n" +
      "━━━━━━━━━━━━━━━━━━\n" +
      "⏰ เวลาอัปเดต: " + nowStr + " น.\n\n" +
      "🟢 สถานะบริการอัตโนมัติ (ขายสินค้าตัวเอง 100%):\n" +
      "  • 🤖 LINE OA Webhook: 🟢 ออนไลน์ 24 ชม. (Google Apps Script @23)\n" +
      "  • 🐟 สินค้าหลัก: ปลาแดดเดียว ป้าเข็ม คัดพิเศษ (สูตรโบราณ)\n" +
      "  • 🧠 ปัญญาประดิษฐ์ปิดการขาย: 🟢 ออนไลน์ (Autonomous Sales Closer)\n" +
      "  • 🛒 ระบบรับออเดอร์ในแชท: 🟢 อัตโนมัติ (ดักจับชื่อ-ที่อยู่-เบอร์โทร)\n" +
      "  • 🔔 แจ้งเตือนยอดขาย: 🟢 Real-time Telegram Commander\n" +
      "━━━━━━━━━━━━━━━━━━\n" +
      "✨ บอททำงานแทนผู้ใช้ 100% รับออเดอร์และตอบลูกค้าตลอด 24 ชม. จ้า!";
    replyLine(replyToken, [{ type: "text", text: statusMsg }]);
    return;
  }


  const isPaySelectCmd = lowerText.startsWith("เลือกโอนเงิน") || lowerText.startsWith("เลือกเก็บปลายทาง") || lowerText.startsWith("เลือกส่งรถห้องเย็น");

  // 0.7 ลูกค้ากดเลือกแพ็กเกจจาก Rich Menu -> เริ่มขั้นที่ 1/5 (ปักหมุดแผนที่ หรือ รหัสไปรษณีย์) ตามลำดับทันที!
  const order1kgDirect = ["สั่งซื้อปลาแดดเดียว 1 กิโลกรัม", "สั่งปลา 1 กิโล", "รับ 1 กิโล", "รับชุด 1 กก", "ชุด 1 กิโล", "ชุด 1 กก"];
  if (!isPaySelectCmd && order1kgDirect.some(k => lowerText === k || (lowerText.includes(k) && userText.length <= 40))) {
    const prevOrd1 = lookupPreviousOrderAddress(userId, "");
    const hasPrev1 = !!(prevOrd1 && prevOrd1.address && prevOrd1.phone);
    var prevDisplay1 = hasPrev1 ? ((prevOrd1.customer_name ? "👤 " + prevOrd1.customer_name + " (" + prevOrd1.phone + ")\n" : "📞 " + prevOrd1.phone + "\n") + "📍 " + prevOrd1.address) : "";
    var patch1 = { packageCode: "SKU-SLID-MD-1KG", payMode: null, waitingTambon: false };
    saveUserOrderContext(userId, patch1);
    replyLine(replyToken, [
      buildStep2AddressGuideFlexMessage("ชุดยอดฮิต 1 กิโลกรัม (4–6 ตัวใหญ่)", "🏦 โอน 550.- ส่งฟรี! (งดรับ COD)", 550, true, hasPrev1, prevDisplay1)
    ]);
    return;
  }

  const order500gDirect = ["รับชุดพอดีมื้อ 500 กรัม", "สั่งปลา 500 กรัม", "รับ 500 กรัม", "ชุด 500 กรัม", "ครึ่งโล", "ครึ่งกิโล"];
  if (!isPaySelectCmd && order500gDirect.some(k => lowerText === k || (lowerText.includes(k) && userText.length <= 40))) {
    const prevOrd5 = lookupPreviousOrderAddress(userId, "");
    const hasPrev5 = !!(prevOrd5 && prevOrd5.address && prevOrd5.phone);
    var prevDisplay5 = hasPrev5 ? ((prevOrd5.customer_name ? "👤 " + prevOrd5.customer_name + " (" + prevOrd5.phone + ")\n" : "📞 " + prevOrd5.phone + "\n") + "📍 " + prevOrd5.address) : "";
    var patch5 = { packageCode: "SKU-SLID-MD-500G", payMode: null, waitingTambon: false };
    saveUserOrderContext(userId, patch5);
    replyLine(replyToken, [
      buildStep2AddressGuideFlexMessage("ชุดพอดีมื้อ 500 กรัม (2–3 ตัวใหญ่)", "🏦 โอน 390.- ส่งฟรี! (งดรับ COD)", 390, true, hasPrev5, prevDisplay5)
    ]);
    return;
  }

  const order2kgDirect = ["สั่งซื้อปลาแดดเดียว 2 กิโลกรัม", "สั่งปลา 2 กิโล", "รับ 2 กิโล", "ชุด 2 กิโล", "ชุด 2 กก"];
  if (!isPaySelectCmd && order2kgDirect.some(k => lowerText === k || (lowerText.includes(k) && userText.length <= 40))) {
    const prevOrd2 = lookupPreviousOrderAddress(userId, "");
    const hasPrev2 = !!(prevOrd2 && prevOrd2.address && prevOrd2.phone);
    var prevDisplay2 = hasPrev2 ? ((prevOrd2.customer_name ? "👤 " + prevOrd2.customer_name + " (" + prevOrd2.phone + ")\n" : "📞 " + prevOrd2.phone + "\n") + "📍 " + prevOrd2.address) : "";
    var patch2 = { packageCode: "SKU-SLID-MD-2KG", payMode: null, waitingTambon: false };
    saveUserOrderContext(userId, patch2);
    replyLine(replyToken, [
      buildStep2AddressGuideFlexMessage("ชุดตุนสุดคุ้ม 2 กิโลกรัม (8–12 ตัวใหญ่)", "❄️ โอน 1,090.- ส่งฟรีรถห้องเย็น!", 1090, true, hasPrev2, prevDisplay2)
    ]);
    return;
  }

  // 0.72 ลูกค้าเก่ากดปุ่ม "✅ ใช้ที่อยู่เดิม" -> คำนวณระยะทาง & วันถึง แล้วเด้งเลือกวิธีชำระเงินทันที!
  if (userText === "ยืนยันใช้ที่อยู่เดิม") {
    const prevSaved = lookupPreviousOrderAddress(userId, "");
    if (prevSaved && prevSaved.address && prevSaved.phone) {
      const prevRoute = calculateShippingRouteInfo(prevSaved.address);
      saveUserOrderContext(userId, {
        savedAddress: prevSaved.address,
        savedName: prevSaved.customer_name || customerName,
        savedPhone: prevSaved.phone,
        distanceKm: prevRoute.distanceKm,
        estDays: prevRoute.estDays,
        allowCod: prevRoute.allowCod,
        houseFilled: true
      });
      const updatedPrevCtx = getUserOrderContext(userId);
      replyLine(replyToken, [buildFinalPaymentConfirmCard(updatedPrevCtx, "5/5")]);
      return;
    }
  }

  // 0.75 ลูกค้ากดปุ่มเลือกวิธีชำระเงิน (เลือกโอนเงิน / เลือกเก็บปลายทาง / เลือกส่งรถห้องเย็น)
  if (lowerText.startsWith("เลือกโอนเงิน") || lowerText.startsWith("เลือกเก็บปลายทาง") || lowerText.startsWith("เลือกส่งรถห้องเย็น")) {
    const curCtx = getUserOrderContext(userId);
    let selPkg = curCtx.packageCode || "SKU-SLID-MD-1KG";
    if (lowerText.includes("500")) selPkg = "SKU-SLID-MD-500G";
    else if (lowerText.includes("2 กิโล")) selPkg = "SKU-SLID-MD-2KG";
    else if (lowerText.includes("1 กิโล")) selPkg = "SKU-SLID-MD-1KG";

    let chosenPayMode = "TRANSFER";
    if (lowerText.startsWith("เลือกเก็บปลายทาง")) chosenPayMode = "COD";
    else if (lowerText.startsWith("เลือกส่งรถห้องเย็น")) chosenPayMode = "COLD_TRUCK";

    saveUserOrderContext(userId, { packageCode: selPkg, payMode: chosenPayMode });
    const updatedCtx = getUserOrderContext(userId);

    // 1) ถ้ามีที่อยู่ + บ้านเลขที่ + ชื่อผู้รับ + เบอร์โทร ครบแล้ว -> ปิดจบออกรหัสสั่งซื้อ PKF-... ทันที!
    if (updatedCtx.savedAddress && updatedCtx.savedPhone && updatedCtx.savedName && updatedCtx.houseFilled !== false) {
      if (!hasCompleteThaiAddress(updatedCtx.savedAddress)) {
        saveUserOrderContext(userId, { waitingTambon: true });
        replyLine(replyToken, [buildTambonSelectCard(getUserOrderContext(userId))]);
        return;
      }
      event.message.text = "ชื่อผู้รับ: " + updatedCtx.savedName + " " + updatedCtx.savedAddress + " โทร " + updatedCtx.savedPhone + " (" + (chosenPayMode === "COD" ? "ปลายทาง" : (chosenPayMode === "COLD_TRUCK" ? "รถห้องเย็น" : "โอนเงิน")) + ")";
      handleTextMessage(event);
      return;
    }

    // 2) ถ้าปักหมุด/ใส่รหัสไปรษณีย์แล้ว (มี savedAddress) แต่ยังไม่ได้กรอกบ้านเลขที่ -> ไปขั้นที่ 3/5 กรอกบ้านเลขที่!
    if (updatedCtx.savedAddress && !updatedCtx.houseFilled) {
      const rInfoStep3 = calculateShippingRouteInfo(updatedCtx.savedAddress);
      replyLine(replyToken, [buildHouseNumberStepCard(updatedCtx.savedAddress, rInfoStep3, updatedCtx)]);
      return;
    }

    // 3) ถ้ามีบ้านเลขที่แล้ว แต่ยังไม่มีตำบล/แขวง -> เด้งเลือกตำบลทันที!
    if (updatedCtx.savedAddress && !hasCompleteThaiAddress(updatedCtx.savedAddress)) {
      saveUserOrderContext(userId, { waitingTambon: true });
      replyLine(replyToken, [buildTambonSelectCard(getUserOrderContext(userId))]);
      return;
    }

    // 4) ถ้ามีบ้านเลขที่+ตำบลครบแล้ว แต่ยังไม่มีชื่อผู้รับ -> ไปขั้นที่ 4/5 ชื่อผู้รับ!
    if (updatedCtx.savedAddress && !updatedCtx.savedName) {
      event.message.text = "บ้านเลขที่: " + updatedCtx.savedAddress;
      handleTextMessage(event);
      return;
    }

    // 4) ถ้ามีชื่อผู้รับแล้ว แต่ยังไม่มีเบอร์โทร -> ไปขั้นที่ 5/5 เบอร์โทร!
    if (updatedCtx.savedAddress && updatedCtx.savedName && !updatedCtx.savedPhone) {
      event.message.text = "ชื่อผู้รับ: " + updatedCtx.savedName;
      handleTextMessage(event);
      return;
    }

    let selName = selPkg === "SKU-SLID-MD-500G" ? "ชุดพอดีมื้อ 500 กรัม (2–3 ตัวใหญ่)" : (selPkg === "SKU-SLID-MD-2KG" ? "ชุดตุนสุดคุ้ม 2 กิโลกรัม (8–12 ตัวใหญ่)" : "ชุดยอดฮิต 1 กิโลกรัม (4–6 ตัวใหญ่)");
    let selPrice = selPkg === "SKU-SLID-MD-500G" ? 390 : (selPkg === "SKU-SLID-MD-2KG" ? 1090 : 550);
    if (chosenPayMode === "COD") selPrice += 20;
    else if (chosenPayMode === "COLD_TRUCK" && selPkg !== "SKU-SLID-MD-2KG") selPrice += 100;
    const payLabel = chosenPayMode === "COD" ? "🚚 เก็บเงินปลายทาง (COD)" : (chosenPayMode === "COLD_TRUCK" || selPkg === "SKU-SLID-MD-2KG" ? "❄️ โอนเงิน (ส่งรถห้องเย็น)" : "🏦 โอนเงิน (ส่งฟรี!)");
    const prevOrd = lookupPreviousOrderAddress(userId, "");
    const hasPrev = !!(prevOrd && prevOrd.address && prevOrd.phone);
    replyLine(replyToken, [
      buildStep2AddressGuideFlexMessage(selName, payLabel, selPrice, chosenPayMode !== "COD", hasPrev, hasPrev ? prevOrd.address : "")
    ]);
    return;
  }

  // 0.8 ระบบเกราะป้องกันโอนสายหาคนจริง (Human-in-the-Loop Escalation Guard)
  const humanKeywords = ["ติดต่อคน", "ขอคุยกับคน", "ขอมนุษย์", "พนักงานคนจริง", "แอดมินคน", "ไม่เอาบอท", "คุยไม่รู้เรื่อง", "คนจริง", "โทรหา", "ขอเบอร์โทร", "คุยกับคน"];
  if (humanKeywords.some(k => lowerText.includes(k))) {
    const selfCloseMsg = [
      "🐟 [ระบบสั่งซื้ออัตโนมัติ 24 ชม. — ป้าเข็ม ปลาสลิดแดดเดียวสุพรรณแท้]",
      "คุณลูกค้าสามารถทำรายการสั่งซื้อ เช็คพัสดุ หรือแจ้งโอนเงินในแชทนี้ได้ทันทีโดยไม่ต้องรอคิวค่ะ ✨",
      "━━━━━━━━━━━━━━━━━━",
      "📦 เลือกแพ็กเกจสุดคุ้ม (โอนเงินส่งฟรีทุกชุด!):",
      "  1️⃣ ชุดพอดีมื้อ 500 กรัม (2–3 ตัวใหญ่): โอน 390.- ส่งฟรี! (งดรับ COD)",
      "  2️⃣ ชุดยอดฮิต 1 กิโลกรัม (4–6 ตัวใหญ่): โอน 550.- ส่งฟรี! (งดรับ COD)",
      "  3️⃣ ชุดตุนสุดคุ้ม 2 กิโลกรัม (8–12 ตัวใหญ่): โอน 1,090.- ส่งฟรีรถห้องเย็น! (งด COD)",
      "",
      "🏦 บัญชีสำหรับโอนชำระเงิน:",
      "  • ธนาคารกรุงไทย: 038-0-25363-1 (นายจีรวัฒน์ พลอาจ)",
      "",
      "⚡ วิธีสั่งซื้อให้จบในแชทนี้ทันที (เลือกวิธีที่สะดวก):",
      "  • วิธีที่ 1: พิมพ์ [ชุดที่ต้องการ + ชื่อ-นามสกุล + ที่อยู่จัดส่ง + เบอร์โทรศัพท์ + โอนเงิน/ปลายทาง] ส่งในแชทนี้ ระบบจะออกรหัสคำสั่งซื้อให้ทันทีค่ะ",
      "  • วิธีที่ 2: กดปุ่ม '🛒 สั่งซื้อผ่านเว็บ' ด้านล่าง เพื่อกรอกฟอร์มสั่งซื้ออัตโนมัติได้เลยค่ะ 😊"
    ].join("\n");

    replyLine(replyToken, [{
      type: "text",
      text: selfCloseMsg,
      quickReply: getMasterQuickReply()
    }]);
    return;
  }

  // 0.9 ลูกค้ากดยกเลิกคำสั่งซื้อ / ยกเลิกออเดอร์ที่ยังไม่โอน
  if (/^(?:ยกเลิกคำสั่งซื้อ|ยกเลิกออเดอร์|ขอยกเลิก|ยกเลิกบิล)/i.test(userText.trim())) {
    const codeMatch = userText.match(/(PKF-[0-9A-Za-z-]+)/i);
    let cancelledCode = codeMatch ? codeMatch[1].toUpperCase() : "";
    try {
      let queryFilter = cancelledCode
        ? ("order_code=eq." + encodeURIComponent(cancelledCode))
        : ("note=ilike.*" + encodeURIComponent(userId) + "*&status=eq.PENDING");
      UrlFetchApp.fetch(SUPABASE_URL + "/rest/v1/direct_orders?" + queryFilter, {
        method: "patch",
        headers: {
          "apikey": SUPABASE_KEY,
          "Authorization": "Bearer " + SUPABASE_KEY,
          "Content-Type": "application/json",
          "Prefer": "return=minimal"
        },
        payload: JSON.stringify({ status: "CANCELLED" }),
        muteHttpExceptions: true
      });
      syncSupabaseToGoogleSheet();
    } catch (ce) {}
    saveUserOrderContext(userId, { packageCode: null, payMode: null, waitingTambon: false });
    replyLine(replyToken, [{
      type: "text",
      text: "✅ ยกเลิกคำสั่งซื้อ" + (cancelledCode ? " (" + cancelledCode + ")" : "") + " เรียบร้อยแล้วค่ะ\n(ระบบเก็บประวัติชื่อ-ที่อยู่ไว้ให้แล้ว หากต้องการสั่งใหม่หรือเปลี่ยนเป็นเก็บปลายทาง กดปุ่มด้านล่างได้ตลอดนะคะ 🙏💕)",
      quickReply: getMasterQuickReply()
    }]);
    pushAdminAlert("⚪ [ลูกค้ากดยกเลิกบิลที่ยังไม่โอนใน LINE]\n👤 ลูกค้า: " + customerName + (cancelledCode ? "\n🔖 รหัสบิล: " + cancelledCode : "") + "\n📌 ระบบย้ายเข้าหมวด '⚪ ยกเลิก/ไม่โอน' และเก็บประวัติในทะเบียนลูกค้า CRM แล้วค่ะ");
    return;
  }

  // 1. ตรวจสอบสถานะการจัดส่ง / เช็คเลขพัสดุ (เฉพาะเมื่อลูกค้าไม่ได้กำลังพิมพ์ที่อยู่สั่งซื้อ)
  const activeOrderCtx = getUserOrderContext(userId);
  const looksLikeNewOrderAddress = /(?:บ้านเลขที่|ต\.|อ\.|จ\.|ตำบล|อำเภอ|จังหวัด|แขวง|เขต|ถนน|ซอย|หมู่|\b\d{5}\b|\d+\/\d+|โอน|ปลายทาง|ยืนยันใช้ที่อยู่เดิม)/.test(userText);
  if (!looksLikeNewOrderAddress && !activeOrderCtx.packageCode && handleOrderStatusLookup(userText, replyToken, userId)) {
    return;
  }
  if (["เช็คพัสดุ", "ติดตามพัสดุ", "เลขพัสดุ", "ของถึงไหน", "สถานะพัสดุ", "เช็คสถานะ", "ทวง", "ทวงปลา", "ทวงของ", "ตามปลา", "ตามของ", "ยังไม่ได้ปลา", "ยังไม่ได้ของ", "ยังไม่ได้รับ", "ปลาถึงไหน", "ของยังไม่ถึง", "ปลายังไม่ถึง"].some(k => lowerText.includes(k)) || /PKF-?[A-Za-z0-9]+/i.test(userText)) {
    if (handleOrderStatusLookup(userText, replyToken, userId)) {
      return;
    }
  }

  // 1.5 ตรวจจับการส่งข้อมูลจัดส่ง / ที่อยู่ / สั่งซื้อในแชทอัตโนมัติ (Autonomous Address Extractor)
  const orderDetails = extractOrderDetails(userText, userId);
  if (orderDetails) {
    const orderCode = "PKF-" + Utilities.formatDate(new Date(), "Asia/Bangkok", "MMddHHmmss");
    const payMethodEnum = orderDetails.paymentMethod.includes("โอน") ? "TRANSFER" : "COD";
    const hasSlipAttached = !!(orderDetails.slipUrl);

    // บันทึกลง Supabase direct_orders ทันที
    try {
      var supaOrderPayload = {
        order_code: orderCode,
        product_name: "ปลาสลิดแดดเดียว ไซส์จัมโบ้ 4 ตัวโล คัดพิเศษ ป้าเข็ม คัดพิเศษ",
        package_code: orderDetails.packageCode || (orderDetails.price >= 800 ? "SKU-SLID-MD-2KG" : (orderDetails.price >= 450 ? "SKU-SLID-MD-1KG" : "SKU-SLID-MD-500G")),
        package_name: orderDetails.package,
        price: orderDetails.price,
        customer_name: orderDetails.recipientName || customerName,
        phone: orderDetails.phone,
        address: orderDetails.fullText,
        payment_method: payMethodEnum,
        status: "PENDING",
        slip_url: orderDetails.slipUrl || null,
        slip_verified: hasSlipAttached,
        note: "สั่งซื้อผ่านข้อความ LINE OA อัตโนมัติ [LINE_UID:" + userId + "]" + (hasSlipAttached ? " (แนบสลิปโอนเงินแล้ว)" : ""),
        created_at: new Date().toISOString()
      };
      UrlFetchApp.fetch(SUPABASE_URL + "/rest/v1/direct_orders", {
        method: "post",
        headers: {
          "apikey": SUPABASE_KEY,
          "Authorization": "Bearer " + SUPABASE_KEY,
          "Content-Type": "application/json",
          "Prefer": "return=minimal"
        },
        payload: JSON.stringify(supaOrderPayload),
        muteHttpExceptions: true
      });
      saveUserOrderContext(userId, {
        packageCode: null,
        payMode: null,
        savedName: orderDetails.recipientName || customerName,
        savedPhone: orderDetails.phone,
        savedAddress: orderDetails.fullText,
        houseFilled: true,
        waitingTambon: false,
        slipUrl: null,
        slipAmount: null
      });
      try {
        recordOrderToGoogleSheet(nowStr, Utilities.formatDate(new Date(), "Asia/Bangkok", "yyyy-MM-dd"), orderCode, orderDetails.package, orderDetails.recipientName || customerName, orderDetails.price, "LINE OA");
      } catch (ge) {}
    } catch (e) {
      Logger.log("Error saving chat order to direct_orders: " + e);
    }

    const receiptRoute = calculateShippingRouteInfo(orderDetails.fullText);
    const paymentNoteInReceipt = hasSlipAttached
      ? "\n✅ แนบสลิปโอนเงินแล้ว"
      : (payMethodEnum === "TRANSFER"
          ? "\n🏦 กรุงไทย 038-0-25363-1 (นายจีรวัฒน์ พลอาจ)\n📸 โอนแล้วส่งรูปสลิปในแชทนี้ได้เลยค่ะ"
          : "");

    const orderReceiptMsg =
      "✅ บันทึกคำสั่งซื้อสำเร็จ!\n" +
      "━━━━━━━━━━━━━━━━━━\n" +
      "🔖 รหัส: " + orderCode + "\n" +
      "📦 " + orderDetails.package + "\n" +
      "💵 ยอดชำระ: " + orderDetails.price.toLocaleString("th-TH") + " บาท (" + (payMethodEnum === "TRANSFER" ? "โอนส่งฟรี" : "เก็บปลายทาง") + ")\n" +
      "👤 ผู้รับ: " + (orderDetails.recipientName || customerName) + " (" + orderDetails.phone + ")\n" +
      "🏠 ที่อยู่: " + orderDetails.fullText + "\n" +
      receiptRoute.summaryLine + " (" + receiptRoute.shipMethodShort + ")" +
      paymentNoteInReceipt;

    var replyMsgs = [{
      type: "text",
      text: orderReceiptMsg,
      quickReply: getMasterQuickReply()
    }];

    if (payMethodEnum === "TRANSFER" && !hasSlipAttached) {
      replyMsgs.push({
        type: "flex",
        altText: "คัดลอกเลขบัญชีกรุงไทย 038-0-25363-1 และแนบสลิปโอนเงิน",
        quickReply: getMasterQuickReply(),
        contents: {
          type: "bubble",
          size: "mega",
          hero: {
            type: "image",
            url: "https://watt29.github.io/pakhem-shop/krungthai_promptpay_qr.png?v=20261030",
            size: "full",
            aspectRatio: "3:4",
            aspectMode: "fit",
            backgroundColor: "#ffffff"
          },
          header: {
            type: "box",
            layout: "vertical",
            backgroundColor: "#1d4ed8",
            paddingAll: "12px",
            contents: [
              { type: "text", text: "🏦 โอนชำระค่าสินค้า (" + orderDetails.price.toLocaleString("th-TH") + " บาท)", color: "#ffffff", size: "sm", weight: "bold" },
              { type: "text", text: "โอนแล้วส่งรูปสลิปในแชทนี้ได้เลยค่ะ", color: "#dbeafe", size: "xs", margin: "xs" }
            ]
          },
          body: {
            type: "box",
            layout: "vertical",
            paddingAll: "14px",
            spacing: "sm",
            contents: [
              { type: "text", text: "ธนาคารกรุงไทย (สาขาท่าพระ)", size: "xs", color: "#475569" },
              { type: "text", text: "038-0-25363-1", size: "lg", weight: "bold", color: "#1d4ed8" },
              { type: "text", text: "ชื่อบัญชี: นายจีรวัฒน์ พลอาจ", size: "xs", weight: "bold", color: "#0f172a" },
              {
                type: "button",
                style: "primary",
                color: "#2563eb",
                height: "sm",
                margin: "sm",
                action: {
                  type: "clipboard",
                  label: "📋 คัดลอกเลขบัญชี",
                  clipboardText: "0380253631"
                }
              },
              {
                type: "button",
                style: "secondary",
                height: "sm",
                margin: "xs",
                action: {
                  type: "message",
                  label: "❌ ยกเลิกคำสั่งซื้อ",
                  text: "ยกเลิกคำสั่งซื้อ " + orderCode
                }
              }
            ]
          }
        }
      });
    }

    replyLine(replyToken, replyMsgs);

    // แจ้งเตือนทันทีเข้า Telegram Commander
    pushAdminAlert(
      "🚨 [ออเดอร์ใหม่ - ปิดจบใน LINE อัตโนมัติ 100%] 🐟\n" +
      "━━━━━━━━━━━━━━━━━━\n" +
      "🔖 รหัสสั่งซื้อ: " + orderCode + "\n" +
      "👤 ชื่อผู้รับ: " + (orderDetails.recipientName || customerName) + " (LINE: " + customerName + ")\n" +
      "🆔 LINE UID: " + userId + "\n" +
      "📞 เบอร์โทร: " + orderDetails.phone + "\n" +
      "📦 สินค้า: " + orderDetails.package + "\n" +
      "💵 ยอดเก็บ: " + orderDetails.price + " บาท\n" +
      "💳 วิธีชำระ: " + orderDetails.paymentMethod + (hasSlipAttached ? " (✅ แนบสลิปแล้ว)" : "") + "\n" +
      "🏠 ที่อยู่จัดส่ง:\n" + orderDetails.fullText + "\n" +
      "⏰ เวลา: " + nowStr + "\n" +
      "━━━━━━━━━━━━━━━━━━\n" +
      "👉 ตรวจสอบในระบบหลังบ้าน: https://watt29.github.io/pakhem-shop/admin.html"
    );
    return;
  }

  // 1.55 กรณีลูกค้าพิมพ์ ชื่อ+ที่อยู่+เบอร์โทร ครบในข้อความเดียว แต่ยังขาด ตำบล/อำเภอ/จังหวัด หรือ ยังไม่ได้เลือกวิธีชำระเงิน
  const checkAfterExtractCtx = getUserOrderContext(userId);
  if (checkAfterExtractCtx.savedAddress && checkAfterExtractCtx.savedPhone && checkAfterExtractCtx.savedName && /(?:0[2689]\d{8}|0[2689]\d{1}[-\s]?\d{3}[-\s]?\d{4})/.test(userText)) {
    if (!hasCompleteThaiAddress(checkAfterExtractCtx.savedAddress)) {
      replyLine(replyToken, [buildTambonSelectCard(checkAfterExtractCtx)]);
      return;
    }
    if (!checkAfterExtractCtx.payMode) {
      replyLine(replyToken, [buildFinalPaymentConfirmCard(checkAfterExtractCtx, "5/5")]);
      return;
    }
  }

  // 1.58 กรณีลูกค้ากดเลือกหรือพิมพ์ "ตำบล/แขวง" (เช่น "เลือกตำบล: ต.มหาราช" หรือ "ต.มหาราช" หรือพิมพ์ชื่อตำบลเมื่อระบบรอตำบล)
  const hasAnyPhone = /(?:0[2689]\d{8}|0[2689]\d{1}[-\s]?\d{3}[-\s]?\d{4})/.test(userText);
  const tambonPrefixMatch = userText.match(/^(?:เลือกตำบล|ตำบล|ต\.|แขวง)\s*[:：-]?\s*(.+)$/i);
  const isWaitingTambonPlain = activeOrderCtx.waitingTambon && activeOrderCtx.savedAddress && !hasAnyPhone && !/^(?:บ้านเลขที่|ชื่อผู้รับ|ชื่อ|เบอร์โทร|รหัสไปรษณีย์|ปณ|เลือก|ยืนยัน|เช็ค|เลขพัสดุ)/.test(userText.trim()) && userText.trim().length >= 2 && userText.trim().length <= 35;
  if (tambonPrefixMatch || isWaitingTambonPlain) {
    const rawTambonVal = tambonPrefixMatch ? tambonPrefixMatch[1].trim() : userText.trim();
    const updatedAddrWithTambon = insertTambonIntoAddress(activeOrderCtx.savedAddress || "", rawTambonVal);
    const tRoute = calculateShippingRouteInfo(updatedAddrWithTambon);
    saveUserOrderContext(userId, {
      savedAddress: updatedAddrWithTambon,
      waitingTambon: false,
      houseFilled: true,
      distanceKm: tRoute.distanceKm,
      estDays: tRoute.estDays,
      allowCod: tRoute.allowCod
    });
    const latestCtx = getUserOrderContext(userId);

    if (!latestCtx.payMode) {
      replyLine(replyToken, [buildFinalPaymentConfirmCard(latestCtx, "2/5")]);
      return;
    }
    if (latestCtx.savedName && latestCtx.savedPhone) {
      event.message.text = "ชื่อผู้รับ: " + latestCtx.savedName + " " + latestCtx.savedAddress + " โทร " + latestCtx.savedPhone + " (" + (latestCtx.payMode === "COD" ? "ปลายทาง" : (latestCtx.payMode === "COLD_TRUCK" ? "รถห้องเย็น" : "โอนเงิน")) + ")";
      handleTextMessage(event);
      return;
    }
    if (!latestCtx.savedName) {
      const askNameAfterTambonCard = {
        type: "flex",
        altText: "4/5 กรอกชื่อผู้รับ",
        quickReply: getFinalAddressStepQuickReply(false, false),
        contents: {
          type: "bubble",
          size: "mega",
          header: {
            type: "box",
            layout: "vertical",
            backgroundColor: "#0284c7",
            paddingAll: "12px",
            contents: [
              { type: "text", text: "👤 4/5 : ชื่อผู้รับพัสดุ", color: "#ffffff", size: "md", weight: "bold" }
            ]
          },
          body: {
            type: "box",
            layout: "vertical",
            paddingAll: "14px",
            spacing: "xs",
            contents: [
              { type: "text", text: "🏠 " + updatedAddrWithTambon, size: "xs", color: "#0369a1", weight: "bold", wrap: true },
              { type: "text", text: tRoute.summaryLine, size: "xs", color: "#059669", weight: "bold", wrap: true },
              {
                type: "button",
                style: "primary",
                color: "#059669",
                height: "sm",
                margin: "md",
                action: {
                  type: "postback",
                  label: "👤 กดกรอกชื่อผู้รับ",
                  data: "action=fill_recipient_name",
                  inputOption: "openKeyboard",
                  fillInText: "ชื่อผู้รับ: "
                }
              }
            ]
          }
        }
      };
      replyLine(replyToken, [askNameAfterTambonCard]);
      return;
    }
    const askPhoneAfterTambonCard = {
      type: "flex",
      altText: "5/5 กรอกเบอร์โทรศัพท์",
      quickReply: getFinalAddressStepQuickReply(false, false),
      contents: {
        type: "bubble",
        size: "mega",
        header: {
          type: "box",
          layout: "vertical",
          backgroundColor: "#059669",
          paddingAll: "12px",
          contents: [
            { type: "text", text: "📞 5/5 : กรอกเบอร์โทรศัพท์", color: "#ffffff", size: "md", weight: "bold" }
          ]
        },
        body: {
          type: "box",
          layout: "vertical",
          paddingAll: "14px",
          spacing: "sm",
          contents: [
            { type: "text", text: "🏠 " + updatedAddrWithTambon, size: "xs", color: "#0369a1", weight: "bold", wrap: true },
            {
              type: "button",
              style: "primary",
              color: "#ea580c",
              height: "sm",
              margin: "md",
              action: {
                type: "postback",
                label: "📞 กดกรอกเบอร์โทร",
                data: "action=fill_phone_last_step",
                inputOption: "openKeyboard",
                fillInText: "เบอร์โทร: "
              }
            }
          ]
        }
      }
    };
    replyLine(replyToken, [askPhoneAfterTambonCard]);
    return;
  }

  // 1.6 ตัวช่วยนำทางทีละขั้น: 1/5 หมุด/ปณ. ➔ 2/5 แจ้งระยะทาง & เลือกวิธีชำระเงิน ➔ 3/5 บ้านเลขที่+ตำบล ➔ 4/5 ชื่อผู้รับ ➔ 5/5 เบอร์โทร
  const zipOnlyMatch = userText.match(/^(?:รหัสไปรษณีย์|ปณ\.?)?[\s:：-]*([1-9]\d{4})[\s]*$/);
  if (zipOnlyMatch) {
    const zipCode = zipOnlyMatch[1];
    const autoArea = enrichThaiAddressWithMaps(zipCode);
    const zipRoute = calculateShippingRouteInfo(autoArea);
    const curCtxZip = getUserOrderContext(userId);
    if (curCtxZip.savedHouseNo) {
      const fullFromZip = enrichThaiAddressWithMaps(curCtxZip.savedHouseNo + " " + autoArea);
      saveUserOrderContext(userId, {
        savedAddress: fullFromZip,
        distanceKm: zipRoute.distanceKm,
        estDays: zipRoute.estDays,
        allowCod: zipRoute.allowCod,
        houseFilled: true,
        waitingTambon: !hasCompleteThaiAddress(fullFromZip)
      });
      event.message.text = fullFromZip;
      handleTextMessage(event);
      return;
    }
    saveUserOrderContext(userId, {
      savedAddress: autoArea,
      distanceKm: zipRoute.distanceKm,
      estDays: zipRoute.estDays,
      allowCod: zipRoute.allowCod,
      houseFilled: false,
      waitingTambon: false
    });
    const updatedZipCtx = getUserOrderContext(userId);
    if (!updatedZipCtx.payMode) {
      replyLine(replyToken, [buildFinalPaymentConfirmCard(updatedZipCtx, "2/5")]);
      return;
    }
    replyLine(replyToken, [buildHouseNumberStepCard(autoArea, zipRoute, updatedZipCtx)]);
    return;
  }

  // กรณีลูกค้าพิมพ์ "ชื่อผู้รับ: ..." (ขั้นที่ 4/5 -> ไปขั้นที่ 5/5 กรอกเบอร์โทร)
  const nameInputMatch = userText.match(/^(?:ชื่อผู้รับ|ชื่อ-นามสกุล|ชื่อ)\s*[:：-]\s*(.+)$/);
  if (nameInputMatch) {
    const cleanRecipient = nameInputMatch[1].trim();
    saveUserOrderContext(userId, { savedName: cleanRecipient });
    const latestCtx = getUserOrderContext(userId);

    // หากมีที่อยู่แล้วแต่ยังไม่มีตำบล -> เด้งเลือกตำบลก่อน!
    if (latestCtx.savedAddress && !hasCompleteThaiAddress(latestCtx.savedAddress)) {
      saveUserOrderContext(userId, { waitingTambon: true });
      replyLine(replyToken, [buildTambonSelectCard(getUserOrderContext(userId))]);
      return;
    }

    // หากมีครบทั้ง ที่อยู่ และ เบอร์โทร อยู่แล้ว -> ไปเลือกวิธีชำระเงินหรือออกใบสั่งซื้อทันที!
    if (latestCtx.savedAddress && latestCtx.savedPhone) {
      if (!latestCtx.payMode) {
        replyLine(replyToken, [buildFinalPaymentConfirmCard(latestCtx, "5/5")]);
        return;
      }
      event.message.text = "ชื่อผู้รับ: " + cleanRecipient + " " + latestCtx.savedAddress + " โทร " + latestCtx.savedPhone + " (" + (latestCtx.payMode === "COD" ? "ปลายทาง" : (latestCtx.payMode === "COLD_TRUCK" ? "รถห้องเย็น" : "โอนเงิน")) + ")";
      handleTextMessage(event);
      return;
    }

    // หากยังไม่มีเบอร์โทร ให้เด้งการ์ด 5/5 กดกรอกเบอร์โทร
    const askPhoneAfterNameCard = {
      type: "flex",
      altText: "5/5 กรอกเบอร์โทรศัพท์",
      quickReply: getFinalAddressStepQuickReply(false, false),
      contents: {
        type: "bubble",
        size: "mega",
        header: {
          type: "box",
          layout: "vertical",
          backgroundColor: "#059669",
          paddingAll: "12px",
          contents: [
            { type: "text", text: "📞 5/5 : กรอกเบอร์โทรศัพท์", color: "#ffffff", size: "md", weight: "bold" }
          ]
        },
        body: {
          type: "box",
          layout: "vertical",
          paddingAll: "14px",
          spacing: "sm",
          contents: [
            { type: "text", text: "👤 ผู้รับ: " + cleanRecipient, size: "xs", weight: "bold", color: "#065f46", wrap: true },
            {
              type: "button",
              style: "primary",
              color: "#ea580c",
              height: "sm",
              margin: "md",
              action: {
                type: "postback",
                label: "📞 กดกรอกเบอร์โทร",
                data: "action=fill_phone_last_step",
                inputOption: "openKeyboard",
                fillInText: "เบอร์โทร: "
              }
            }
          ]
        }
      }
    };
    replyLine(replyToken, [askPhoneAfterNameCard]);
    return;
  }

  // กรณีลูกค้าพิมพ์เบอร์โทร (ขั้นที่ 5/5 -> ตรวจสอบความถูกต้อง 10 หลักจริงก่อนปิดจบออเดอร์)
  const phoneAttemptMatch = userText.match(/^(?:เบอร์โทรศัพท์|เบอร์โทร|เบอร์|โทร)\s*[:：-]?\s*(.+)$/) || userText.match(/^(0\d[\d-\s]{4,14})$/);
  if (phoneAttemptMatch) {
    const pCheck = validateThaiPhoneNumber(phoneAttemptMatch[1]);
    if (!pCheck.valid) {
      replyLine(replyToken, [buildInvalidPhoneCard(pCheck.reason)]);
      return;
    }
    const cleanPhone = pCheck.phone;
    saveUserOrderContext(userId, { savedPhone: cleanPhone });
    const latestCtx = getUserOrderContext(userId);

    // หากมีที่อยู่แล้วแต่ยังขาด ตำบล/อำเภอ/จังหวัด -> เด้งเลือกตำบลทันที!
    if (latestCtx.savedAddress && !hasCompleteThaiAddress(latestCtx.savedAddress)) {
      saveUserOrderContext(userId, { waitingTambon: true });
      replyLine(replyToken, [buildTambonSelectCard(getUserOrderContext(userId))]);
      return;
    }

    // ถ้ามีที่อยู่และชื่อผู้รับครบแล้ว -> ปิดจบออเดอร์ทันที (หรือเลือกวิธีชำระเงินถ้ายังไม่ได้เลือก)!
    if (latestCtx.savedAddress && latestCtx.savedName) {
      if (!latestCtx.payMode) {
        replyLine(replyToken, [buildFinalPaymentConfirmCard(latestCtx, "5/5")]);
        return;
      }
      event.message.text = "ชื่อผู้รับ: " + latestCtx.savedName + " " + latestCtx.savedAddress + " โทร " + cleanPhone + " (" + (latestCtx.payMode === "COD" ? "ปลายทาง" : (latestCtx.payMode === "COLD_TRUCK" ? "รถห้องเย็น" : "โอนเงิน")) + ")";
      handleTextMessage(event);
      return;
    }

    // ถ้ามีที่อยู่แล้ว แต่ยังไม่ได้กรอกชื่อผู้รับ -> เด้งปุ่มถามชื่อผู้รับ!
    if (latestCtx.savedAddress && !latestCtx.savedName) {
      const askNameCard = {
        type: "flex",
        altText: "4/5 กรอกชื่อผู้รับ",
        quickReply: getFinalAddressStepQuickReply(false, false),
        contents: {
          type: "bubble",
          size: "mega",
          header: {
            type: "box",
            layout: "vertical",
            backgroundColor: "#0284c7",
            paddingAll: "12px",
            contents: [
              { type: "text", text: "👤 4/5 : ชื่อผู้รับพัสดุ", color: "#ffffff", size: "md", weight: "bold" }
            ]
          },
          body: {
            type: "box",
            layout: "vertical",
            paddingAll: "14px",
            spacing: "sm",
            contents: [
              { type: "text", text: "📞 เบอร์โทร: " + cleanPhone, size: "xs", weight: "bold", color: "#1e293b", wrap: true },
              {
                type: "button",
                style: "primary",
                color: "#059669",
                height: "sm",
                margin: "sm",
                action: {
                  type: "postback",
                  label: "👤 กดกรอกชื่อผู้รับ",
                  data: "action=fill_recipient_name",
                  inputOption: "openKeyboard",
                  fillInText: "ชื่อผู้รับ: "
                }
              }
            ]
          }
        }
      };
      replyLine(replyToken, [askNameCard]);
      return;
    }

    const prevOrder = lookupPreviousOrderAddress(userId, cleanPhone);
    if (prevOrder && prevOrder.address) {
      const pRoute = calculateShippingRouteInfo(prevOrder.address);
      saveUserOrderContext(userId, {
        savedPhone: cleanPhone,
        savedAddress: prevOrder.address,
        savedName: prevOrder.customer_name || "",
        distanceKm: pRoute.distanceKm,
        estDays: pRoute.estDays,
        allowCod: pRoute.allowCod,
        houseFilled: true
      });
      replyLine(replyToken, [buildFinalPaymentConfirmCard(getUserOrderContext(userId), "5/5")]);
      return;
    }

    replyLine(replyToken, [{
      type: "text",
      text: "✅ บันทึกเบอร์โทร " + cleanPhone + " แล้วค่ะ\n👇 กดปุ่ม [📍 ปักหมุดที่อยู่] ด้านล่างได้เลยค่ะ",
      quickReply: getFinalAddressStepQuickReply(false, false)
    }]);
    return;
  }

  // กรณีลูกค้ากดปุ่ม "✍️ กดกรอกบ้านเลขที่" แล้วพิมพ์บ้านเลขที่ส่งมา (เช่น "บ้านเลขที่: 99/1 หมู่ 2")
  const isHouseInput = userText.startsWith("บ้านเลขที่") || (activeOrderCtx.savedAddress && !activeOrderCtx.houseFilled && !hasAnyPhone && /^\d/.test(userText.trim()));
  const hasAddrWordsOnly = /(?:บ้านเลขที่|ต\.|อ\.|จ\.|ตำบล|อำเภอ|จังหวัด|แขวง|เขต|ถนน|ซอย|หมู่ที่|หมู่|\b\d{5}\b|\d+\/\d+)/.test(userText);

  if (!hasAnyPhone && (isHouseInput || (hasAddrWordsOnly && userText.length >= 4))) {
    let rawHouseText = userText.trim().replace(/^บ้านเลขที่\s*[:：-]?\s*/, "บ้านเลขที่ ").trim();
    if (/^\d/.test(rawHouseText)) {
      rawHouseText = "บ้านเลขที่ " + rawHouseText;
    }
    const hasAreaInText = /(?:ต\.|อ\.|จ\.|ตำบล|อำเภอ|จังหวัด|แขวง|เขต|กทม|กรุงเทพ|\b[1-9]\d{4}\b)/.test(rawHouseText);

    // หากลูกค้ายังไม่ได้ปักหมุดแผนที่ และพิมพ์มาเฉพาะบ้านเลขที่/หมู่ (ยังไม่มี ตำบล/อำเภอ/จังหวัด หรือ รหัสไปรษณีย์ 5 หลัก)
    if (!activeOrderCtx.savedAddress && !hasAreaInText) {
      saveUserOrderContext(userId, { savedHouseNo: rawHouseText });
      const askAreaCard = {
        type: "flex",
        altText: "กดปักหมุดแผนที่ หรือ พิมพ์รหัสไปรษณีย์",
        quickReply: getFinalAddressStepQuickReply(false, false),
        contents: {
          type: "bubble",
          size: "mega",
          header: {
            type: "box",
            layout: "vertical",
            backgroundColor: "#0284c7",
            paddingAll: "12px",
            contents: [
              { type: "text", text: "📍 ปักหมุด / รหัสไปรษณีย์", color: "#ffffff", size: "md", weight: "bold" }
            ]
          },
          body: {
            type: "box",
            layout: "vertical",
            paddingAll: "14px",
            spacing: "sm",
            contents: [
              { type: "text", text: "🏠 บันทึก " + rawHouseText + " แล้วค่ะ", size: "xs", weight: "bold", color: "#1e293b", wrap: true },
              {
                type: "button",
                style: "primary",
                color: "#0284c7",
                height: "sm",
                margin: "sm",
                action: {
                  type: "uri",
                  label: "📍 กดปักหมุดแผนที่",
                  uri: "https://line.me/R/nv/location/"
                }
              },
              {
                type: "button",
                style: "primary",
                color: "#059669",
                height: "sm",
                margin: "sm",
                action: {
                  type: "postback",
                  label: "📮 พิมพ์รหัสไปรษณีย์",
                  data: "action=fill_zip_code",
                  inputOption: "openKeyboard",
                  fillInText: "รหัสไปรษณีย์: "
                }
              }
            ]
          }
        }
      };
      replyLine(replyToken, [askAreaCard]);
      return;
    }

    let combinedAddr = rawHouseText;
    if (activeOrderCtx.savedAddress && combinedAddr.indexOf(activeOrderCtx.savedAddress) === -1) {
      combinedAddr = enrichThaiAddressWithMaps(combinedAddr + " " + activeOrderCtx.savedAddress);
    } else {
      combinedAddr = enrichThaiAddressWithMaps(combinedAddr);
    }
    const isAddrCompleteNow = hasCompleteThaiAddress(combinedAddr);
    const houseRoute = calculateShippingRouteInfo(combinedAddr);
    saveUserOrderContext(userId, {
      savedAddress: combinedAddr,
      savedHouseNo: null,
      houseFilled: true,
      waitingTambon: !isAddrCompleteNow,
      distanceKm: houseRoute.distanceKm,
      estDays: houseRoute.estDays,
      allowCod: houseRoute.allowCod
    });
    const latestCtx = getUserOrderContext(userId);

    // ถ้ายังไม่ได้เลือกวิธีชำระเงิน -> เด้งการ์ด 2/5 เลือกวิธีชำระเงินพร้อมแจ้งระยะทาง & วันถึงก่อน!
    if (!latestCtx.payMode) {
      replyLine(replyToken, [buildFinalPaymentConfirmCard(latestCtx, "2/5")]);
      return;
    }

    // ถ้ายังไม่มี ตำบล/แขวง ในที่อยู่ -> เด้งการ์ดให้กดเลือกตำบลใน 1 คลิกทันที!
    if (!isAddrCompleteNow) {
      replyLine(replyToken, [buildTambonSelectCard(latestCtx)]);
      return;
    }

    // ถ้ายังไม่ได้กรอกชื่อผู้รับ -> เด้งการ์ด 4/5 ให้กดปุ่ม "👤 กดกรอกชื่อผู้รับ"
    if (!latestCtx.savedName) {
      const askNameAfterHouseCard = {
        type: "flex",
        altText: "4/5 กรอกชื่อผู้รับ",
        quickReply: getFinalAddressStepQuickReply(false, false),
        contents: {
          type: "bubble",
          size: "mega",
          header: {
            type: "box",
            layout: "vertical",
            backgroundColor: "#0284c7",
            paddingAll: "12px",
            contents: [
              { type: "text", text: "👤 4/5 : ชื่อผู้รับพัสดุ", color: "#ffffff", size: "md", weight: "bold" }
            ]
          },
          body: {
            type: "box",
            layout: "vertical",
            paddingAll: "14px",
            spacing: "xs",
            contents: [
              { type: "text", text: "🏠 " + combinedAddr, size: "xs", color: "#0369a1", weight: "bold", wrap: true },
              { type: "text", text: houseRoute.summaryLine, size: "xs", color: "#059669", weight: "bold", wrap: true },
              {
                type: "button",
                style: "primary",
                color: "#059669",
                height: "sm",
                margin: "md",
                action: {
                  type: "postback",
                  label: "👤 กดกรอกชื่อผู้รับ",
                  data: "action=fill_recipient_name",
                  inputOption: "openKeyboard",
                  fillInText: "ชื่อผู้รับ: "
                }
              }
            ]
          }
        }
      };
      replyLine(replyToken, [askNameAfterHouseCard]);
      return;
    }

    // ถ้ามีชื่อผู้รับแล้ว -> เด้งการ์ด 5/5 ให้กดปุ่ม "📞 กดกรอกเบอร์โทร"
    const askPhoneCard = {
      type: "flex",
      altText: "5/5 กรอกเบอร์โทรศัพท์",
      quickReply: getFinalAddressStepQuickReply(false, false),
      contents: {
        type: "bubble",
        size: "mega",
        header: {
          type: "box",
          layout: "vertical",
          backgroundColor: "#059669",
          paddingAll: "12px",
          contents: [
            { type: "text", text: "📞 5/5 : กรอกเบอร์โทรศัพท์", color: "#ffffff", size: "md", weight: "bold" }
          ]
        },
        body: {
          type: "box",
          layout: "vertical",
          paddingAll: "14px",
          spacing: "xs",
          contents: [
            { type: "text", text: "🏠 " + combinedAddr, size: "xs", color: "#065f46", weight: "bold", wrap: true },
            { type: "text", text: houseRoute.summaryLine, size: "xs", color: "#059669", weight: "bold", wrap: true },
            {
              type: "button",
              style: "primary",
              color: "#ea580c",
              height: "sm",
              margin: "md",
              action: {
                type: "postback",
                label: "📞 กดกรอกเบอร์โทร",
                data: "action=fill_phone_last_step",
                inputOption: "openKeyboard",
                fillInText: "เบอร์โทร: "
              }
            }
          ]
        }
      }
    };

    replyLine(replyToken, [askPhoneCard]);
    return;
  }

  // ฟังก์ชันสร้างการ์ดคำตอบสั้นกระชับ + ปุ่มนำทางสั่งซื้อทันที
  function buildQuickInfoNavCard(headerText, headerColor, bulletLines, showBankBtn) {
    var bodyItems = bulletLines.map(function(line, idx) {
      return {
        type: "text",
        text: line,
        size: "xs",
        color: idx === 0 ? "#0f172a" : "#334155",
        weight: idx === 0 ? "bold" : "regular",
        wrap: true,
        margin: idx === 0 ? "none" : "xs"
      };
    });
    bodyItems.push({
      type: "button",
      style: "primary",
      color: "#059669",
      height: "sm",
      margin: "md",
      action: {
        type: "message",
        label: "🐟 สั่ง 1 กก. (550.-)",
        text: "สั่งซื้อปลาแดดเดียว 1 กิโลกรัม"
      }
    });
    bodyItems.push({
      type: "button",
      style: "secondary",
      height: "sm",
      margin: "sm",
      action: {
        type: "message",
        label: "🐟 สั่ง 500g (390.-)",
        text: "รับชุดพอดีมื้อ 500 กรัม"
      }
    });
    if (showBankBtn) {
      bodyItems.push({
        type: "button",
        style: "primary",
        color: "#2563eb",
        height: "sm",
        margin: "sm",
        action: {
          type: "clipboard",
          label: "📋 คัดลอกเลขบัญชี",
          clipboardText: "0380253631"
        }
      });
    }
    return {
      type: "flex",
      altText: headerText,
      quickReply: getMasterQuickReply(),
      contents: {
        type: "bubble",
        size: "mega",
        header: {
          type: "box",
          layout: "vertical",
          backgroundColor: headerColor || "#065f46",
          paddingAll: "12px",
          contents: [
            { type: "text", text: headerText, color: "#ffffff", size: "md", weight: "bold" }
          ]
        },
        body: {
          type: "box",
          layout: "vertical",
          paddingAll: "14px",
          spacing: "xs",
          contents: bodyItems
        }
      }
    };
  }

  // 1.7 & 7. เงื่อนไขการจัดส่ง / ส่งต่างจังหวัด / เก็บเงินปลายทาง (COD) / ถามระยะทาง กม. / กี่วันถึง
  if (COLD_PACK_KEYWORDS.some(k => lowerText.includes(k)) || ["เงื่อนไขการจัดส่ง", "เงื่อนไขการส่ง", "วิธีจัดส่ง", "ส่งยังไง", "ส่งฟรีไหม", "ค่าส่ง", "ปลายทาง", "เก็บเงินปลายทาง", "cod", "กี่วันถึง", "ส่งวันไหน", "รถเย็น", "รถห้องเย็น", "ได้สินค้ากี่วัน", "กี่วันได้", "ระยะทาง", "กี่กิโล", "กี่โล", "กี่กม"].some(k => lowerText.includes(k))) {
    const addrToCalc = (/(?:จ\.|จังหวัด|\b[1-9]\d{4}\b|กรุงเทพ|กทม|เชียงใหม่|ภูเก็ต|ชลบุรี|ขอนแก่น|โคราช|นนทบุรี|ปทุมธานี|สุราษฎร์|สงขลา|หาดใหญ่|อุบล|อุดร|เชียงราย|ระยอง|นครปฐม|สมุทรปราการ|อยุธยา)/.test(userText)) ? userText : (activeOrderCtx.savedAddress || "");
    const askRoute = addrToCalc ? calculateShippingRouteInfo(addrToCalc) : null;
    const distBullet = askRoute
      ? ("📍 พื้นที่ของคุณลูกค้า: ระยะทาง ~" + askRoute.distanceKm.toLocaleString("th-TH") + " กม. (จากบางปะหัน อยุธยา) • ถึงใน " + askRoute.estDays)
      : "📍 ต้นทาง: อ.บางปะหัน จ.อยุธยา (ปักหมุดแผนที่เพื่อเช็คระยะทาง กม. & วันถึงได้ทันที)";
    replyLine(replyToken, [
      buildQuickInfoNavCard("🚚 ระยะทางจัดส่ง & วิธีชำระเงิน", "#0284c7", [
        distBullet,
        "🚚 จัดส่งถึงหน้าบ้านใน 1–2 วัน: แพ็กฟอยล์เก็บความเย็น • โอนส่งฟรีทุกชุด (งดรับ COD)",
        "❄️ ระยะ > 350 กม. (ถึงใน 3–4 วัน) / ชุด 2 กก.: ส่งรถห้องเย็นควบคุมอุณหภูมิ (โอนเงินล่วงหน้า)",
        "🏦 บัญชีรับโอน: กรุงไทย 038-0-25363-1 (นายจีรวัฒน์ พลอาจ)"
      ], true)
    ]);
    return;
  }

  // 1.8 ลูกค้าขอคุยกับป้าเข็ม / เจ้าของร้าน / เคลมสินค้า / ขายส่ง
  const ownerKeywords = ["คุยกับป้าเข็ม", "ขอคุยกับป้าเข็ม", "เจ้าของร้าน", "เคลม", "ปลาเน่า", "ปลาเสีย", "ร้องเรียน", "ขายส่ง", "สั่งเยอะ", "ตัวแทน", "รับไปขาย"];
  if (ownerKeywords.some(k => lowerText.includes(k))) {
    replyLine(replyToken, [
      buildQuickInfoNavCard("🛡️ รับประกันความสด & สั่งจำนวนมาก", "#0f172a", [
        "✅ รับประกันความสด 100% (พบปัญหาถ่ายรูปแจ้งเคลมชุดใหม่ฟรีทันที)",
        "📦 ชุดตุนสุดคุ้ม 2 กก. (8–12 ตัวใหญ่): 1,090.- ส่งฟรีรถห้องเย็น",
        "💬 สั่งมากกว่า 2 กก. กดเลือกแพ็กเกจด้านล่างได้เลยค่ะ"
      ], false)
    ]);
    return;
  }

  // 2. คำทักทาย / เริ่มต้น / เมนู
  const greetingKeywords = ["สวัสดี", "หวัดดี", "ดีจ้า", "hello", "hi", "เมนู", "เริ่ม", "ป้าเข็ม", "สวัสดีครับ", "สวัสดีค่ะ", "ทักครับ", "ทักค่ะ", "ถามได้ทุกเรื่อง", "ถามอะไรก็ได้", "ปรึกษาป้าเข็ม"];
  if (greetingKeywords.some(k => lowerText === k)) {
    sendWelcomeMessage(replyToken);
    return;
  }

  // 2.3 เมนูแนะนำ
  const emotionKeywords = ["เหนื่อย", "เครียด", "หมดแรง", "เบื่อ", "หิว", "กินอะไรดี", "กินไรดี", "ทอดกินกับอะไรดี", "เมนู", "แนะนำเมนู", "ฮีลใจ", "ปลอบใจ"];
  if (emotionKeywords.some(k => lowerText.includes(k))) {
    replyLine(replyToken, [
      buildQuickInfoNavCard("🍳 3 เมนูยอดฮิต ปลาสลิดป้าเข็ม", "#ea580c", [
        "1️⃣ ปลาสลิดทอดกรอบ คู่น้ำปลาพริกมะนาวสด",
        "2️⃣ ต้มยำปลาสลิดใบมะขามอ่อน ซดร้อนๆ คล่องคอ",
        "3️⃣ ข้าวต้มกุ๊ยร้อนๆ แกล้มปลาสลิดทอดมันแทรก"
      ], false)
    ]);
    return;
  }

  // 2.5 ลูกค้าถามซื้อ 1 ตัว / แบ่งขาย
  const singleFishKeywords = ["ตัวเดียว", "1 ตัว", "1ตัว", "หนึ่งตัว", "แยกตัว", "แบ่งตัว", "แบ่งขาย", "แยกขาย", "ตัวละ", "ซื้อตัวเดียว", "ขอตัวเดียว"];
  if (singleFishKeywords.some(k => lowerText.includes(k))) {
    replyLine(replyToken, [
      buildQuickInfoNavCard("🐟 แพ็กเกจซีลสูญญากาศพร้อมส่ง", "#065f46", [
        "ทางร้านซีลสูญญากาศแพ็กเก็บความเย็น (ไม่ได้แยกขาย 1 ตัวค่ะ)",
        "• ชุดเล็ก 500g (2–3 ตัวใหญ่): โอน 390.- ส่งฟรี (งดรับ COD)",
        "• ชุดฮิต 1 กก. (4–6 ตัวใหญ่): โอน 550.- ส่งฟรี (งดรับ COD)"
      ], false)
    ]);
    return;
  }

  // 4. เค็มไหม / รสชาติ
  if (["เค็มไหม", "เค็มมั้ย", "เค็มป่าว", "รสชาติ", "หวานไหม", "ไตพัง", "เค็มมากไหม"].some(k => lowerText.includes(k))) {
    replyLine(replyToken, [
      buildQuickInfoNavCard("🧂 สูตรเค็มน้อย กลมกล่อม (เกลือสมุทร 3%)", "#065f46", [
        "✅ หมักเกลือสมุทรธรรมชาติเพียง 3% เค็มน้อยกำลังดี ไม่แสบคอ",
        "✅ เนื้อปลาสลิดสุพรรณแท้ 97% เนื้อแน่นหนาฟู มันแทรก",
        "❌ ไร้ผงชูรส ไร้สารกันบูด ไร้ฟอร์มาลีน 100%"
      ], false)
    ]);
    return;
  }

  // 5. สะอาดไหม / ตากยังไง / สารเคมี
  if (["สะอาดไหม", "สะอาดมั้ย", "แมลงวัน", "มีฝุ่น", "ตากยังไง", "สารเคมี", "ฟอร์มาลีน", "ยาฆ่าแมลง"].some(k => lowerText.includes(k))) {
    replyLine(replyToken, [
      buildQuickInfoNavCard("☀️ ตากโดมโซล่าร์ระบบปิด สะอาด 100%", "#0284c7", [
        "✅ ตากในโรงเรือนโดมพลังงานแสงอาทิตย์ ไร้ฝุ่น ไร้แมลงวัน",
        "❌ ไม่ฉีดสารเคมี ไม่ใส่ฟอร์มาลีน ไม่ใส่สารกันบูด",
        "❄️ ซีลสูญญากาศแช่เยือกแข็ง -18°C สดสะอาดถึงบ้าน"
      ], false)
    ]);
    return;
  }

  // 6. วิธีเก็บรักษา / เก็บได้นานไหม / ซีลสูญญากาศ
  if (["เก็บได้นานไหม", "เก็บได้กี่วัน", "แช่ตู้เย็น", "แช่ฟรีซ", "วิธีเก็บ", "อายุ", "ซีล", "สูญญากาศ", "ถุงแบบไหน"].some(k => lowerText.includes(k))) {
    replyLine(replyToken, [
      buildQuickInfoNavCard("❄️ วิธีเก็บรักษา (ซีลสูญญากาศ Food Grade)", "#0284c7", [
        "🧊 ช่องฟรีซ (-18°C): เก็บได้นาน 6–12 เดือน (เนื้อยังสดฉ่ำเหมือนใหม่)",
        "🧊 ช่องธรรมดา: เก็บได้ 10–14 วัน",
        "🍳 ก่อนทอด: นำออกมาคลายเย็น ฉีกซองทอดได้ทันที ไม่ต้องล้างน้ำซ้ำ"
      ], false)
    ]);
    return;
  }

  // 6.5 วิธีทอดด้วยหม้อทอดไร้น้ำมัน & กระทะ
  if (["หม้อทอด", "ไร้น้ำมัน", "air fryer", "airfryer", "อบลมร้อน", "กี่องศา", "กี่นาที", "ไม่ใช้น้ำมัน", "วิธีทอด", "ทอดยังไง"].some(k => lowerText.includes(k))) {
    replyLine(replyToken, [
      buildQuickInfoNavCard("🍳 วิธีทอดให้กรอบนอกนุ่มฟู", "#ea580c", [
        "🔥 หม้อทอดไร้น้ำมัน: คลายเย็น ซับแห้ง ทาน้ำมันบางๆ อบ 180°C ด้านละ 10 นาที",
        "🥘 ทอดกระทะ: ใช้ไฟกลางค่อนอ่อน ทอดด้านละ 4–5 นาทีจนเหลืองทอง",
        "💡 ไม่ต้องล้างน้ำซ้ำก่อนทอด รสชาติกลมกล่อมพอดีค่ะ"
      ], false)
    ]);
    return;
  }

  // 6.6 มีไข่ไหม / บั้งมาหรือยัง / ทำสะอาดหรือยัง
  if (["มีไข่ไหม", "มีไข่มั้ย", "ปลาไข่", "ไข่เต็มท้อง", "ไข่ปลา", "ขอดเกล็ด", "ตัดหัว", "บั้ง", "ทำสะอาดหรือยัง", "พร้อมทอดไหม"].some(k => lowerText.includes(k))) {
    replyLine(replyToken, [
      buildQuickInfoNavCard("🔪 ทำสะอาด บั้งพร้อมทอด (เนื้อล้วนคัดพิเศษ)", "#065f46", [
        "✅ ขอดเกล็ด ตัดหัว ควักไส้ ล้างสะอาด และบั้งพร้อมทอดทุกตัว",
        "🐟 เป็นปลาสลิดเนื้อล้วนไซส์จัมโบ้ 4 ตัวโล คัดพิเศษ เนื้อแน่นหนาฟู มันแทรก (ไม่ได้คัดแบบมีไข่ค่ะ)"
      ], false)
    ]);
    return;
  }

  // 6.7 แหล่งที่มา (บางบ่อไหม / ปลาสลิดที่ไหน / สุพรรณบุรี)
  if (["บางบ่อ", "สุพรรณ", "บ่อไหน", "แหล่งไหน", "ปลาที่ไหน", "ของที่ไหน", "จังหวัดไหน", "รับมาจากไหน"].some(k => lowerText.includes(k))) {
    replyLine(replyToken, [
      buildQuickInfoNavCard("📍 ปลาสลิดสุพรรณบุรีแท้ 100% คัดพิเศษ", "#065f46", [
        "🐟 ของร้านป้าเข็มเป็น 'ปลาสลิดสุพรรณบุรีแท้ 100%' ค่ะ (ไม่ใช่บางบ่อจ้า)",
        "✅ ตัวปลามาจากแหล่งน้ำธรรมชาติแท้ 100% ไร้กลิ่นสาบโคลน 100% เนื้อแน่นหนาฟู มันแทรก เค็มน้อย 3%",
        "🚚 แพ็กซีลสูญญากาศส่งตรงจาก อ.บางปะหัน จ.พระนครศรีอยุธยา ค่ะ"
      ], false)
    ]);
    return;
  }

  // 6.8 ทอดมาให้ไหม / แบบดิบหรือสุก
  if (["ทอดมาให้ไหม", "ทอดให้ไหม", "แบบทอด", "พร้อมทาน", "ทอดสุก", "ดิบหรือสุก", "ทอดหรือยัง"].some(k => lowerText.includes(k))) {
    replyLine(replyToken, [
      buildQuickInfoNavCard("🍳 จำหน่ายแบบดิบแดดเดียว (พร้อมทอด)", "#ea580c", [
        "🐟 ทางร้านจำหน่ายเฉพาะ 'ปลาสลิดแดดเดียวแบบดิบ' (ต้องนำไปทอดก่อนทานค่ะ)",
        "❄️ ซีลสูญญากาศ แช่แข็ง -18°C เพื่อให้ลูกค้าทอดสดๆ ร้อนๆ กรอบนอกนุ่มในที่สุดค่ะ"
      ], false)
    ]);
    return;
  }

  // 6.9 ขนาดปลา / กี่ตัวโล / ถามหาปลาชนิดอื่น
  if (["กี่ตัวโล", "โลละกี่ตัว", "กี่ตัวกิโล", "ไซส์ไหน", "ขนาดไหน", "ตัวใหญ่ไหม", "ตัวใหญ่มั้ย"].some(k => lowerText.includes(k))) {
    replyLine(replyToken, [
      buildQuickInfoNavCard("📏 ไซส์จัมโบ้คัดพิเศษ 4 ตัวโล คัดพิเศษ", "#0284c7", [
        "🐟 คัดเฉพาะไซส์ใหญ่จัมโบ้ เนื้อแน่นหนาฟู เต็มคำทุกตัว:",
        "• ชุด 500 กรัม (ประมาณ 2–3 ตัวใหญ่): โอน 390.- ส่งฟรี (งดรับ COD)",
        "• ชุด 1 กิโลกรัม (ประมาณ 4–6 ตัวใหญ่): โอน 550.- ส่งฟรี (งดรับ COD) ⭐",
        "• ชุด 2 กิโลกรัม (ประมาณ 8–12 ตัวใหญ่): โอน 1,090.- ส่งฟรีรถห้องเย็น!"
      ], false)
    ]);
    return;
  }

  if (["ปลาช่อน", "ปลาดุก", "ปลานิล", "ปลาทับทิม", "ปลาอินทรีย์", "มีปลาอะไรบ้าง", "ปลาอื่น"].some(k => lowerText.includes(k))) {
    replyLine(replyToken, [
      buildQuickInfoNavCard("🐟 คัดพิเศษเฉพาะปลาสลิดสุพรรณแท้", "#065f46", [
        "ตอนนี้ทางร้านป้าเข็มทำเฉพาะ 'ปลาสลิดแดดเดียว สุพรรณบุรีแท้ ไซส์จัมโบ้ 4 ตัวโล คัดพิเศษ' อย่างเดียวเลยจ้า",
        "✅ เนื้อหนาฟู มันแทรก เค็มน้อย 3% ไร้ก้างฝอย ทานง่ายมากค่ะ"
      ], false)
    ]);
    return;
  }

  // 8. ช่องทางชำระเงิน / ขอเลขบัญชี (กระชับ เข้าใจง่าย พร้อมปุ่มคัดลอกและปุ่มนำทางสั่งซื้อ)
  if (["เลขบัญชี", "โอนเงิน", "ชำระเงิน", "พร้อมเพย์", "โอน", "บัญชี"].some(k => lowerText.includes(k))) {
    const bankNavCard = {
      type: "flex",
      altText: "บัญชีกรุงไทย 038-0-25363-1 (นายจีรวัฒน์ พลอาจ)",
      quickReply: getMasterQuickReply(),
      contents: {
        type: "bubble",
        size: "mega",
        header: {
          type: "box",
          layout: "vertical",
          backgroundColor: "#1d4ed8",
          paddingAll: "12px",
          contents: [
            { type: "text", text: "🏦 บัญชีโอนเงิน (ส่งฟรีทุกชุด!)", color: "#ffffff", size: "md", weight: "bold" }
          ]
        },
        body: {
          type: "box",
          layout: "vertical",
          paddingAll: "14px",
          spacing: "xs",
          contents: [
            { type: "text", text: "ธนาคารกรุงไทย (สาขาท่าพระ)", size: "xs", color: "#475569" },
            { type: "text", text: "038-0-25363-1", size: "lg", weight: "bold", color: "#1d4ed8" },
            { type: "text", text: "ชื่อบัญชี: นายจีรวัฒน์ พลอาจ", size: "xs", weight: "bold", color: "#0f172a" },
            { type: "text", text: "📸 โอนแล้วส่งรูปสลิปในแชทนี้ได้เลยค่ะ", size: "xs", color: "#059669", margin: "xs" },
            {
              type: "button",
              style: "primary",
              color: "#2563eb",
              height: "sm",
              margin: "md",
              action: {
                type: "clipboard",
                label: "📋 คัดลอกเลขบัญชี",
                clipboardText: "0380253631"
              }
            },
            {
              type: "button",
              style: "primary",
              color: "#059669",
              height: "sm",
              margin: "sm",
              action: {
                type: "message",
                label: "🐟 สั่ง 1 กก. (550.-)",
                text: "สั่งซื้อปลาแดดเดียว 1 กิโลกรัม"
              }
            },
            {
              type: "button",
              style: "secondary",
              height: "sm",
              margin: "sm",
              action: {
                type: "message",
                label: "🐟 สั่ง 500g (390.-)",
                text: "รับชุดพอดีมื้อ 500 กรัม"
              }
            }
          ]
        }
      }
    };
    replyLine(replyToken, [bankNavCard]);
    return;
  }


  // 8.5 สนใจปลา / ขอดูสินค้า / ราคา / โปรโมชั่น / สั่งปลา
  const postponeLineKeywords = ["ค่อยสั่ง", "เดี๋ยวค่อยสั่ง", "ไว้สั่ง", "ไว้ค่อยสั่ง", "ใกล้ปีใหม่", "ปีใหม่ก่อน", "หลังปีใหม่", "ช่วงปีใหม่", "สงกรานต์", "ใกล้สงกรานต์", "รอสิ้นเดือน", "สิ้นเดือนก่อน", "รอเงินออก", "เงินเดือนออก", "ไว้มาอุดหนุน", "ไว้อุดหนุน", "วันหลังค่อย", "รอบหน้าค่อย", "ยังไม่สั่งตอนนี้", "ทักไว้ก่อน", "แปะไว้ก่อน", "บันทึกไว้ก่อน", "ขอคิดดูก่อน", "ตัดสินใจก่อน"];
  if (postponeLineKeywords.some(k => lowerText.includes(k))) {
    replyLine(replyToken, [{
      type: "text",
      text: "สวัสดีค่ะคุณลูกค้า 🙏💕 ยินดีมากๆ เลยจ้าคุณพี่ ใกล้ปีใหม่หรือสะดวกเมื่อไหร่ เปิดแชทนี้ทักหาป้าเข็มได้ตลอดเลยนะคะ (แชทนี้บันทึกไว้ให้แล้ว ไม่หายจ้า)\n❄️ กระซิบนิดนึงค่ะ: ปลาสลิดป้าเข็มซีลสูญญากาศแช่แข็ง เก็บในช่องฟรีซได้นานถึง 3–6 เดือน โดยรสชาติสดใหม่เหมือนเดิมเลยค่ะ หากกลัวช่วงใกล้เทศกาลขนส่งคิวแน่น สั่งตุนติดตู้ฟรีซไว้ก่อน หรือรอสั่งใกล้ๆ วันใช้ก็ได้เลยนะคะ ป้าเข็มยินดีให้บริการเสมอจ้า 🐟✨"
    }]);
    return;
  }

  const fishCardKeywords = ["ปลา", "ปลาแดดเดียว", "ปลาสลิด", "สั่งปลา", "ปลาทอด", "ซื้อปลา", "ปลาเค็ม", "ปลาแดด", "ราคาปลา", "ของกิน", "อาหาร", "ปลาแห้ง", "แดดเดียว", "fish", "ราคา", "กี่บาท", "เท่าไหร่", "โปรโมชั่น", "สั่งซื้อ", "สั่งของ", "หน้าร้าน", "หน้าเว็บ", "ขอซื้อ", "สนใจ", "สินค้าขายดี", "สินค้า", "แคตตาล็อก"];
  if (fishCardKeywords.some(k => lowerText === k || lowerText.includes(k))) {
    sendFishProductFlexCard(replyToken);
    return;
  }

  // 9. ปรึกษาคำถามทั่วไป หรือการปิดการขายอัตโนมัติด้วย Groq AI
  const aiAnswer = askGroqAI(userText);
  replyLine(replyToken, [{
    type: "text",
    text: aiAnswer,
    quickReply: getMasterQuickReply()
  }]);
}

function getUserDisplayName(userId) {
  if (!userId || userId === "ไม่ระบุ") return "ลูกค้าใน LINE OA";
  try {
    const url = "https://api.line.me/v2/bot/profile/" + encodeURIComponent(userId);
    const res = UrlFetchApp.fetch(url, {
      headers: { "Authorization": "Bearer " + LINE_ACCESS_TOKEN },
      muteHttpExceptions: true
    });
    if (res.getResponseCode() === 200) {
      const data = JSON.parse(res.getContentText());
      return data.displayName || "ลูกค้าใน LINE OA";
    }
  } catch (e) {}
  return "ลูกค้าใน LINE OA";
}

/**
 * จัดการเมื่อลูกค้าส่งรูปภาพ (สลิปโอนเงิน / รูปสินค้า)
 * - ดึงรูปภาพจาก LINE Content API
 * - อัปโหลดขึ้น Supabase Storage (Bucket: slips)
 * - จับคู่กับออเดอร์ล่าสุดที่รอโอนเงิน (PENDING + TRANSFER)
 * - อัปเดต slip_url ลงในฐานข้อมูล direct_orders
 * - ส่งแจ้งเตือนพร้อมรูปสลิปตรงเข้า Telegram Commander
 * - ตอบกลับลูกค้าพร้อม Quick Reply
 */
/**
 * วิเคราะห์รูปภาพด้วย Groq Vision (qwen/qwen3.8-27b) เพื่อแยกแยะว่า
 * เป็น "สลิปโอนเงินธนาคารจริง (Bank Transfer E-Slip)" หรือเป็นรูปภาพทั่วไป (อาหาร/สมุดบัญชี/สินค้า/อื่นๆ)
 */
function analyzeImageWithGroqVision(base64Data, contentType, expectedAmount) {
  var defaultRes = {
    ok: false,
    is_slip: false,
    category: "other",
    amount: null,
    bank: "",
    receiver_name: "",
    receiver_account: "",
    ref_no: "",
    date_time: "",
    receiver_matched: false,
    amount_matched: false,
    is_duplicate_ref: false,
    verified_all: false,
    reject_reason: "",
    description: "รูปภาพทั่วไป"
  };
  if (!base64Data) return defaultRes;
  var mime = contentType || "image/jpeg";
  var dataUrl = base64Data.indexOf("data:") === 0 ? base64Data : ("data:" + mime + ";base64," + base64Data);

  var prompt =
    'ตรวจสอบว่ารูปภาพนี้เป็น "สลิปโอนเงินธนาคารไทย (Bank Transfer E-Slip ที่มีรายการโอนเงินสำเร็จ วันที่-เวลา ยอดเงินโอน และรหัสอ้างอิง)" จริงหรือไม่?\n' +
    'กฎเหล็ก:\n' +
    '1. หากเป็นรูปสมุดบัญชีธนาคาร (Passbook), รูปอาหาร/ปลาสลิดทอด, รูปสินค้า, รูปคน, รูปหน้าจอแชท, หรือรูปทั่วไปที่ไม่มีรายการโอนเงินสำเร็จ ให้ตอบ "is_slip": false เสมอ ห้ามเหมาเป็นสลิปเด็ดขาด!\n' +
    '2. จะตอบ "is_slip": true ได้ก็ต่อเมื่อเป็นใบเสร็จสลิปโอนเงินจากแอปธนาคารไทย (หรือสลิปโอนเงิน) ที่ระบุการโอนเงินสำเร็จ มียอดเงินโอนชัดเจน (amount > 0) และมีรหัสอ้างอิง/เลขที่รายการเท่านั้น\n' +
    'ตอบเป็น JSON เท่านั้น ห้ามมีข้อความอื่น:\n' +
    '{"is_slip": true/false, "category": "slip|passbook|food|product|other", "amount": ตัวเลขยอดโอนหรือ null, "bank": "ชื่อธนาคาร", "receiver_name": "ชื่อบัญชีผู้รับโอนที่ปรากฏบนสลิป", "receiver_account": "เลขบัญชีผู้รับโอน (รวมตัวเลขที่มี X บัง เช่น XXX-X-XX363-1)", "ref_no": "รหัสอ้างอิง/เลขที่รายการ", "date_time": "วันและเวลาที่โอนบนสลิป", "description": "อธิบายสั้นๆ ภาษาไทยว่าคือภาพอะไร"}';

  var startIdx = Math.floor(Math.random() * GROQ_KEYS.length);
  for (var i = 0; i < Math.min(GROQ_KEYS.length, 4); i++) {
    var apiKey = GROQ_KEYS[(startIdx + i) % GROQ_KEYS.length];
    try {
      var res = UrlFetchApp.fetch("https://api.groq.com/openai/v1/chat/completions", {
        method: "post",
        contentType: "application/json",
        headers: { "Authorization": "Bearer " + apiKey },
        payload: JSON.stringify({
          model: "qwen/qwen3.8-27b",
          messages: [{
            role: "user",
            content: [
              { type: "text", text: prompt },
              { type: "image_url", image_url: { url: dataUrl } }
            ]
          }],
          temperature: 0.1
        }),
        muteHttpExceptions: true
      });
      if (res.getResponseCode() === 200) {
        var body = JSON.parse(res.getContentText());
        var raw = (body.choices && body.choices[0] && body.choices[0].message && body.choices[0].message.content) || "";
        raw = raw.replace(/<think>[\s\S]*?<\/think>/gi, "").trim();
        var m = raw.match(/\{[\s\S]*\}/);
        if (m) {
          var parsed = JSON.parse(m[0]);
          var amt = null;
          if (parsed.amount !== null && parsed.amount !== undefined && String(parsed.amount).trim() !== "") {
            var numStr = String(parsed.amount).replace(/,/g, "").match(/\d+(?:\.\d+)?/);
            if (numStr) amt = parseFloat(numStr[0]);
          }
          var isValidSlip = (parsed.is_slip === true && amt !== null && amt > 0 && parsed.category === "slip");
          var recName = String(parsed.receiver_name || "").trim();
          var recAcc = String(parsed.receiver_account || "").trim();
          var refNo = String(parsed.ref_no || "").trim();

          // ชั้นที่ 2: ตรวจชื่อผู้รับโอน (นายจีรวัฒน์ พลอาจ) หรือเลขบัญชีปลายทาง (038-0-25363-1)
          var recLower = (recName + " " + recAcc).toLowerCase();
          var receiverMatched = false;
          if (isValidSlip) {
            if (recLower.indexOf("จีรวัฒน์") !== -1 || recLower.indexOf("จิรวัฒน์") !== -1 ||
                recLower.indexOf("พลอาจ") !== -1 || recLower.indexOf("jeerawat") !== -1 ||
                recLower.indexOf("jirawat") !== -1 || recLower.indexOf("25363") !== -1 ||
                recLower.indexOf("5363-1") !== -1 || recLower.indexOf("53631") !== -1) {
              receiverMatched = true;
            }
          }

          // ชั้นที่ 3: ตรวจยอดเงินตรงกับยอดสั่งซื้อ และตรวจกรณีโอนน้อยกว่าราคาสินค้า
          var expAmt = Number(expectedAmount) || 0;
          var minPkgPrice = 390; // ราคาสินค้าขั้นต่ำสุดของร้าน (ชุด 500g = 390 บาท ส่งฟรี)
          var shortfallAmount = 0;
          if (isValidSlip && expAmt > 0 && amt < expAmt - 0.5) {
            shortfallAmount = Math.round((expAmt - amt) * 100) / 100;
          } else if (isValidSlip && expAmt === 0 && amt < minPkgPrice - 0.5) {
            shortfallAmount = Math.round((minPkgPrice - amt) * 100) / 100;
          }
          var amountMatched = isValidSlip && shortfallAmount === 0 && (expAmt > 0 ? Math.abs(amt - expAmt) < 1 : amt >= minPkgPrice);

          // ชั้นที่ 4: ตรวจรหัสอ้างอิงซ้ำ (Anti-Duplicate Ref No ในตาราง direct_orders)
          var isDuplicateRef = false;
          if (isValidSlip && refNo.length >= 6) {
            try {
              var dupUrl = SUPABASE_URL + "/rest/v1/direct_orders?note=ilike.*" + encodeURIComponent(refNo) + "*&select=order_code&limit=1";
              var dupRes = UrlFetchApp.fetch(dupUrl, {
                method: "get",
                headers: { "apikey": SUPABASE_KEY, "Authorization": "Bearer " + SUPABASE_KEY },
                muteHttpExceptions: true
              });
              if (dupRes.getResponseCode() === 200) {
                var dupRows = JSON.parse(dupRes.getContentText());
                if (dupRows && dupRows.length > 0) isDuplicateRef = true;
              }
            } catch (dupErr) {
              Logger.log("Dup ref check error: " + dupErr);
            }
          }

          var rejectReason = "";
          if (!isValidSlip) {
            rejectReason = "ไม่ใช่สลิปโอนเงินธนาคาร (ตรวจพบเป็น: " + (parsed.description || "รูปภาพทั่วไป") + ")";
          } else if (isDuplicateRef) {
            rejectReason = "สลิปโอนเงินนี้ (Ref: " + refNo + ") เคยถูกใช้แจ้งโอนไปแล้วค่ะ";
          } else if (recName && !receiverMatched) {
            rejectReason = "ชื่อผู้รับโอนในสลิป (" + recName + ") ไม่ตรงกับบัญชีร้าน (นายจีรวัฒน์ พลอาจ • 038-0-25363-1)";
          } else if (expAmt > 0 && amt < expAmt - 0.5) {
            rejectReason = "ยอดโอนน้อยกว่าราคาสินค้าค่ะ! โอนมา " + amt.toLocaleString("th-TH") + " บาท แต่ยอดที่ต้องชำระคือ " + expAmt.toLocaleString("th-TH") + " บาท (ยังขาดอีก " + shortfallAmount.toLocaleString("th-TH") + " บาท)";
          } else if (expAmt === 0 && amt < minPkgPrice - 0.5) {
            rejectReason = "ยอดโอนในสลิป (" + amt.toLocaleString("th-TH") + " บาท) น้อยกว่าราคาสินค้าขั้นต่ำของร้าน (ชุด 500 กรัม 390 บาท ส่งฟรี • ยังขาดอีกอย่างน้อย " + shortfallAmount.toLocaleString("th-TH") + " บาท)";
          } else if (expAmt > 0 && !amountMatched) {
            rejectReason = "ยอดเงินในสลิป (" + amt.toLocaleString("th-TH") + " บาท) ไม่ตรงกับยอดที่ต้องชำระ (" + expAmt.toLocaleString("th-TH") + " บาท)";
          }

          var verifiedAll = isValidSlip && !isDuplicateRef && (receiverMatched || !recName) && amountMatched;

          return {
            ok: true,
            is_slip: isValidSlip,
            category: parsed.category || (isValidSlip ? "slip" : "other"),
            amount: amt,
            bank: parsed.bank || "",
            receiver_name: recName,
            receiver_account: recAcc,
            ref_no: refNo,
            date_time: parsed.date_time || "",
            receiver_matched: receiverMatched,
            amount_matched: amountMatched,
            shortfall_amount: shortfallAmount,
            is_underpaid: shortfallAmount > 0,
            is_duplicate_ref: isDuplicateRef,
            verified_all: verifiedAll,
            reject_reason: rejectReason,
            description: parsed.description || (isValidSlip ? "สลิปโอนเงินธนาคาร" : "รูปภาพทั่วไป")
          };
        }
      }
    } catch (err) {
      Logger.log("Groq vision error key " + i + ": " + err);
    }
  }
  return defaultRes;
}

/**
 * API สำหรับหน้าเว็บ (/fish.html) เรียกตรวจสอบรูปภาพที่ลูกค้าแนบว่าเป็นสลิปโอนเงินจริงหรือไม่ (ตรวจครบ 5 ชั้น)
 */
function handleVerifySlipApi(data) {
  var b64 = data.image_base64 || "";
  var mime = data.content_type || "image/jpeg";
  var expectedAmount = Number(data.expected_amount) || 0;
  var vision = analyzeImageWithGroqVision(b64, mime, expectedAmount);
  return ContentService.createTextOutput(JSON.stringify(vision))
    .setMimeType(ContentService.MimeType.JSON);
}

function handleImageMessage(event) {
  const replyToken = event.replyToken;
  const userId = (event.source && event.source.userId) || "ไม่ระบุ";
  const messageId = (event.message && event.message.id) || ("msg_" + Date.now());
  const customerName = getUserDisplayName(userId);
  const nowStr = new Date().toLocaleString("th-TH", { timeZone: "Asia/Bangkok" });
  
  var slipUrl = "";
  var vision = { ok: false, is_slip: false, category: "other", amount: null, bank: "", receiver_name: "", ref_no: "", description: "รูปภาพทั่วไป" };
  var imgBytes = null;
  var contentType = "image/jpeg";

  // 1. ดึงข้อมูลรูปภาพจาก LINE Content API และตรวจสอบด้วย AI Vision ก่อนเสมอ
  try {
    var lineContentUrl = "https://api-data.line.me/v2/bot/message/" + messageId + "/content";
    var imgRes = UrlFetchApp.fetch(lineContentUrl, {
      method: "get",
      headers: {
        "Authorization": "Bearer " + LINE_ACCESS_TOKEN
      },
      muteHttpExceptions: true
    });

    if (imgRes.getResponseCode() === 200) {
      var blob = imgRes.getBlob();
      contentType = blob.getContentType() || "image/jpeg";
      imgBytes = blob.getBytes();
      var b64 = Utilities.base64Encode(imgBytes);
      vision = analyzeImageWithGroqVision(b64, contentType);
    }
  } catch (err) {
    Logger.log("Error fetching/analyzing LINE image: " + err);
  }

  // กรณีที่ 1: รูปที่ส่งมา "ไม่ใช่สลิปโอนเงิน" (เช่น รูปสมุดบัญชี, รูปปลา, รูปอาหาร, รูปสินค้า, รูปทั่วไป)
  if (!vision.is_slip) {
    var nonSlipReply = "";
    if (vision.category === "passbook") {
      nonSlipReply =
        "📸 แอดมินน้องพิมได้รับรูปภาพหน้าสมุดบัญชีแล้วค่ะ (ภาพนี้ยังไม่ใช่ใบเสร็จสลิปโอนเงินนะคะ 😊)\n\n" +
        "หากคุณลูกค้าต้องการโอนชำระค่าสินค้า สามารถโอนเข้าบัญชีร้าน:\n" +
        "🏦 ธนาคารกรุงไทย: 038-0-25363-1 (นายจีรวัฒน์ พลอาจ)\n\n" +
        "เมื่อโอนสำเร็จแล้ว รบกวนส่งภาพ 'สลิปโอนเงินจากแอปธนาคารที่มีเลขที่รายการและยอดเงิน' เข้ามาในแชทนี้ได้เลยนะคะ 🙏✨";
    } else {
      nonSlipReply =
        "📸 แอดมินน้องแพรวได้รับรูปภาพของคุณลูกค้าแล้วค่ะ\n" +
        "(🔍 ระบบ AI ตรวจพบว่าเป็น: " + (vision.description || "รูปภาพทั่วไป") + " — ไม่ใช่สลิปโอนเงินธนาคารนะคะ 😊)\n\n" +
        "• หากต้องการสั่งซื้อปลาสลิดแดดเดียวสุพรรณบุรีแท้ หรือสอบถามข้อมูล พิมพ์ข้อความแจ้งแอดมินได้เลยค่ะ\n" +
        "• หากต้องการแจ้งโอนเงิน กรุณาส่งภาพ 'สลิปโอนเงินธนาคารที่มีรายการโอนสำเร็จและยอดเงินชัดเจน' เข้ามาอีกครั้งนะคะ 🙏💕";
    }

    replyLine(replyToken, [{
      type: "text",
      text: nonSlipReply,
      quickReply: getMasterQuickReply()
    }]);

    pushAdminAlert(
      "📸 [ลูกค้าส่งรูปภาพทั่วไปใน LINE OA — ไม่ใช่สลิปโอนเงิน]\n" +
      "━━━━━━━━━━━━━━━━━━\n" +
      "👤 ชื่อผู้รับ: " + (orderDetails.recipientName || customerName) + " (LINE: " + customerName + ")\n" +
      "🆔 LINE UID: " + userId + "\n" +
      "🔍 AI วิเคราะห์ภาพ: " + (vision.description || "รูปภาพทั่วไป") + " (หมวด: " + (vision.category || "other") + ")\n" +
      "⏰ เวลา: " + nowStr + "\n" +
      "━━━━━━━━━━━━━━━━━━\n" +
      "ℹ️ ระบบคัดกรองอัตโนมัติ: ไม่ได้นำไปผูกเป็นสลิปโอนเงินค่ะ"
    );
    return;
  }

  // กรณีที่ 2: เป็นสลิปโอนเงินธนาคารจริง (vision.is_slip === true && vision.amount > 0)
  if (imgBytes) {
    try {
      var filename = "line_" + messageId + ".jpg";
      var uploadUrl = SUPABASE_URL + "/storage/v1/object/slips/" + filename;
      var upRes = UrlFetchApp.fetch(uploadUrl, {
        method: "post",
        headers: {
          "apikey": SUPABASE_KEY,
          "Authorization": "Bearer " + SUPABASE_KEY,
          "Content-Type": contentType
        },
        payload: imgBytes,
        muteHttpExceptions: true
      });
      if (upRes.getResponseCode() === 200 || upRes.getResponseCode() === 201) {
        slipUrl = SUPABASE_URL + "/storage/v1/object/public/slips/" + filename;
      }
    } catch (err) {
      Logger.log("Error uploading verified slip: " + err);
    }
  }

  // 3. ค้นหาออเดอร์ล่าสุดที่รอโอนเงิน (PENDING + TRANSFER) เพื่อพ่วงสลิปอัตโนมัติ
  var matchedOrder = null;
  try {
    var orderQueryUrl = SUPABASE_URL + "/rest/v1/direct_orders?payment_method=eq.TRANSFER&status=eq.PENDING&order=created_at.desc&limit=5";
    var orderRes = UrlFetchApp.fetch(orderQueryUrl, {
      method: "get",
      headers: {
        "apikey": SUPABASE_KEY,
        "Authorization": "Bearer " + SUPABASE_KEY
      },
      muteHttpExceptions: true
    });

    if (orderRes.getResponseCode() === 200) {
      var pendingOrders = JSON.parse(orderRes.getContentText());
      if (pendingOrders && pendingOrders.length > 0) {
        for (var i = 0; i < pendingOrders.length; i++) {
          var noteStr = String(pendingOrders[i].note || "");
          if (!pendingOrders[i].slip_url && userId && noteStr.indexOf(userId) !== -1) {
            matchedOrder = pendingOrders[i];
            break;
          }
        }
        if (!matchedOrder) {
          for (var j = 0; j < pendingOrders.length; j++) {
            if (!pendingOrders[j].slip_url) {
              matchedOrder = pendingOrders[j];
              break;
            }
          }
        }
      }
    }
  } catch (err) {
    Logger.log("Error querying direct_orders: " + err);
  }

  var ocrSummary = "ยอดโอน: " + (vision.amount ? vision.amount.toLocaleString("th-TH") + " บาท" : "-") +
                   (vision.bank ? " | ธนาคาร: " + vision.bank : "") +
                   (vision.ref_no ? " | Ref: " + vision.ref_no : "");

  // 4. หากพบออเดอร์ที่ตรงกัน ให้อัปเดต slip_url ลงใน Supabase ทันที
  var amountMatchesOrder = matchedOrder && vision.amount && Math.abs(Number(vision.amount) - Number(matchedOrder.price)) < 1;
  if (matchedOrder && slipUrl) {
    try {
      var patchUrl = SUPABASE_URL + "/rest/v1/direct_orders?id=eq." + matchedOrder.id;
      var patchNote = (matchedOrder.note ? matchedOrder.note + " | " : "") + "สลิป LINE (" + ocrSummary + ")";
      UrlFetchApp.fetch(patchUrl, {
        method: "patch",
        headers: {
          "apikey": SUPABASE_KEY,
          "Authorization": "Bearer " + SUPABASE_KEY,
          "Content-Type": "application/json",
          "Prefer": "return=minimal"
        },
        payload: JSON.stringify({
          slip_url: slipUrl,
          slip_verified: !!amountMatchesOrder,
          note: patchNote
        }),
        muteHttpExceptions: true
      });
    } catch (err) {
      Logger.log("Error updating order with slip_url: " + err);
    }
  }

  // 5. ตอบกลับลูกค้าใน LINE พร้อมตรวจสอบกรณีโอนเงินน้อยกว่าราคาสินค้าอย่างเคร่งครัด
  var replyMsg = "";
  var orderExpectedPrice = matchedOrder ? Number(matchedOrder.price) : 0;
  var underpaidDiff = 0;
  if (matchedOrder && vision.amount < orderExpectedPrice - 0.5) {
    underpaidDiff = Math.round((orderExpectedPrice - vision.amount) * 100) / 100;
  } else if (!matchedOrder && vision.amount < 390) {
    underpaidDiff = Math.round((390 - vision.amount) * 100) / 100;
  }

  var replyMessages = [];
  if (vision.receiver_name && !vision.receiver_matched) {
    replyMsg =
      "⚠️ ชื่อผู้รับโอนในสลิปไม่ตรงกับบัญชีร้านค่ะ\n" +
      "• ในสลิป: " + vision.receiver_name + "\n" +
      "• บัญชีร้าน: กรุงไทย 038-0-25363-1 (นายจีรวัฒน์ พลอาจ)\n" +
      "📌 รบกวนส่งสลิปใบที่โอนเข้าบัญชีร้านเข้ามาใหม่นะคะ 🙏";
    replyMessages.push({ type: "text", text: replyMsg, quickReply: getMasterQuickReply() });
  } else if (matchedOrder && underpaidDiff > 0) {
    replyMsg =
      "⚠️ ยอดโอนยังไม่ครบตามออเดอร์ค่ะ\n" +
      "🔖 รหัส: " + matchedOrder.order_code + "\n" +
      "💰 ยอดเต็ม: " + orderExpectedPrice.toLocaleString("th-TH") + " บ. | โอนแล้ว: " + vision.amount.toLocaleString("th-TH") + " บ.\n" +
      "❗ ขาดอีก: " + underpaidDiff.toLocaleString("th-TH") + " บาท\n" +
      "🏦 โอนส่วนต่างเข้า กรุงไทย 038-0-25363-1 (นายจีรวัฒน์ พลอาจ) แล้วส่งสลิปเพิ่มได้เลยค่ะ 🙏";
    replyMessages.push({ type: "text", text: replyMsg, quickReply: getMasterQuickReply() });
  } else if (!matchedOrder && underpaidDiff > 0) {
    replyMsg =
      "⚠️ ยอดโอนน้อยกว่าราคาสินค้าขั้นต่ำค่ะ\n" +
      "💵 ยอดในสลิป: " + vision.amount.toLocaleString("th-TH") + " บ. (ขาดอีกอย่างน้อย " + underpaidDiff.toLocaleString("th-TH") + " บ.)\n" +
      "📦 ราคา: 500g = 390.- | 1 กก. = 550.- | 2 กก. = 1,090.-\n" +
      "🏦 โอนเพิ่มเข้า กรุงไทย 038-0-25363-1 (นายจีรวัฒน์ พลอาจ) แล้วส่งสลิปได้เลยค่ะ 🙏";
    replyMessages.push({ type: "text", text: replyMsg, quickReply: getMasterQuickReply() });
  } else if (matchedOrder) {
    replyMsg =
      "✅ ยืนยันสลิปโอนเงินเรียบร้อยค่ะ!\n" +
      "🔖 รหัส: " + matchedOrder.order_code + "\n" +
      "📦 สินค้า: " + matchedOrder.package_name + "\n" +
      "💵 ยอดโอน: " + vision.amount.toLocaleString("th-TH") + " บาท ✅\n" +
      "🚚 ส่งคิวแพ็กจัดส่งให้ทันทีค่ะ (เช็คเลขพัสดุกดปุ่มด้านล่างได้ตลอดค่ะ) 🙏";
    replyMessages.push({ type: "text", text: replyMsg, quickReply: getMasterQuickReply() });
  } else {
    var inferredPkg = vision.amount >= 950 ? "SKU-SLID-MD-2KG" : (vision.amount >= 500 ? "SKU-SLID-MD-1KG" : "SKU-SLID-MD-500G");
    var inferredPkgName = vision.amount >= 950 ? "ชุดตุนสุดคุ้ม 2 กก." : (vision.amount >= 500 ? "ชุดยอดฮิต 1 กก." : "ชุดพอดีมื้อ 500 กรัม");
    var newCtx = saveUserOrderContext(userId, { slipUrl: slipUrl, slipAmount: vision.amount, packageCode: inferredPkg });
    replyMsg =
      "✅ รับสลิปโอนเงิน " + vision.amount.toLocaleString("th-TH") + " บาท เรียบร้อยค่ะ!\n" +
      "👇 กดปักหมุดที่อยู่จัดส่งด้านล่าง (1/5) เพื่อออกรหัสพัสดุทันทีค่ะ";
    replyMessages.push({ type: "text", text: replyMsg });
    var step1Card = buildStep2AddressGuideFlexMessage(inferredPkgName, vision.amount.toLocaleString("th-TH") + " บาท (โอนแล้ว ✅)", newCtx);
    step1Card.quickReply = getMasterQuickReply();
    replyMessages.push(step1Card);
  }

  replyLine(replyToken, replyMessages);

  // 6. แจ้งเตือนตรงเข้า Telegram Commander ทันที
  var resolvedCustName = (matchedOrder && matchedOrder.customer_name) ? matchedOrder.customer_name : customerName;
  var adminMsg = 
    "🧾 [ยืนยันสลิปโอนเงินจริงจาก LINE OA ✅] 🐟\n" +
    "━━━━━━━━━━━━━━━━━━\n" +
    "👤 ชื่อผู้รับ: " + resolvedCustName + " (LINE: " + customerName + ")\n" +
    "🆔 LINE UID: " + userId + "\n" +
    "💵 ยอดในสลิป (AI OCR): " + vision.amount.toLocaleString("th-TH") + " บาท\n" +
    (vision.bank ? "🏦 ธนาคาร: " + vision.bank + "\n" : "") +
    (vision.receiver_name ? "🎯 ผู้รับโอน: " + vision.receiver_name + "\n" : "") +
    (vision.ref_no ? "🔢 เลขอ้างอิง: " + vision.ref_no + "\n" : "") +
    "⏰ เวลา: " + nowStr + "\n";

  if (matchedOrder) {
    adminMsg += 
      "🔖 พ่วงออเดอร์: " + matchedOrder.order_code + " (" + (amountMatchesOrder ? "✅ ยอดตรง" : "⚠️ ยอดไม่ตรงกับ " + matchedOrder.price + " บ.") + ")\n" +
      "📦 รายการ: " + matchedOrder.package_name + "\n" +
      "📞 เบอร์โทร: " + matchedOrder.phone + "\n";
  } else {
    adminMsg += "⚠️ ยังไม่พบเลขออเดอร์อัตโนมัติ (รอจับคู่ที่อยู่ลูกค้า)\n";
  }

  if (slipUrl) {
    adminMsg += "🖼️ ดูรูปสลิป: " + slipUrl + "\n";
  }

  adminMsg += "━━━━━━━━━━━━━━━━━━\n" +
              "👉 ตรวจสอบในระบบหลังบ้าน: https://watt29.github.io/pakhem-shop/admin.html";

  pushAdminAlert(adminMsg);
}

/**
 * ข้อความต้อนรับ
 */
function sendWelcomeMessage(replyToken) {
  sendFishProductFlexCard(replyToken);
}

function askGroqAI(userPrompt) {
  const systemPrompt = `คุณคือตัวแทนฝ่ายบริการลูกค้าของ 'ทีมงานร้านปลาสลิดป้าเข็ม สุพรรณบุรีแท้'
บุคลิกและน้ำเสียง:
- อบอุ่น สุภาพ นอบน้อม เป็นกันเอง เหมือนพนักงานร้านของกินอร่อยๆ คุยกับลูกค้าด้วยความใส่ใจ
- ใช้ภาษาพูดธรรมชาติ 100% ห้ามใช้ภาษาหุ่นยนต์ ห้ามพูดคำว่า 'ระบบ AI', 'ระบบตอบรับอัตโนมัติ', 'ระบบออนไลน์', 'บอท' หรือศัพท์วิชาการเด็ดขาด
- ห้ามใช้คำว่า 'คน' หรือ 'คนจริง' เด็ดขาด! หากพูดถึงการคุยสายหรือทีมงาน ให้ใช้คำว่า 'เจ้าหน้าที่ฝ่ายบริการลูกค้า' หรือ 'ทีมงานป้าเข็ม'
- ห้ามเอ่ยชื่อจริงบุคคลในการสนทนาทั่วไป ยกเว้นกรณีลูกค้าถามเลขบัญชีเพื่อโอนเงิน ให้แจ้ง: ธนาคารกรุงไทย 038-0-25363-1 (ชื่อบัญชี: นายจีรวัฒน์ พลอาจ)

ข้อมูลความจริงของร้าน:
1. หน้าร้าน/สถานที่: แหล่งผลิตอยู่ที่บางปะหัน อยุธยา ตอนนี้ยังไม่มีหน้าร้านเปิดให้แวะรับนะคะ เราเน้นทำปลาสดใหม่รอบต่อรอบ แล้วแพ็กซองฟอยล์เก็บอุณหภูมิส่งด่วนถึงหน้าบ้านทั่วประเทศค่ะ
2. สินค้า: ปลาสลิดแดดเดียวสุพรรณบุรีแท้ ไซส์จัมโบ้ 4 ตัวโล คัดพิเศษ เป็นปลาเนื้อล้วนคัดพิเศษ เนื้อหนาฟูเป็นลอน มันแทรก หมักเกลือสมุทร 3% เค็มน้อยกำลังดี ไม่เค็มแสบคอ ไม่ไตพัง ตากโดมโซล่าร์สะอาดไร้ฝุ่นแมลงวัน ซีลสูญญากาศแช่ฟรีซได้ 6-12 เดือน (ข้อสำคัญ: ตอนนี้ปลายังไม่วางไข่นะคะ จึงเป็นปลาเนื้อล้วนไซส์ใหญ่คัดพิเศษ ไม่มีปลาไข่เด็ดขาด หากลูกค้าถามหาปลาไข่ ให้ตอบตามตรงอย่างสุภาพว่าช่วงนี้ปลายังไม่วางไข่ค่ะ เป็นปลาเนื้อล้วนตัวใหญ่ เนื้อแน่นหนาฟู มันแทรก ทอดแล้วกรอบอร่อยมาก และไม่ขายแยกตัวเดียวเพราะต้องซีลและแพ็กความเย็นรักษาคุณภาพค่ะ)
3. วิธีทอด: นำออกจากฟรีซพักให้คลายเย็น ไม่ต้องล้างน้ำซ้ำ ทอดน้ำมันไฟกลางค่อนอ่อน หรือใส่หม้อทอดไร้น้ำมัน 160-180°C ด้านละ 10-12 นาที กรอบนอกนุ่มใน
4. 3 แพ็กเกจมาตรฐาน และช่องทางชำระเงิน:
   - ชุดพอดีมื้อ 500 กรัม (ประมาณ 2–3 ตัวใหญ่) : โอน 390.- ส่งฟรี (งดรับ COD | หรือ 11 USDT)
   - ชุดยอดฮิต 1 กิโลกรัม (ประมาณ 4–6 ตัวใหญ่) : โอน 550.- ส่งฟรี (งดรับ COD | หรือ 16 USDT)
   - ชุดตุนสุดคุ้ม 2 กิโลกรัม (ประมาณ 8–12 ตัวใหญ่) : โอน 1,090.- ส่งฟรีรถห้องเย็น (หรือ 31 USDT • ชุด 2kg รับเฉพาะโอนล่วงหน้านะคะ)
   * ช่องทางชำระเงินรองรับ 3 แบบ:
     1) โอนบัญชีธนาคาร: กรุงไทย 038-0-25363-1 (นายจีรวัฒน์ พลอาจ)
     2) ทางร้านจัดส่งหลังรับยอดโอนเงินเท่านั้น (งดรับเก็บปลายทางเพื่อการันตีความสดใหม่ของอาหารแช่แข็ง)
     3) เหรียญดิจิทัล USDT & Bitcoin: USDT เครือข่าย BNB Smart Chain (BEP-20) เลขกระเป๋า: 0x54Debd9f5fA08053B9a37bC3B09Ba5024Ec9dd0b (500g=11 USDT, 1kg=16 USDT, 2kg=31 USDT) หรือ Bitcoin (BTC Native SegWit): bc1qm5029706v00m2sdxl2kw2f9s2exwqg2smajv9v
5. การสั่งซื้อ: ลูกค้าสั่งซื้อง่ายๆ แค่พิมพ์ 'ชื่อ-ที่อยู่-เบอร์โทร' และชุดที่ต้องการในแชทนี้ได้เลยค่ะ เดี๋ยวทีมงานลงคิวจัดส่งด่วนให้ถึงบ้านเลยค่ะ
6. หากลูกค้าขอคุยสาย หรืออยากให้โทรหา: ให้เรียนแจ้งอย่างสุภาพว่า 'ทางร้านรับเรื่องและรับออเดอร์ผ่านแชทนี้เท่านั้นค่ะ (ไม่มีบริการโทรกลับ เพื่อป้องกันการจดที่อยู่ตกหล่น) คุณลูกค้าพิมพ์สอบถามในแชทนี้ได้เลยนะคะ ยินดีดูแลเต็มที่ค่ะ'
7. รับประกันความสด 100%: หากสินค้าเสียหายจากการขนส่ง ทางร้านเคลมส่งชุดใหม่ให้ฟรีทันทีค่ะ

การตอบ: ตอบสั้นกระชับ 2-4 ประโยค ตรงคำถาม สุภาพ อบอุ่น และชวนสั่งซื้ออย่างเป็นธรรมชาติ`;

  const models = ["qwen/qwen3.8-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b"];

  for (let m = 0; m < models.length; m++) {
    const modelName = models[m];
    for (let i = 0; i < GROQ_KEYS.length; i++) {
      const key = GROQ_KEYS[i];
      try {
        const payload = {
          model: modelName,
          messages: [
            { role: "system", content: systemPrompt },
            { role: "user", content: userPrompt }
          ],
          temperature: 0.7,
          max_tokens: 450
        };
        const res = UrlFetchApp.fetch("https://api.groq.com/openai/v1/chat/completions", {
          method: "post",
          headers: {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + key
          },
          payload: JSON.stringify(payload),
          muteHttpExceptions: true
        });
        if (res.getResponseCode() === 200) {
          const json = JSON.parse(res.getContentText());
          if (json.choices && json.choices[0] && json.choices[0].message && json.choices[0].message.content) {
            const content = json.choices[0].message.content.trim();
            if (content.length > 0) {
              return content;
            }
          }
        }
      } catch (e) {}
    }
  }
  return [
    "🐟 [ทีมงานร้านปลาสลิดป้าเข็ม สุพรรณบุรีแท้]",
    "สวัสดีค่ะคุณลูกค้า ทีมงานยินดีให้บริการนะคะ 🙏 สนใจสั่งซื้อปลาสลิดแดดเดียวสุพรรณบุรีแท้ ไซส์จัมโบ้ ไซส์จัมโบ้คัดพิเศษ 4–6 ตัวโล คัดพิเศษ สามารถพิมพ์ 'ชื่อ-ที่อยู่-เบอร์โทร' ในแชทนี้ หรือพิมพ์แจ้งข้อมูลที่ต้องการสอบถามในแชทนี้ได้เลยนะคะ ยินดีดูแลเต็มที่ค่ะ 😊"
  ].join("\n");
}

function getMasterQuickReply() {
  return {
    items: [
      {
        type: "action",
        action: {
          type: "location",
          label: "📍 ปักหมุดที่อยู่จัดส"
        }
      },
      {
        type: "action",
        action: {
          type: "uri",
          label: "🛒 สั่งผ่านเว็บ",
          uri: "https://watt29.github.io/pakhem-shop/fish.html#order-section"
        }
      },
      {
        type: "action",
        action: {
          type: "message",
          label: "🧂 เค็มไหม / รสชาติ",
          text: "เค็มไหม รสชาติเป็นยังไง"
        }
      },
      {
        type: "action",
        action: {
          type: "message",
          label: "🍳 วิธีทอดหม้อทอด",
          text: "วิธีทอดด้วยหม้อทอดไร้น้ำมัน"
        }
      },
      {
        type: "action",
        action: {
          type: "message",
          label: "🔪 บั้งไหม/มีไข่ไหม",
          text: "ทำสะอาดพร้อมทอดไหม มีไข่ไหม"
        }
      }
    ]
  };
}

/**
 * การ์ด Flex Message ขั้นที่ 1: เลือกวิธีชำระเงินด้วยปุ่มใหญ่ในหน้าแชท (มองเห็นชัดเจนแม้เปิด Rich Menu ค้างไว้!)
 */
function buildStep1PaymentFlexMessage(pkgCode, titleText, specText, transferPrice, codPrice, coldPrice) {
  var buttons = [
    {
      type: "button",
      style: "primary",
      color: "#059669",
      height: "sm",
      action: {
        type: "message",
        label: "🏦 โอน " + transferPrice.toLocaleString("th-TH") + ".- ส่งฟรี",
        text: "เลือกโอนเงิน " + titleText + " (" + transferPrice + ".-)"
      }
    }
  ];
  // COD completely disabled
  if (coldPrice > 0) {
    buttons.push({
      type: "button",
      style: "secondary",
      height: "sm",
      margin: "sm",
      action: {
        type: "message",
        label: "❄️ รถเย็น " + coldPrice.toLocaleString("th-TH") + ".-",
        text: "เลือกส่งรถห้องเย็น " + titleText + " (" + coldPrice + ".-)"
      }
    });
  }
  buttons.push({
    type: "button",
    style: "link",
    height: "sm",
    margin: "xs",
    action: {
      type: "uri",
      label: "📍 ปักหมุดส่งที่อยู่",
      uri: "https://line.me/R/nv/location/"
    }
  });

  return {
    type: "flex",
    altText: "เลือกวิธีชำระเงินสำหรับ " + titleText,
    quickReply: getPaymentStepQuickReply(pkgCode),
    contents: {
      type: "bubble",
      size: "mega",
      header: {
        type: "box",
        layout: "vertical",
        backgroundColor: "#0f172a",
        paddingAll: "14px",
        contents: [
          { type: "text", text: "ขั้นที่ 1/2 : เลือกวิธีชำระเงิน", color: "#fbbf24", size: "xs", weight: "bold" },
          { type: "text", text: "🐟 " + titleText, color: "#ffffff", size: "md", weight: "bold", wrap: true, margin: "xs" },
          { type: "text", text: specText, color: "#cbd5e1", size: "xs", wrap: true, margin: "xs" }
        ]
      },
      body: {
        type: "box",
        layout: "vertical",
        paddingAll: "14px",
        spacing: "sm",
        contents: [
          {
            type: "text",
            text: "👇 กดปุ่มสีเขียวหรือสีส้มในกล่องนี้ได้เลยค่ะ (ไม่ต้องพิมพ์เอง):",
            size: "sm",
            weight: "bold",
            color: "#1e293b",
            wrap: true
          }
        ].concat(buttons)
      }
    }
  };
}

/**
 * การ์ด Flex Message ขั้นที่ 2: นำทางส่งที่อยู่แบบไม่ต้องพิมพ์ยาว (ปุ่มปักหมุดแผนที่ในการ์ด + ปุ่มใช้ที่อยู่เดิม + ปุ่มคัดลอกเลขบัญชี)
 */
function buildStep2AddressGuideFlexMessage(selName, payLabel, amount, isTransfer, hasPrev, prevAddressText) {
  var bodyContents = [
    { type: "text", text: "🐟 " + selName, weight: "bold", size: "sm", color: "#065f46", wrap: true },
    { type: "text", text: payLabel, weight: "bold", size: "xs", color: "#b91c1c", margin: "xs", wrap: true }
  ];

  if (hasPrev && prevAddressText) {
    bodyContents.push({
      type: "box",
      layout: "vertical",
      backgroundColor: "#f0fdf4",
      borderColor: "#86efac",
      borderWidth: "1px",
      cornerRadius: "8px",
      paddingAll: "10px",
      margin: "md",
      contents: [
        { type: "text", text: "🏠 ข้อมูลจัดส่งเดิมที่บันทึกไว้:", size: "xxs", weight: "bold", color: "#065f46" },
        { type: "text", text: prevAddressText, size: "xs", color: "#1e293b", wrap: true, margin: "xs" }
      ]
    });
    bodyContents.push({
      type: "button",
      style: "primary",
      color: "#059669",
      height: "sm",
      margin: "sm",
      action: {
        type: "message",
        label: "✅ ใช้ชื่อ-เบอร์-ที่อยู่เดิมนี้",
        text: "ยืนยันใช้ที่อยู่เดิม"
      }
    });
  }

  bodyContents.push({
    type: "button",
    style: "primary",
    color: "#0284c7",
    height: "sm",
    margin: "md",
    action: {
      type: "uri",
      label: "📍 กดปักหมุดแผนที่",
      uri: "https://line.me/R/nv/location/"
    }
  });

  bodyContents.push({
    type: "button",
    style: "secondary",
    height: "sm",
    margin: "sm",
    action: {
      type: "postback",
      label: "📮 พิมพ์รหัสไปรษณีย์",
      data: "action=fill_zip_direct",
      inputOption: "openKeyboard",
      fillInText: "รหัสไปรษณีย์: "
    }
  });

  return {
    type: "flex",
    altText: "1/5 ปักหมุดที่อยู่จัดส่ง",
    quickReply: getFinalAddressStepQuickReply(isTransfer, hasPrev),
    contents: {
      type: "bubble",
      size: "mega",
      header: {
        type: "box",
        layout: "vertical",
        backgroundColor: "#065f46",
        paddingAll: "12px",
        contents: [
          { type: "text", text: "📍 1/5 : ปักหมุดที่อยู่จัดส่ง", color: "#ffffff", size: "md", weight: "bold" }
        ]
      },
      body: {
        type: "box",
        layout: "vertical",
        paddingAll: "14px",
        contents: bodyContents
      }
    }
  };
}

function buildFinalPaymentConfirmCard(ctx, stepBadge) {
  var badge = stepBadge || "2/5";
  var pkgCode = ctx.packageCode || "SKU-SLID-MD-1KG";
  var is500 = pkgCode === "SKU-SLID-MD-500G";
  var is2kg = pkgCode === "SKU-SLID-MD-2KG";
  var titleText = is2kg ? "ชุดตุนสุดคุ้ม 2 กิโลกรัม" : (is500 ? "ชุดพอดีมื้อ 500 กรัม" : "ชุดยอดฮิต 1 กิโลกรัม");
  var trPrice = is2kg ? 1090 : (is500 ? 390 : 550);
  var codPrice = is2kg ? 0 : (is500 ? 410 : 570);
  var coldPrice = is2kg ? 0 : (is500 ? 490 : 650);

  var rInfo = calculateShippingRouteInfo(ctx.savedAddress || "");
  var distKm = ctx.distanceKm || rInfo.distanceKm;
  var estDays = ctx.estDays || rInfo.estDays;
  var allowCod = (typeof ctx.allowCod === "boolean") ? ctx.allowCod : rInfo.allowCod;

  var payButtons = [];
  if (!allowCod && !is2kg) {
    // พื้นที่ 3–4 วัน (> 350 กม.): แนะนำส่งรถห้องเย็น / โอนเงินล่วงหน้า (งดเก็บเงินปลายทาง COD)
    payButtons.push({
      type: "button",
      style: "primary",
      color: "#0284c7",
      height: "sm",
      margin: "md",
      action: {
        type: "message",
        label: "❄️ รถเย็น " + coldPrice + ".-",
        text: "เลือกส่งรถห้องเย็น " + titleText + " (" + coldPrice + ".-)"
      }
    });
    payButtons.push({
      type: "button",
      style: "primary",
      color: "#059669",
      height: "sm",
      margin: "sm",
      action: {
        type: "message",
        label: "🏦 โอน " + trPrice + ".- ส่งฟรี",
        text: "เลือกโอนเงิน " + titleText + " (" + trPrice + ".-)"
      }
    });
  } else {
    // พื้นที่ 1–2 วัน (≤ 350 กม.): มีปุ่มกดเลือกทั้ง "โอนชำระเงิน (ส่งฟรี)" และ "เก็บเงินปลายทาง (COD)"
    payButtons.push({
      type: "button",
      style: "primary",
      color: "#059669",
      height: "sm",
      margin: "md",
      action: {
        type: "message",
        label: is2kg ? "❄️ โอน 1,090.- ส่งฟรี" : ("🏦 โอน " + trPrice + ".- ส่งฟรี"),
        text: "เลือกโอนเงิน " + titleText + " (" + trPrice + ".-)"
      }
    });
    // COD completely disabled
    if (coldPrice > 0) {
      payButtons.push({
        type: "button",
        style: "secondary",
        height: "sm",
        margin: "sm",
        action: {
          type: "message",
          label: "❄️ รถเย็น " + coldPrice + ".-",
          text: "เลือกส่งรถห้องเย็น " + titleText + " (" + coldPrice + ".-)"
        }
      });
    }
  }

  var bodyDetails = [
    { type: "text", text: "📦 " + titleText, size: "xs", weight: "bold", color: "#0f172a", wrap: true },
    { type: "text", text: "📍 " + (ctx.savedAddress || "ต้นทาง อ.บางปะหัน จ.อยุธยา"), size: "xs", color: "#334155", wrap: true },
    { type: "text", text: "🛣️ ระยะทาง ~" + distKm.toLocaleString("th-TH") + " กม. • ⏱️ ถึงใน " + estDays, size: "xs", weight: "bold", color: "#059669", wrap: true }
  ];
  if (ctx.savedName || ctx.savedPhone) {
    bodyDetails.push({
      type: "text",
      text: "👤 " + (ctx.savedName || "-") + (ctx.savedPhone ? " (" + ctx.savedPhone + ")" : ""),
      size: "xs",
      color: "#334155",
      wrap: true
    });
  }
  bodyDetails.push({
    type: "text",
    text: allowCod && !is2kg
      ? "👇 กดเลือก โอนเงิน(ส่งฟรี) หรือ เก็บปลายทาง:"
      : "❄️ พื้นที่ส่ง " + estDays + " (รับเฉพาะโอนเงินล่วงหน้าค่ะ):",
    size: "xs",
    weight: "bold",
    color: allowCod && !is2kg ? "#1e40af" : "#b45309",
    wrap: true,
    margin: "xs"
  });

  return {
    type: "flex",
    altText: badge + " เลือกวิธีชำระเงิน",
    quickReply: getPaymentStepQuickReply(pkgCode),
    contents: {
      type: "bubble",
      size: "mega",
      header: {
        type: "box",
        layout: "vertical",
        backgroundColor: "#0f172a",
        paddingAll: "12px",
        contents: [
          { type: "text", text: "💳 " + badge + " : เลือกวิธีชำระเงิน", color: "#34d399", size: "md", weight: "bold" }
        ]
      },
      body: {
        type: "box",
        layout: "vertical",
        paddingAll: "14px",
        spacing: "xs",
        contents: bodyDetails.concat(payButtons)
      }
    }
  };
}


function replyLine(replyToken, messages) {
  const url = "https://api.line.me/v2/bot/message/reply";
  const payload = { replyToken: replyToken, messages: messages };
  UrlFetchApp.fetch(url, {
    method: "post",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${LINE_ACCESS_TOKEN}`
    },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  });
}

function pushAdminAlert(text) {
  if (!TELEGRAM_BOT_TOKEN || !TELEGRAM_CHAT_ID) return;
  const url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage";
  const payload = {
    chat_id: TELEGRAM_CHAT_ID,
    text: text,
    disable_web_page_preview: true
  };
  try {
    UrlFetchApp.fetch(url, {
      method: "post",
      contentType: "application/json",
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    });
  } catch (e) {
    Logger.log("Telegram push error: " + e);
  }
}

/**
 * ส่งการ์ดสินค้า "ปลาแดดเดียว ป้าเข็ม คัดพิเศษ" (สินค้าตัวเอง 100% Direct D2C)
 */
function sendFishProductFlexCard(replyToken) {
  var fishImg = "https://watt29.github.io/pakhem-shop/fried_fish.jpg";
  var orderWebUrl = "https://watt29.github.io/pakhem-shop/fish.html";

  var fishBubble = {
    type: "bubble",
    size: "mega",
    hero: {
      type: "image",
      url: fishImg,
      size: "full",
      aspectRatio: "16:10",
      aspectMode: "cover",
      action: {
        type: "uri",
        uri: orderWebUrl
      }
    },
    body: {
      type: "box",
      layout: "vertical",
      spacing: "md",
      contents: [
        {
          type: "box",
          layout: "horizontal",
          contents: [
            {
              type: "text",
              text: "⭐ ปลาสลิดไซส์จัมโบ้ 4 ตัวโล คัดพิเศษ (คัดพิเศษ 100%)",
              size: "xxs",
              color: "#FFFFFF",
              weight: "bold"
            }
          ],
          backgroundColor: "#D97706",
          paddingAll: "4px",
          paddingStart: "8px",
          paddingEnd: "8px",
          cornerRadius: "12px",
          width: "240px"
        },
        {
          type: "text",
          text: "🐟 ปลาสลิดแดดเดียว ไซส์จัมโบ้ 4 ตัวโล คัดพิเศษ",
          weight: "bold",
          size: "lg",
          color: "#1E293B",
          wrap: true
        },
        {
          type: "text",
          text: "✨ \"ปลาสลิดสุพรรณบุรีแท้ ไซส์ใหญ่ ไซส์จัมโบ้คัดพิเศษ 4–6 ตัวโล คัดพิเศษ เนื้อแน่นหนาเป็นลอน เค็มกำลังดี ทอดกรอบนอกนุ่มฟู\"\n\n🐟 คัดไซส์ใหญ่พิเศษ ไซส์จัมโบ้คัดพิเศษ 4–6 ตัวใหญ่/กิโลกรัม (ชั่งตามน้ำหนักจริง) เนื้อแน่นทุกล็อต\n☀️ ตากสะอาดในโรงมุ้งโซล่าร์ ไร้ฝุ่น ไร้แมลงวัน 100%\n🧂 หมักเกลือสมุทรสูตรโบราณ เค็มพอดี ไม่เค็มไตพัง\n📦 ซีลสูญญากาศ PA/PE มาตรฐานญี่ปุ่น ตุนฟรีซ 1–2 ปี",
          size: "xs",
          color: "#475569",
          wrap: true
        },
        {
          type: "box",
          layout: "vertical",
          spacing: "xs",
          backgroundColor: "#FFFBEB",
          paddingAll: "10px",
          cornerRadius: "8px",
          borderColor: "#FDE68A",
          borderWidth: "1px",
          contents: [
            {
              type: "box",
              layout: "horizontal",
              contents: [
                { type: "text", text: "• ชุด 500 กรัม (ประมาณ 2–3 ตัวใหญ่):", size: "xs", color: "#92400E" },
                { type: "text", text: "โอน 390.- ฟรี! (งดรับ COD)", size: "xs", weight: "bold", color: "#B45309", align: "end" }
              ]
            },
            {
              type: "box",
              layout: "horizontal",
              contents: [
                { type: "text", text: "• ชุด 1 กิโลกรัม (ประมาณ 4–6 ตัวใหญ่):", size: "xs", weight: "bold", color: "#B45309" },
                { type: "text", text: "โอน 550.- ฟรี! (งดรับ COD)", size: "xs", weight: "bold", color: "#D97706", align: "end" }
              ]
            },
            {
              type: "box",
              layout: "horizontal",
              contents: [
                { type: "text", text: "• ชุด 2 กิโลกรัม (ประมาณ 8–12 ตัวใหญ่):", size: "xs", color: "#92400E" },
                { type: "text", text: "โอน 1,090.- (ฟรีรถเย็น)", size: "xs", weight: "bold", color: "#059669", align: "end" }
              ]
            }
          ]
        },
        {
          type: "box",
          layout: "vertical",
          spacing: "xs",
          backgroundColor: "#EFF6FF",
          paddingAll: "8px",
          cornerRadius: "8px",
          contents: [
            {
              type: "text",
              text: "🚚 พื้นที่ส่งถึงใน 1–2 วัน: แพ็กแช่แข็งซองฟอยล์ (รับโอน & ปลายทาง COD)",
              size: "xxs",
              color: "#1E40AF",
              wrap: true
            },
            {
              type: "text",
              text: "❄️ พื้นที่ส่งใช้เวลา 3–4 วัน: ส่งด้วยรถห้องเย็น (ชำระเงินเต็มจำนวน งดรับ COD)",
              size: "xxs",
              color: "#0F766E",
              wrap: true
            }
          ]
        }
      ]
    },
    footer: {
      type: "box",
      layout: "vertical",
      spacing: "sm",
      contents: [
        {
          type: "button",
          style: "primary",
          color: "#EA580C",
          height: "sm",
          action: {
            type: "uri",
            label: "🛒 สั่งซื้อทันที (โอน",
            uri: orderWebUrl
          }
        },
        {
          type: "button",
          style: "secondary",
          height: "sm",
          action: {
            type: "message",
            label: "💬 สั่งซื้อผ่านแชทนี้",
            text: "สั่งซื้อปลาแดดเดียว 1 กิโลกรัม"
          }
        }
      ]
    }
  };

  replyLine(replyToken, [
    {
      type: "flex",
      altText: "🐟 ปลาแดดเดียว ป้าเข็ม คัดพิเศษ (สูตรโบราณ เค็มน้อย ปลอดสาร 100%)",
      contents: fishBubble,
      quickReply: getMasterQuickReply()
    }
  ]);
}

/**
 * จัดการออเดอร์ปลาแดดเดียวที่ส่งตรงจากเว็บ (Web D2C Checkout)
 */
function sha256Hex(input) {
  if (!input) return null;
  var clean = String(input).trim().toLowerCase();
  var rawHash = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, clean, Utilities.Charset.UTF_8);
  var out = "";
  for (var i = 0; i < rawHash.length; i++) {
    var b = rawHash[i];
    if (b < 0) b += 256;
    var hex = b.toString(16);
    if (hex.length === 1) out += "0";
    out += hex;
  }
  return out;
}

function getMetaPixelConfig() {
  try {
    var url = SUPABASE_URL + "/rest/v1/system_preferences?key=eq.meta_pixel_config&select=value";
    var r = UrlFetchApp.fetch(url, {
      headers: { "apikey": SUPABASE_KEY, "Authorization": "Bearer " + SUPABASE_KEY },
      muteHttpExceptions: true
    });
    if (r.getResponseCode() === 200) {
      var rows = JSON.parse(r.getContentText()) || [];
      if (rows.length > 0 && rows[0].value && rows[0].value.pixel_id) return rows[0].value;
    }
  } catch (e) {}
  return { pixel_id: "1307380735783361", capi_token: FB_PAGE_ACCESS_TOKEN, mode: "AUTO" };
}

function saveMetaPixelConfig(pixelId, capiToken) {
  var cfg = getMetaPixelConfig();
  if (pixelId !== undefined) cfg.pixel_id = String(pixelId).trim();
  if (capiToken !== undefined && capiToken) cfg.capi_token = String(capiToken).trim();
  var payload = {
    key: "meta_pixel_config",
    value: cfg,
    updated_at: new Date().toISOString()
  };
  var url = SUPABASE_URL + "/rest/v1/system_preferences?on_conflict=key";
  var r = UrlFetchApp.fetch(url, {
    method: "post",
    headers: {
      "apikey": SUPABASE_KEY,
      "Authorization": "Bearer " + SUPABASE_KEY,
      "Content-Type": "application/json",
      "Prefer": "resolution=merge-duplicates,return=minimal"
    },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  });
  return r.getResponseCode() >= 200 && r.getResponseCode() < 300;
}

function sendMetaConversionEvent(orderData) {
  try {
    var cfg = getMetaPixelConfig();
    var pixelId = (cfg && cfg.pixel_id) ? String(cfg.pixel_id).trim() : "";
    if (!pixelId) return { ok: false, reason: "no_pixel_id" };
    var accessToken = (cfg && cfg.capi_token) ? cfg.capi_token : FB_PAGE_ACCESS_TOKEN;

    var rawPhone = String(orderData.phone || "").replace(/[^0-9]/g, "");
    if (rawPhone.indexOf("0") === 0) rawPhone = "66" + rawPhone.substring(1);

    var userData = {
      country: [sha256Hex("th")]
    };
    if (rawPhone) userData.ph = [sha256Hex(rawPhone)];
    if (orderData.name) userData.fn = [sha256Hex(orderData.name)];
    if (orderData.fbc) userData.fbc = orderData.fbc;
    if (orderData.fbp) userData.fbp = orderData.fbp;
    if (orderData.user_agent) userData.client_user_agent = orderData.user_agent;

    var eventPayload = {
      data: [{
        event_name: "Purchase",
        event_time: Math.floor(Date.now() / 1000),
        event_id: orderData.order_id,
        action_source: orderData.action_source || "website",
        event_source_url: orderData.event_source_url || "https://watt29.github.io/pakhem-shop/fish.html",
        user_data: userData,
        custom_data: {
          currency: "THB",
          value: Number(orderData.price) || 550,
          content_name: orderData.package_name || "ปลาสลิดแดดเดียว ป้าเข็ม คัดพิเศษ",
          content_ids: [orderData.package_code || "SKU-SLID-MD-1KG"],
          content_type: "product",
          num_items: 1
        }
      }]
    };

    var url = "https://graph.facebook.com/v19.0/" + encodeURIComponent(pixelId) + "/events?access_token=" + encodeURIComponent(accessToken);
    var r = UrlFetchApp.fetch(url, {
      method: "post",
      contentType: "application/json",
      payload: JSON.stringify(eventPayload),
      muteHttpExceptions: true
    });
    return { ok: r.getResponseCode() === 200, code: r.getResponseCode() };
  } catch (e) {
    Logger.log("Meta CAPI error: " + e);
    return { ok: false, error: String(e) };
  }
}

function handleDirectWebOrder(data) {
  var now = new Date();
  var nowStr = now.toLocaleString("th-TH", { timeZone: "Asia/Bangkok" });
  var orderId = data.order_id || ("PKF-" + Utilities.formatDate(now, "Asia/Bangkok", "MMddHHmmss"));
  var pkgName = data.package_name || ("ปลาแดดเดียว ชุด " + (data.package || "1kg"));
  var price = Number(data.price) || 550.0;
  var payMethod = (data.payment_method || "COD").toUpperCase();
  var payBadge = payMethod === "COD" ? "🚚 เก็บเงินปลายทาง (COD)" : "💳 โอนเงิน / พร้อมเพย์";
  var sourceBadge = data.fbc ? "🎯 โฆษณา Facebook Ads (fbclid Verified)" : "🌐 หน้าเว็บโดยตรง / ออร์แกนิก";

  // เติม อำเภอ/จังหวัด อัตโนมัติจากรหัสไปรษณีย์ และบังคับตรวจ ตำบล/อำเภอ/จังหวัด + เบอร์โทร 10 หลัก ก่อนเปิดบิล
  var enrichedWebAddr = enrichThaiAddressWithMaps(data.address || "");
  data.address = enrichedWebAddr;
  var phoneCheckWeb = validateThaiPhoneNumber(data.phone || "");
  if (!phoneCheckWeb.valid) {
    return ContentService.createTextOutput(JSON.stringify({
      ok: false,
      error: "เบอร์โทรศัพท์ไม่ถูกต้อง (" + phoneCheckWeb.reason + ") กรุณาระบุเบอร์โทรศัพท์จริง 10 หลัก"
    })).setMimeType(ContentService.MimeType.JSON);
  }
  data.phone = phoneCheckWeb.phone;
  if (!hasCompleteThaiAddress(enrichedWebAddr)) {
    return ContentService.createTextOutput(JSON.stringify({
      ok: false,
      error: "ที่อยู่จัดส่งยังไม่ครบถ้วน กรุณาระบุ บ้านเลขที่ ตำบล/แขวง อำเภอ/เขต และจังหวัด ให้ครบถ้วนค่ะ"
    })).setMimeType(ContentService.MimeType.JSON);
  }

  var savedByServer = null;
  if (!data.skip_db) {
    try {
      var supaPayload = {
        order_code: orderId,
        product_name: "ปลาสลิดแดดเดียว ไซส์จัมโบ้ 4 ตัวโล คัดพิเศษ ป้าเข็ม คัดพิเศษ",
        package_code: data.package || "SKU-SLID-MD-1KG",
        package_name: pkgName,
        price: price,
        customer_name: data.name || "ไม่ระบุ",
        phone: data.phone || "ไม่ระบุ",
        address: data.address || "ไม่ระบุ",
        payment_method: payMethod,
        status: "PENDING",
        note: data.note || null,
        slip_url: data.slip_url || null,
        created_at: now.toISOString()
      };
      var insRes = UrlFetchApp.fetch(SUPABASE_URL + "/rest/v1/direct_orders?on_conflict=order_code", {
        method: "post",
        headers: {
          "apikey": SUPABASE_KEY,
          "Authorization": "Bearer " + SUPABASE_KEY,
          "Content-Type": "application/json",
          "Prefer": "resolution=ignore-duplicates,return=minimal"
        },
        payload: JSON.stringify(supaPayload),
        muteHttpExceptions: true
      });
      savedByServer = insRes.getResponseCode() >= 200 && insRes.getResponseCode() < 300;
      if (!savedByServer) Logger.log("Supabase fallback insert failed: " + insRes.getResponseCode() + " " + insRes.getContentText());
    } catch (err) {
      savedByServer = false;
      Logger.log("Supabase insert order error: " + err);
    }
  }

  // ซิงค์ออเดอร์ยอดขายลง Google Sheets อัตโนมัติทันที
  try {
    recordOrderToGoogleSheet(nowStr, Utilities.formatDate(now, "Asia/Bangkok", "yyyy-MM-dd"), orderId, pkgName, data.name || "ลูกค้า", price, "Direct Web");
  } catch (sheetErr) {
    Logger.log("recordOrderToGoogleSheet error: " + sheetErr);
  }

  // ยิงข้อมูล Conversion API (CAPI) กลับไปสอน AI ของ Facebook อัตโนมัติ
  var capiRes = sendMetaConversionEvent({
    order_id: orderId,
    name: data.name,
    phone: data.phone,
    price: price,
    package_code: data.package || "SKU-SLID-MD-1KG",
    package_name: pkgName,
    fbc: data.fbc || null,
    fbp: data.fbp || null,
    user_agent: data.user_agent || null,
    event_source_url: data.event_source_url || "https://watt29.github.io/",
    action_source: "website"
  });

  var alertMsg = "🐟 [ออเดอร์ใหม่] ปลาแดดเดียว ป้าเข็ม (สินค้าตัวเอง 100%)\n" +
                 "━━━━━━━━━━━━━━━━━━━\n" +
                 "🔖 รหัสสั่งซื้อ: " + orderId + "\n" +
                 "⏰ เวลา: " + nowStr + "\n" +
                 "👤 ลูกค้า: " + (data.name || "-") + "\n" +
                 "📞 โทร: " + (data.phone || "-") + "\n" +
                 "📦 สินค้า: " + pkgName + "\n" +
                 "💰 ยอดเก็บเงิน: " + price.toLocaleString("th-TH") + " บาท\n" +
                 "💵 วิธีชำระ: " + payBadge + "\n" +
                 "📡 แหล่งที่มา: " + sourceBadge + "\n" +
                 (savedByServer === true ? "🛟 บันทึกผ่านระบบสำรอง (เซิร์ฟเวอร์)\n" : "") +
                 (savedByServer === false ? "🚨 บันทึกฐานข้อมูลไม่สำเร็จ! โปรดคัดลอกออเดอร์นี้เก็บไว้\n" : "") +
                 "📍 ที่อยู่จัดส่ง:\n" + (data.address || "-") + "\n";
  if (data.note) {
    alertMsg += "📝 โน้ต: " + data.note + "\n";
  }
  if (capiRes && capiRes.ok) {
    alertMsg += "✅ ส่งสัญญาณ Purchase สอน AI Facebook (CAPI) สำเร็จ\n";
  }
  alertMsg += "━━━━━━━━━━━━━━━━━━━\n" +
              "👉 เตรียมแพ็คซีลสูญญากาศและส่งรถเย็นรอบถัดไปได้เลยครับ";

  pushAdminAlert(alertMsg);
  checkTelegramWebhookHealth();

  // หากลูกค้ากดลิงก์มาจาก LINE (มี line_uid) ให้ส่งใบเสร็จยืนยันออเดอร์เด้งกลับเข้าแชท LINE ของลูกค้าทันที!
  var lineUid = data.line_uid || "";
  if (!lineUid && data.note) {
    var uidMatch = String(data.note).match(/\[LINE_UID:([^\]]+)\]/);
    if (uidMatch && uidMatch[1]) lineUid = uidMatch[1];
  }
  if (lineUid) {
    try {
      saveUserOrderContext(lineUid, { packageCode: null, payMode: null, savedName: null, savedPhone: null, savedAddress: null, slipUrl: null, slipAmount: null });
      var webReceiptMsg =
        "📝 [ยืนยันคำสั่งซื้อจากหน้าเว็บสำเร็จ 100%] 🎉\n" +
        "ขอบพระคุณมากนะคะคุณ " + (data.name || "ลูกค้า") + " 🙏✨\n" +
        "━━━━━━━━━━━━━━━━━━\n" +
        "🔖 รหัสคำสั่งซื้อ: " + orderId + "\n" +
        "👤 ชื่อผู้รับ: " + (data.name || "-") + "\n" +
        "📦 สินค้า: " + pkgName + "\n" +
        "💵 ยอดชำระ: " + price.toLocaleString("th-TH") + " บาท\n" +
        "💳 วิธีชำระ: " + payBadge + "\n" +
        "📞 เบอร์โทร: " + (data.phone || "-") + "\n" +
        "🏠 ที่อยู่จัดส่ง:\n" + (data.address || "-") + "\n" +
        "━━━━━━━━━━━━━━━━━━\n" +
        "🚚 ระบบเชื่อมข้อมูลเข้าคิวแพ็คซีลสูญญากาศเรียบร้อยแล้วค่ะ เมื่อจัดส่งแล้วระบบจะแจ้งเลขพัสดุในแชทนี้อัตโนมัติค่ะ 😊";
      UrlFetchApp.fetch("https://api.line.me/v2/bot/message/push", {
        method: "post",
        contentType: "application/json",
        headers: { "Authorization": "Bearer " + LINE_ACCESS_TOKEN },
        payload: JSON.stringify({
          to: lineUid,
          messages: [{ type: "text", text: webReceiptMsg, quickReply: getMasterQuickReply() }]
        }),
        muteHttpExceptions: true
      });
    } catch (pushErr) {
      Logger.log("Push web receipt to LINE error: " + pushErr);
    }
  }

  return ContentService.createTextOutput(JSON.stringify({
    ok: true,
    order_id: orderId,
    saved: savedByServer !== false,
    capi_sent: !!(capiRes && capiRes.ok),
    message: "บันทึกออเดอร์สำเร็จเรียบร้อยค่ะ ป้าเข็มกำลังจัดเตรียมปลาแดดเดียวส่งตรงถึงบ้านคุณนะคะ!"
  })).setMimeType(ContentService.MimeType.JSON);
}

function sendTelegramDirect(chatId, text, replyMarkup) {
  try {
    var defaultMarkup = {
      keyboard: [
        [{ text: "📊 สรุปยอดขาย & แอด" }, { text: "💰 บัญชีกำไรขาดทุน" }],
        [{ text: "📦 ดูออเดอร์ล่าสุด" }, { text: "📑 เปิด Google Sheets" }]
      ],
      resize_keyboard: true,
      is_persistent: true
    };
    var payload = {
      chat_id: chatId,
      text: text,
      reply_markup: replyMarkup || defaultMarkup
    };
    var url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage";
    UrlFetchApp.fetch(url, {
      method: "post",
      contentType: "application/json",
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    });
  } catch (e) {
    Logger.log("sendTelegramDirect error: " + e);
  }
}

function handleTelegramWebhookUpdate(data) {
  try {
    var msg = data.message || {};
    var chatId = msg.chat && msg.chat.id;
    if (!chatId) return;

    // 🔒 Admin-only guard: ignore everyone except the shop admin chat
    if (String(chatId) !== String(TELEGRAM_CHAT_ID)) {
      sendTelegramDirect(chatId, "⚠️ บอทนี้ใช้งานได้เฉพาะแอดมินร้านเท่านั้นค่ะ", { remove_keyboard: true });
      Logger.log("Blocked non-admin Telegram chat: " + chatId);
      return;
    }

    // 0.0 หากแอดมินส่งรูปภาพเข้ามาใน Telegram → ใช้ AI Vision ตรวจสอบว่าเป็นสลิปโอนเงินจริงหรือไม่
    if (msg.photo && msg.photo.length > 0 && !msg.text) {
      try {
        var bestPhoto = msg.photo[msg.photo.length - 1];
        var getFileRes = UrlFetchApp.fetch("https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/getFile?file_id=" + encodeURIComponent(bestPhoto.file_id), { muteHttpExceptions: true });
        var fileInfo = JSON.parse(getFileRes.getContentText());
        if (fileInfo && fileInfo.ok && fileInfo.result && fileInfo.result.file_path) {
          var tgFileUrl = "https://api.telegram.org/file/bot" + TELEGRAM_BOT_TOKEN + "/" + fileInfo.result.file_path;
          var tgImgBlob = UrlFetchApp.fetch(tgFileUrl, { muteHttpExceptions: true }).getBlob();
          var tgVision = analyzeImageWithGroqVision(Utilities.base64Encode(tgImgBlob.getBytes()), tgImgBlob.getContentType() || "image/jpeg");
          if (tgVision.is_slip) {
            sendTelegramDirect(chatId,
              "✅ [AI ตรวจพบสลิปโอนเงินจริง! 🧾]\n" +
              "━━━━━━━━━━━━━━━━━━\n" +
              "• 💵 ยอดเงินโอน: " + tgVision.amount.toLocaleString("th-TH") + " บาท\n" +
              "• 🏦 ธนาคาร: " + (tgVision.bank || "-") + "\n" +
              "• 🎯 ผู้รับโอน: " + (tgVision.receiver_name || "-") + "\n" +
              "• 🔢 เลขอ้างอิง: " + (tgVision.ref_no || "-") + "\n" +
              "• 📝 รายละเอียด: " + (tgVision.description || "-"));
          } else {
            sendTelegramDirect(chatId,
              "⚠️ [รูปนี้ไม่ใช่สลิปโอนเงินค่ะ 🔍]\n" +
              "━━━━━━━━━━━━━━━━━━\n" +
              "• 🤖 AI ตรวจพบเป็น: " + (tgVision.description || "รูปภาพทั่วไป") + "\n" +
              "• 📂 หมวดภาพ: " + (tgVision.category || "other") + "\n" +
              "• 🛡️ สถานะ: ระบบคัดกรองไม่เหมาเป็นสลิปโอนเงินค่ะ");
          }
          return;
        }
      } catch (tgPhotoErr) {
        Logger.log("TG photo vision error: " + tgPhotoErr);
      }
    }

    var text = (msg.text || "").trim();
    if (!text) return;

    var lower = text.toLowerCase();

    // 0. ตั้งค่า Meta Pixel ID & CAPI ผ่านคำสั่ง /pixel
    if (lower.indexOf("/pixel") === 0 || lower.indexOf("pixel ") === 0) {
      var parts = text.split(/\s+/);
      if (parts.length >= 2 && /^\d{10,20}$/.test(parts[1].trim())) {
        var newPixelId = parts[1].trim();
        var optToken = parts.length >= 3 ? parts[2].trim() : "";
        var saved = saveMetaPixelConfig(newPixelId, optToken);
        if (saved) {
          sendTelegramDirect(chatId,
            "✅ [บันทึก Meta Pixel & CAPI สำเร็จ!] 🎯\n" +
            "━━━━━━━━━━━━━━━━━━━━━━\n" +
            "• 🆔 Pixel ID: " + newPixelId + "\n" +
            "• 🌐 เว็บไซต์ watt29.github.io: เปิดใช้งาน Browser Pixel (PageView, ViewContent, AddToCart, InitiateCheckout, Purchase) อัตโนมัติทันที\n" +
            "• ⚡ Server CAPI: เปิดส่งสัญญาณ Purchase ย้อนกลับให้ Facebook AI ทุกครั้งที่มีออเดอร์ใหม่ค่ะ!");
        } else {
          sendTelegramDirect(chatId, "⚠️ ไม่สามารถบันทึก Pixel ID ลงฐานข้อมูลได้ในขณะนี้ค่ะ");
        }
        return;
      } else {
        sendTelegramDirect(chatId,
          "🟢 [ระบบติดตามโฆษณา Facebook ทำงานอัตโนมัติ 100% แล้วค่ะ!] 🎯\n" +
          "━━━━━━━━━━━━━━━━━━━━━━\n" +
          "• สถานะระบบ: 🟢 ทำงานอัตโนมัติ 100% (ไม่ต้องพิมพ์หรือตั้งค่ารหัสใดๆ เพิ่ม)\n" +
          "• การดักจับคลิกจากแอด (fbclid): 🟢 ทำงานอัตโนมัติทุกคลิกบนหน้าเว็บและแชทเพจ\n" +
          "• การสรุปยอดซื้อ (390.- / 550.- / 1,090.-): 🟢 บันทึกและแจ้งเตือนเข้า Telegram นี้ทันทีที่มีออเดอร์ค่ะ ✨");
        return;
      }
    }

        // -------------------------------------------------------------
    // 💰 บอททำบัญชีอัจฉริยะ (Smart Accounting & Financial Engine)
    // -------------------------------------------------------------

    // A. บันทึกรายรับ-รายจ่ายภาษาธรรมชาติ สไตล์ "ป้านวล" (Universal Natural Language Accounting & Asset Auto-Classifier)
    var expMatch = null;
    var expCategory = "";
    var expAmount = 0;
    var expDesc = "";

    // 1. ตรวจจับคำสั่งทางการ: "/expense <หมวด> <จำนวน> [รายละเอียด]"
    if ((expMatch = text.match(/^\/expense\s+(\S+)\s+(\d+(?:\.\d+)?)\s*(.*)/i))) {
      var catRaw = expMatch[1].toUpperCase();
      if (catRaw.indexOf("ASSET") !== -1 || catRaw.indexOf("ตู้") !== -1 || catRaw.indexOf("เครื่อง") !== -1 || catRaw.indexOf("อุปกรณ์") !== -1) expCategory = "ASSET";
      else if (catRaw.indexOf("AD") !== -1 || catRaw.indexOf("แอด") !== -1) expCategory = "ADS";
      else if (catRaw.indexOf("ปลา") !== -1 || catRaw.indexOf("FISH") !== -1) expCategory = "FISH";
      else if (catRaw.indexOf("กล่อง") !== -1 || catRaw.indexOf("PACK") !== -1) expCategory = "PACKAGING";
      else if (catRaw.indexOf("ส่ง") !== -1 || catRaw.indexOf("SHIP") !== -1) expCategory = "SHIPPING";
      else if (catRaw.indexOf("กิน") !== -1 || catRaw.indexOf("ข้าว") !== -1 || catRaw.indexOf("FOOD") !== -1) expCategory = "FOOD";
      else if (catRaw.indexOf("น้ำมัน") !== -1 || catRaw.indexOf("TRAVEL") !== -1) expCategory = "TRAVEL";
      else expCategory = "OTHER";
      expAmount = parseFloat(expMatch[2]);
      expDesc = expMatch[3] ? expMatch[3].trim() : "รายจ่ายบันทึกเอง";
    }
    // 2. ตรวจจับภาษาพูดธรรมชาติ สไตล์ป้านวล (เช่น "ซื้อตู้แช่ 18000", "เครื่องซีล 4500", "กาแฟ 60", "ค่าน้ำมัน 500", "ค่าแอด 300", "ซื้อปลา 5000")
    else if (!text.startsWith("/") && (expMatch = text.match(/^([^\d\n]+?)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:บาท|บ\.?)?$/i))) {
      expDesc = expMatch[1].trim();
      expAmount = parseFloat(expMatch[2]);
    }
    // 3. ตรวจจับกลับด้าน (เช่น "18000 ค่าตู้แช่", "60 กาแฟ", "500 ค่าน้ำมัน")
    else if (!text.startsWith("/") && (expMatch = text.match(/^(\d+(?:\.\d+)?)\s*(?:บาท|บ\.?)?\s*([^\d\n]+)$/i))) {
      expAmount = parseFloat(expMatch[1]);
      expDesc = expMatch[2].trim();
    }

    // หากพบข้อความเข้าข่ายการลงบัญชี
    if (expAmount > 0 && expDesc) {
      var descLower = expDesc.toLowerCase();
      // ลำดับการจำแนกหมวดหมู่อัตโนมัติ (Intelligent Category Auto-Classifier)
      if (!expCategory) {
        // 1. ตรวจจับสินทรัพย์ถาวร / เครื่องจักร / อุปกรณ์ลงทุนร้าน (CAPEX / Fixed Assets)
        if (descLower.indexOf("ตู้แช่") !== -1 || descLower.indexOf("ตู้เย็น") !== -1 || descLower.indexOf("ตู้ฟรีซ") !== -1 || descLower.indexOf("เครื่องซีล") !== -1 || descLower.indexOf("เครื่องชั่ง") !== -1 || descLower.indexOf("โต๊ะสแตนเลส") !== -1 || descLower.indexOf("โต๊ะแพ็ก") !== -1 || descLower.indexOf("อุปกรณ์ร้าน") !== -1 || descLower.indexOf("asset") !== -1 || descLower.indexOf("equipment") !== -1) {
          expCategory = "ASSET";
        }
        // 2. ตรวจจับค่าโฆษณาและการตลาด
        else if (descLower.indexOf("แอด") !== -1 || descLower.indexOf("โฆษณา") !== -1 || descLower.indexOf("ad") !== -1 || descLower.indexOf("boost") !== -1 || descLower.indexOf("fb") !== -1 || descLower.indexOf("facebook") !== -1) {
          expCategory = "ADS";
        }
        // 3. ตรวจจับวัตถุดิบเนื้อปลา
        else if (descLower.indexOf("ปลา") !== -1 || descLower.indexOf("สลิด") !== -1 || descLower.indexOf("เกลือ") !== -1 || descLower.indexOf("วัตถุดิบ") !== -1 || descLower.indexOf("fish") !== -1) {
          expCategory = "FISH";
        }
        // 4. ตรวจจับวัสดุแพ็กเกจจิ้ง
        else if (descLower.indexOf("กล่อง") !== -1 || descLower.indexOf("ถุง") !== -1 || descLower.indexOf("ฟอยล์") !== -1 || descLower.indexOf("เทป") !== -1 || descLower.indexOf("สติกเกอร์") !== -1 || descLower.indexOf("แพ็ก") !== -1 || descLower.indexOf("pack") !== -1) {
          expCategory = "PACKAGING";
        }
        // 5. ตรวจจับค่าขนส่ง
        else if (descLower.indexOf("ส่ง") !== -1 || descLower.indexOf("ขนส่ง") !== -1 || descLower.indexOf("flash") !== -1 || descLower.indexOf("scg") !== -1 || descLower.indexOf("inter") !== -1 || descLower.indexOf("kerry") !== -1 || descLower.indexOf("j&t") !== -1 || descLower.indexOf("ship") !== -1) {
          expCategory = "SHIPPING";
        }
        // 6. ตรวจจับค่าน้ำมันและการเดินทาง
        else if (descLower.indexOf("น้ำมัน") !== -1 || descLower.indexOf("ทางด่วน") !== -1 || descLower.indexOf("grab") !== -1 || descLower.indexOf("แท็กซี่") !== -1 || descLower.indexOf("bts") !== -1 || descLower.indexOf("mrt") !== -1 || descLower.indexOf("รถเมล์") !== -1 || descLower.indexOf("วิน") !== -1) {
          expCategory = "TRAVEL";
        }
        // 7. ตรวจจับค่าน้ำค่าไฟ/สาธารณูปโภค
        else if (descLower.indexOf("ไฟ") !== -1 || descLower.indexOf("น้ำประปา") !== -1 || descLower.indexOf("เน็ต") !== -1 || descLower.indexOf("โทรศัพท์") !== -1 || descLower.indexOf("ค่าเช่า") !== -1) {
          expCategory = "UTILITIES";
        }
        // 8. ตรวจจับอาหารและเครื่องดื่ม
        else if (descLower.indexOf("กาแฟ") !== -1 || descLower.indexOf("ชา") !== -1 || descLower.indexOf("ข้าว") !== -1 || descLower.indexOf("ก๋วยเตี๋ยว") !== -1 || descLower.indexOf("กิน") !== -1 || descLower.indexOf("น้ำ") !== -1 || descLower.indexOf("ขนม") !== -1 || descLower.indexOf("อาหาร") !== -1 || descLower.indexOf("เซเว่น") !== -1 || descLower.indexOf("7-11") !== -1 || descLower.indexOf("กะเพรา") !== -1 || descLower.indexOf("กระเพรา") !== -1) {
          expCategory = "FOOD";
        } else {
          expCategory = "OTHER";
        }
      }

      var nowStr = Utilities.formatDate(new Date(), "Asia/Bangkok", "dd/MM/yyyy HH:mm น.");
      var todayStr = Utilities.formatDate(new Date(), "Asia/Bangkok", "yyyy-MM-dd");

      // บันทึกลง Supabase Table accounting_expenses
      try {
        UrlFetchApp.fetch(SUPABASE_URL + "/rest/v1/accounting_expenses", {
          method: "post",
          headers: {
            "apikey": SUPABASE_KEY,
            "Authorization": "Bearer " + SUPABASE_KEY,
            "Content-Type": "application/json",
            "Prefer": "return=minimal"
          },
          payload: JSON.stringify({
            category: expCategory,
            amount: expAmount,
            description: expDesc,
            recorded_by: "admin",
            expense_date: todayStr
          }),
          muteHttpExceptions: true
        });

        // ซิงค์ลง Google Sheets อัตโนมัติทันที
        var expRefNo = "EXP-" + Utilities.formatDate(new Date(), "Asia/Bangkok", "yyyyMMdd-HHmmss");
        recordExpenseToGoogleSheet(nowStr, todayStr, expRefNo, expCategory, expDesc, expAmount, "Telegram");

        // คาแร็กเตอร์ "ป้าเข็ม" อบอุ่น เป็นกันเอง ให้กำลังใจ สไตล์ป้านวล (Make Finance a Friend)
        var warmDialogue = "";
        var catName = "";

        if (expCategory === "ASSET") {
          catName = "🏢 สินทรัพย์และอุปกรณ์ลงทุน (Fixed Asset / CAPEX)";
          var depMonth = Math.round(expAmount / 60);
          var depDay = Math.round(expAmount / 1800);
          warmDialogue =
            "ป้าเข็มลงบัญชีหมวด [🏢 สินทรัพย์และอุปกรณ์ร้าน / CAPEX] ให้เรียบร้อยแล้วจ้ะลูก! ✨\n" +
            "การลงทุน \"" + expDesc + "\" " + expAmount.toLocaleString("th-TH") + " บาทนี้ จะช่วยยกระดับร้านเรา สต็อกปลาได้สดใหม่ ล็อคความเย็นได้ถึงใจ คืนทุนไวๆ และกิจการเติบโตยั่งยืนนะจ๊ะ 💕\n\n" +
            "💡 คำแนะนำทางบัญชี: รายการนี้จัดเป็น \"สินทรัพย์ถาวรของร้าน\" ไม่ใช่ค่าใช้จ่ายวันเดียว บอทจะไม่นำไปตัดกำไรรายวันให้ติดลบค่ะ! (คิดค่าเสื่อมราคาเฉลี่ย 5 ปี ตกเพียงเดือนละ ~" + depMonth.toLocaleString("th-TH") + " บาท หรือวันละ ~" + depDay + " บาทเท่านั้นจ้ะ)";
        } else if (expCategory === "FOOD") {
          catName = "🍲 อาหารและเครื่องดื่ม";
          warmDialogue = "ป้าเข็มจดค่า \"" + expDesc + "\" " + expAmount.toLocaleString("th-TH") + " บาทให้เรียบร้อยแล้วจ้ะลูก ทานให้อร่อย มีแรงลุยงานทั้งวันนะจ๊ะ 💕";
        } else if (expCategory === "ADS") {
          catName = "📢 ค่าโฆษณา Facebook Ads";
          warmDialogue = "ป้าเข็มลงบัญชีค่าแอด " + expAmount.toLocaleString("th-TH") + " บาทให้แล้วจ้ะ ขอให้วันนี้แอดวิ่งฉิว ออเดอร์ปลาสลิดเด้งรัวๆ เงินทองไหลมาเทมานะลูก ✨";
        } else if (expCategory === "FISH") {
          catName = "🐟 ต้นทุนเนื้อปลาสุพรรณ";
          warmDialogue = "ป้าเข็มบันทึกต้นทุนปลา " + expAmount.toLocaleString("th-TH") + " บาทเข้าสต็อกให้เรียบร้อยจ้ะ คัดปลาตัวอวบๆ เนื้อแน่นๆ ทอดกรอบหอมฟุ้ง ลูกค้าติดใจสั่งซ้ำแน่นอนจ้ะ 🐟";
        } else if (expCategory === "PACKAGING") {
          catName = "📦 วัสดุแพ็กเกจจิ้ง";
          warmDialogue = "ป้าเข็มบันทึกค่าอุปกรณ์แพ็กเกจ " + expAmount.toLocaleString("th-TH") + " บาทให้แล้วจ้ะ ห่อซองฟอยล์เก็บอุณหภูมิแน่นหนา ลูกค้าประทับใจแน่นอนจ้ะ 🧊";
        } else if (expCategory === "SHIPPING") {
          catName = "🚚 ค่าจัดส่งสินค้า";
          warmDialogue = "ป้าเข็มบันทึกค่าส่ง " + expAmount.toLocaleString("th-TH") + " บาทให้แล้วจ้ะ พี่วินเตรียมส่งด่วนถึงหน้าบ้านสดใหม่ 100% เลยจ้ะ 💨";
        } else if (expCategory === "TRAVEL") {
          catName = "🚗 เดินทางและค่าน้ำมัน";
          warmDialogue = "ป้าเข็มจดค่าน้ำมัน/เดินทาง " + expAmount.toLocaleString("th-TH") + " บาทให้แล้วจ้ะ ขับรถปลอดภัย ค้าขายราบรื่นตลอดเส้นทางนะลูก 🚗💨";
        } else if (expCategory === "UTILITIES") {
          catName = "💡 ค่าน้ำค่าไฟ/สาธารณูปโภค";
          warmDialogue = "ป้าเข็มจดค่า \"" + expDesc + "\" " + expAmount.toLocaleString("th-TH") + " บาทให้เรียบร้อยแล้วนะจ๊ะ เพื่อให้ร้านเราดำเนินงานได้อย่างราบรื่นจ้ะ 💡";
        } else {
          catName = "📝 ค่าใช้จ่ายอื่นๆ";
          warmDialogue = "ป้าเข็มลงสมุดบัญชีค่า \"" + expDesc + "\" " + expAmount.toLocaleString("th-TH") + " บาทให้เรียบร้อยแล้วนะจ๊ะลูก สู้ๆ นะจ๊ะ ป้าเป็นกำลังใจให้เสมอจ้ะ 🙏💕";
        }

        // ระบบเตือนสติด้านการเงิน (Financial Guardrail): ตรวจจับหากค่าแอดสะสมแตะ 500 บาท แต่วันนี้ยังไม่มีออเดอร์
        var warningAlert = "";
        if (expCategory === "ADS") {
          try {
            var chkAdUrl = SUPABASE_URL + "/rest/v1/accounting_expenses?select=amount&category=eq.ADS&expense_date=eq." + todayStr;
            var rChk = UrlFetchApp.fetch(chkAdUrl, { headers: { "apikey": SUPABASE_KEY, "Authorization": "Bearer " + SUPABASE_KEY }, muteHttpExceptions: true });
            if (rChk.getResponseCode() === 200) {
              var allAds = JSON.parse(rChk.getContentText()) || [];
              var totalAdToday = 0;
              for (var ai = 0; ai < allAds.length; ai++) totalAdToday += Number(allAds[ai].amount || 0);
              if (totalAdToday >= 500) {
                warningAlert = "\n\n👵 [ป้าเข็มสะกิดเตือนเบาๆ จ้ะ]: ลูกจ๋า วันนี้ค่าแอดสะสมแตะ " + totalAdToday.toLocaleString("th-TH") + " บาทแล้วน้า อย่าลืมแวะไปเช็คคอมเมนต์หรือกลุ่มเป้าหมายใน Facebook Ads Manager นิดนึงนะลูก เดี๋ยวเงินจะไหล ป้าเป็นห่วงจ้ะ 💸";
              }
            }
          } catch (_) {}
        }

        var confMsg =
          "✅ [ป้าเข็มจดบัญชีให้เรียบร้อยจ้ะ] 🧾\n" +
          "━━━━━━━━━━━━━━━━━━━━━━\n" +
          "💬 " + warmDialogue + "\n\n" +
          "📂 หมวดหมู่: " + catName + "\n" +
          "💵 จำนวนเงิน: " + expAmount.toLocaleString("th-TH") + " บาท\n" +
          "⏰ เวลา: " + nowStr + warningAlert + "\n" +
          "━━━━━━━━━━━━━━━━━━━━━━\n" +
          "📑 ซิงค์ลง Google Sheets สดแล้ว: " + getAccountingSheetUrl() + "\n🌐 ดูตารางบัญชีบนเว็บ: https://watt29.github.io/pakhem-shop/admin.html#accounting\n💡 แตะปุ่ม [ 💰 บัญชีกำไรขาดทุน ] เพื่อดูงบสดได้เลยนะจ๊ะ ✨";

        sendTelegramDirect(chatId, confMsg);
        return;
      } catch (err) {
        Logger.log("Save expense error: " + err);
      }
    }

    // B. สรุปงบกำไรขาดทุน (P&L Accounting Statement)
    if (lower.indexOf("/pnl") !== -1 || lower.indexOf("/accounting") !== -1 || lower.indexOf("บัญชี") !== -1 || lower.indexOf("กำไรขาดทุน") !== -1 || lower.indexOf("งบ") !== -1) {
      var nowStr = Utilities.formatDate(new Date(), "Asia/Bangkok", "dd/MM/yyyy HH:mm น.");
      var today = Utilities.formatDate(new Date(), "Asia/Bangkok", "yyyy-MM-dd");

      // 1. ดึงออเดอร์ทั้งหมดของวันนี้
      var orders = [];
      try {
        var ordUrl = SUPABASE_URL + "/rest/v1/direct_orders?select=package_name,price,status&created_at=gte." + today + "T00:00:00";
        var rOrd = UrlFetchApp.fetch(ordUrl, {
          headers: { "apikey": SUPABASE_KEY, "Authorization": "Bearer " + SUPABASE_KEY },
          muteHttpExceptions: true
        });
        if (rOrd.getResponseCode() === 200) {
          orders = JSON.parse(rOrd.getContentText()) || [];
        }
      } catch (e) {}

      var totalRev = 0;
      var cogsFish = 0;
      var cogsPack = 0;
      var cogsShip = 0;
      var count500g = 0;
      var count1kg = 0;
      var count2kg = 0;

      for (var oi = 0; oi < orders.length; oi++) {
        var o = orders[oi];
        var price = Number(o.price || 0);
        totalRev += price;
        var pName = o.package_name || "";
        if (pName.indexOf("500") !== -1) {
          count500g++;
          cogsFish += 155;
          cogsPack += 25;
          cogsShip += 45;
        } else if (pName.indexOf("2") !== -1 || pName.indexOf("สอง") !== -1) {
          count2kg++;
          cogsFish += 620;
          cogsPack += 15;
          cogsShip += 140;
        } else {
          count1kg++;
          cogsFish += 310;
          cogsPack += 30;
          cogsShip += 55;
        }
      }

      var totalCogs = cogsFish + cogsPack + cogsShip;
      var grossProfit = totalRev - totalCogs;
      var grossMargin = totalRev > 0 ? ((grossProfit / totalRev) * 100).toFixed(1) : "0.0";

      // 2. ดึงรายจ่ายของวันนี้
      var expenses = [];
      try {
        var expUrl = SUPABASE_URL + "/rest/v1/accounting_expenses?select=category,amount,description&expense_date=eq." + today;
        var rExp = UrlFetchApp.fetch(expUrl, {
          headers: { "apikey": SUPABASE_KEY, "Authorization": "Bearer " + SUPABASE_KEY },
          muteHttpExceptions: true
        });
        if (rExp.getResponseCode() === 200) {
          expenses = JSON.parse(rExp.getContentText()) || [];
        }
      } catch (e) {}

      var adSpend = 0;
      var otherExpenses = 0;
      var assetInvestments = 0;
      var assetItems = [];
      for (var ei = 0; ei < expenses.length; ei++) {
        var ex = expenses[ei];
        var amt = Number(ex.amount || 0);
        if (ex.category === "ASSET") {
          assetInvestments += amt;
          assetItems.push((ex.description || "อุปกรณ์") + " (" + amt.toLocaleString("th-TH") + " บ.)");
        } else if (ex.category === "ADS") {
          adSpend += amt;
        } else {
          otherExpenses += amt;
        }
      }

      var totalOperatingExp = adSpend + otherExpenses;
      var netProfit = grossProfit - totalOperatingExp;
      var netMargin = totalRev > 0 ? ((netProfit / totalRev) * 100).toFixed(1) : "0.0";
      var roas = adSpend > 0 ? (totalRev / adSpend).toFixed(2) : (totalRev > 0 ? "∞" : "0.00");
      var profitBadge = netProfit >= 0 ? "🟢 +" + netProfit.toLocaleString("th-TH") + " บาท (กำไร)" : "🔴 " + netProfit.toLocaleString("th-TH") + " บาท (ขาดทุน)";

      var pnlMsg =
        "📊 [งบกำไรขาดทุน / บัญชีร้านปลาสลิดป้าเข็ม] 🐟\n" +
        "━━━━━━━━━━━━━━━━━━━━━━\n" +
        "📅 ประจำวันที่: " + Utilities.formatDate(new Date(), "Asia/Bangkok", "dd/MM/yyyy") + "\n" +
        "⏰ อัปเดตสด: " + nowStr + "\n\n" +

        "💵 1. สรุปรายรับ (Revenue):\n" +
        "  • จำนวนออเดอร์: " + orders.length + " กล่อง\n" +
        "    - ชุด 500g (390.-): " + count500g + " กล่อง\n" +
        "    - ชุด 1kg (550.-): " + count1kg + " กล่อง\n" +
        "    - ชุด 2kg (1,090.-): " + count2kg + " กล่อง\n" +
        "  • 💰 ยอดขายรวม: " + totalRev.toLocaleString("th-TH") + " บาท\n\n" +

        "📦 2. ต้นทุนสินค้าขายจริง (COGS):\n" +
        "  • ทุนเนื้อปลา: -" + cogsFish.toLocaleString("th-TH") + " บาท\n" +
        "  • ทุนแพ็กเกจ (ซีล+ซองฟอยล์): -" + cogsPack.toLocaleString("th-TH") + " บาท\n" +
        "  • ค่าจัดส่งจริง (ส่งด่วน/รถเย็น): -" + cogsShip.toLocaleString("th-TH") + " บาท\n" +
        "  • รวมต้นทุนสินค้า: -" + totalCogs.toLocaleString("th-TH") + " บาท\n" +
        "  👉 กำไรขั้นต้น (Gross Profit): +" + grossProfit.toLocaleString("th-TH") + " บ. (" + grossMargin + "%)\n\n" +

        "📢 3. ค่าโฆษณา & รายจ่ายดำเนินงาน (Expenses):\n" +
        "  • ค่าโฆษณา Facebook Ads: -" + adSpend.toLocaleString("th-TH") + " บาท\n" +
        (otherExpenses > 0 ? "  • ค่าใช้จ่ายอื่นๆ (เดินทาง/อาหาร/จิปาถะ): -" + otherExpenses.toLocaleString("th-TH") + " บาท\n" : "") +
        "  • รวมรายจ่ายดำเนินงาน: -" + totalOperatingExp.toLocaleString("th-TH") + " บาท\n\n" +

        "━━━━━━━━━━━━━━━━━━━━━━\n" +
        "💎 4. กำไรสุทธิจากการดำเนินงาน (Operating Net Profit):\n" +
        "  " + profitBadge + "\n" +
        "  • % อัตรากำไรสุทธิ: " + netMargin + "%\n" +
        "  • 🎯 ผลตอบแทนค่าโฆษณา (ROAS): " + roas + " เท่า\n" +
        "━━━━━━━━━━━━━━━━━━━━━━\n" +
        (assetInvestments > 0 ? 
        "🏢 5. สินทรัพย์และอุปกรณ์ลงทุน (Fixed Asset / CAPEX):\n" +
        "  • ยอดลงทุนสะสมวันนี้: +" + assetInvestments.toLocaleString("th-TH") + " บาท\n" +
        "  • รายการ: " + assetItems.join(", ") + "\n" +
        "  💡 ตามหลักบัญชี: ไม่หักกำไรรายวัน (คิดค่าเสื่อมราคา ~" + Math.round(assetInvestments / 1800) + " บาท/วัน)\n" +
        "━━━━━━━━━━━━━━━━━━━━━━\n" : "") +
        "💡 วิธีลงบัญชีรายจ่ายเพิ่ม:\n" +
        "• พิมพ์: ค่าแอด 300 หรือ ค่าปลา 5000\n" +
        "• บอทจะลงสมุดบัญชีและคำนวณกำไรสุทธิให้อัตโนมัติทันทีค่ะ!\n🌐 เปิดหน้าแดชบอร์ดบัญชี: https://watt29.github.io/pakhem-shop/admin.html#accounting";

      sendTelegramDirect(chatId, pnlMsg);
      return;
    }

    // 1. Start / Help
    if (lower === "/start" || lower === "/help") {
      var welcome = 
        "🐟 ยินดีต้อนรับสู่ศูนย์บัญชาการ ป้าเข็ม คัดพิเศษ (@pakhem_fish_bot) ✨\n" +
        "━━━━━━━━━━━━━━━━━━━━━━\n" +
        "ระบบเชื่อมต่อข้อมูลโฆษณา Facebook AI & ยอดขายสดอัตโนมัติตลอด 24 ชม.\n\n" +
        "👇 แตะปุ่มเมนูลัดด้านล่างได้เลยค่ะ (ไม่ต้องตั้งค่าใดๆ เพิ่ม):\n" +
        "• 📊 ดูสถิติโฆษณา & ยอดขาย (/report)\n" +
        "• 🐟 ดูราคา 3 แพ็กเกจ (/fish)\n" +
        "• 📦 ดูออเดอร์ล่าสุด (/orders)\n" +
        "• 🌐 ลิงก์ร้าน & โพสต์แอด (/link)\n\n" +
        "🛒 หน้าร้านออนไลน์: https://watt29.github.io/";
      sendTelegramDirect(chatId, welcome);
      return;
    }

    // 2. Report / Ads / Stats / ยอดขาย + AI Automated Rules Advisor
    if (lower.indexOf("/report") !== -1 || lower.indexOf("/ads") !== -1 || lower.indexOf("สถิติ") !== -1 || lower.indexOf("ยอดขาย") !== -1 || lower.indexOf("รายงาน") !== -1 || lower.indexOf("โฆษณา") !== -1) {
      var nowStr = Utilities.formatDate(new Date(), "Asia/Bangkok", "dd/MM/yyyy HH:mm น.");
      var views = 0, likes = 0, comments = 0;
      try {
        var fbUrl = "https://graph.facebook.com/v19.0/943186271935444?fields=views,likes.summary(true),comments.summary(true)&access_token=" + encodeURIComponent(FB_PAGE_ACCESS_TOKEN);
        var rFb = UrlFetchApp.fetch(fbUrl, { muteHttpExceptions: true });
        if (rFb.getResponseCode() === 200) {
          var fbData = JSON.parse(rFb.getContentText());
          views = fbData.views || 0;
          likes = (fbData.likes && fbData.likes.summary && fbData.likes.summary.total_count) || 0;
          comments = (fbData.comments && fbData.comments.summary && fbData.comments.summary.total_count) || 0;
        }
      } catch (e) {}

      var totalOrders = 0, totalRev = 0;
      try {
        var today = Utilities.formatDate(new Date(), "Asia/Bangkok", "yyyy-MM-dd");
        var supaUrl = SUPABASE_URL + "/rest/v1/direct_orders?select=price&created_at=gte." + today + "T00:00:00";
        var rSupa = UrlFetchApp.fetch(supaUrl, {
          headers: {
            "apikey": SUPABASE_KEY,
            "Authorization": "Bearer " + SUPABASE_KEY
          },
          muteHttpExceptions: true
        });
        if (rSupa.getResponseCode() === 200) {
          var ords = JSON.parse(rSupa.getContentText()) || [];
          totalOrders = ords.length;
          for (var i = 0; i < ords.length; i++) {
            totalRev += Number(ords[i].price || 0);
          }
        }
      } catch (e) {}

      // AI Automated Rules Evaluation
      var aiRuleAdvice = "";
      if (totalOrders >= 3) {
        aiRuleAdvice = "🟢 [Rule 2: Scale-Up] ยอดสั่งซื้อดีเยี่ยม! แนะนำเพิ่มงบแอด +20% เพื่อขยายฐานลูกค้า";
      } else if (views < 500) {
        aiRuleAdvice = "🔵 [Learning Phase] ระบบ AI ของ Meta กำลังเรียนรู้และสะสมการมองเห็น (รันต่อตามปกติ ห้ามแก้แอดบ่อย)";
      } else if (views >= 1500 && totalOrders === 0 && comments === 0) {
        aiRuleAdvice = "🟡 [Rule 1: Stop-Loss Warning] ยอดวิวเกิน 1,500 แต่ยังไม่มีออเดอร์ แนะนำเช็คค่า Cost per Result หากเกิน 55 บ. ให้พักแอดตัวนี้";
      } else {
        aiRuleAdvice = "🟢 [Normal Delivery] แอดกำลังวิ่งหากลุ่มคนชอบอาหารทะเล/ปลาสลิดตามปกติ";
      }

      var pxStatus = "🟢 ทำงานอัตโนมัติ 100% (ดักจับคลิกแอด & ออเดอร์อัตโนมัติ)";

      var reportMsg = 
        "📊 [รายงานสด: สถิติโฆษณา Facebook & ยอดขายปลาสลิด] 🐟\n" +
        "━━━━━━━━━━━━━━━━━━━━━━\n" +
        "⏰ อัปเดตข้อมูล: " + nowStr + "\n" +
        "🎯 สถานะโฆษณา: 🟢 ได้รับการอนุมัติแล้ว (Approved)\n\n" +
        "📈 ผลลัพธ์การมีส่วนร่วม (Ad Engagement):\n" +
        "  • 👀 ยอดรับชมวิดีโอ: " + views + " ครั้ง\n" +
        "  • ❤️ ยอดกดถูกใจ: " + likes + " คน\n" +
        "  • 💬 ความคิดเห็น: " + comments + " ข้อความ\n\n" +
        "💰 รายงานยอดขายคำสั่งซื้อวันนี้:\n" +
        "  • 📦 จำนวนออเดอร์ใหม่: " + totalOrders + " รายการ\n" +
        "  • 💵 ยอดขายรวม: " + totalRev.toLocaleString() + " บาท\n\n" +
        "🤖 วิเคราะห์ด้วยกฎ AI (Automated Rules):\n" +
        "  • " + aiRuleAdvice + "\n" +
        "  • 📡 Meta Pixel/CAPI: " + pxStatus + "\n\n" +
        "🌐 ทางลัดตรวจสอบสด:\n" +
        "  • 🔗 โพสต์บนหน้าเพจ: https://www.facebook.com/1307380735783361/videos/943186271935444\n" +
        "  • 🛒 หน้าร้านสั่งซื้อเว็บ: https://watt29.github.io/\n" +
        "━━━━━━━━━━━━━━━━━━━━━━\n" +
        "🤖 รายงานตามสั่ง (On-Demand) โดย @pakhem_fish_bot";
      sendTelegramDirect(chatId, reportMsg);
      return;
    }

    // 3. Fish / Packages / Price / ราคา
    if (lower.indexOf("/fish") !== -1 || lower.indexOf("/price") !== -1 || lower.indexOf("ราคา") !== -1 || lower.indexOf("แพ็กเกจ") !== -1 || lower.indexOf("ปลาสลิด") !== -1) {
      var fishMsg = 
        "🐟 [เมนูโปรโมชั่น & โครงสร้างกำไร ป้าเข็ม คัดพิเศษ]\n" +
        "━━━━━━━━━━━━━━━━━━━━━━\n" +
        "1️⃣ 🏷️ ชุดพอดีมื้อ 500 กรัม (ประมาณ 2–3 ตัวใหญ่)\n" +
        "   • ราคาขาย: 390.- (ส่งด่วนแพ็กซองฟอยล์เก็บความเย็น ฟรี!)\n" +
        "   • กำไรสุทธิ: ~150 – 165 บาท/กล่อง\n\n" +
        "2️⃣ ⭐ ชุดยอดฮิต 1 กิโลกรัม (ประมาณ 4–6 ตัวใหญ่)\n" +
        "   • ราคาขาย: 550.- (ส่งด่วนแพ็กซองฟอยล์เก็บความเย็น ฟรี!)\n" +
        "   • กำไรสุทธิ: ~155 บาท/กล่อง\n\n" +
        "3️⃣ 🔥 ชุดตุนสุดคุ้ม 2 กิโลกรัม (ประมาณ 8–12 ตัวใหญ่)\n" +
        "   • ราคาขาย: 1,090.- (ส่งฟรีแพ็กซองฟอยล์เก็บความเย็น / รถห้องเย็น)\n" +
        "   • กำไรสุทธิ: ~315 – 356 บาท/กล่อง\n\n" +
        "❄️ ตัวเลือกเสริมหน้าเว็บ: ลูกค้าชุด 500g / 1kg กดอัปเกรดส่งรถห้องเย็น SCG/Inter ได้ (+ลูกค้าจ่ายเพิ่ม 100.- ร้านไม่เข้าเนื้อ)\n" +
        "━━━━━━━━━━━━━━━━━━━━━━\n" +
        "🛒 หน้าร้านสั่งซื้อเว็บ: https://watt29.github.io/";
      sendTelegramDirect(chatId, fishMsg);
      return;
    }

    // 4. Orders / คำสั่งซื้อล่าสุด
    if (lower.indexOf("/orders") !== -1 || lower.indexOf("ออเดอร์") !== -1 || lower.indexOf("คำสั่งซื้อ") !== -1) {
      var supaUrl = SUPABASE_URL + "/rest/v1/direct_orders?select=order_code,customer_name,package_name,price,payment_method,status,created_at&order=created_at.desc&limit=5";
      var rSupa = UrlFetchApp.fetch(supaUrl, {
        headers: {
          "apikey": SUPABASE_KEY,
          "Authorization": "Bearer " + SUPABASE_KEY
        },
        muteHttpExceptions: true
      });
      var ords = (rSupa.getResponseCode() === 200) ? JSON.parse(rSupa.getContentText()) : [];
      if (!ords || ords.length === 0) {
        var emptyMsg = 
          "📦 [รายการคำสั่งซื้อล่าสุด] 🐟\n" +
          "━━━━━━━━━━━━━━━━━━━━━━\n" +
          "ℹ️ ขณะนี้ยังไม่มีคำสั่งซื้อใหม่ในระบบค่ะ\n" +
          "(ระบบพร้อมรับออเดอร์ตลอด 24 ชม. และจะแจ้งเตือนเข้า Telegram นี้ทันทีที่มีการสั่งซื้อค่ะ ✨)\n" +
          "━━━━━━━━━━━━━━━━━━━━━━\n" +
          "🛒 หน้าร้านสั่งซื้อ: https://watt29.github.io/";
        sendTelegramDirect(chatId, emptyMsg);
        return;
      }
      var orderLines = [];
      for (var i = 0; i < ords.length; i++) {
        var o = ords[i];
        orderLines.push("• " + (o.order_code || "-") + " | " + (o.customer_name || "ลูกค้า") + " | " + (o.package_name || "") + " | " + (o.price || 0) + " บ. [" + (o.status || "PENDING") + "]");
      }
      var listMsg = 
        "📦 [รายการคำสั่งซื้อล่าสุด 5 รายการ] 🐟\n" +
        "━━━━━━━━━━━━━━━━━━━━━━\n" +
        orderLines.join("\n") + "\n" +
        "━━━━━━━━━━━━━━━━━━━━━━\n" +
        "🛒 หน้าร้านสั่งซื้อ: https://watt29.github.io/";
      sendTelegramDirect(chatId, listMsg);
      return;
    }

    // 7. ลิงก์เปิด Google Drive & Google Sheets บัญชีร้าน
    if (lower.indexOf("/sheet") !== -1 || lower.indexOf("/drive") !== -1 || lower.indexOf("ชีท") !== -1 || lower.indexOf("ไดรฟ์") !== -1 || lower.indexOf("กูเกิลชีต") !== -1 || lower.indexOf("สเปรดชีต") !== -1 || lower.indexOf("เปิด google sheets") !== -1) {
      var ssUrl = getAccountingSheetUrl();
      var driveFolderUrl = "https://drive.google.com/drive/folders/1nY59jT4e90X2hHq-m1fSH8FCXQVLAOds";
      var sheetMsg = 
        "📁 [คลังบัญชี Google Drive & Google Sheets ป้าเข็ม] 🐟\n" +
        "━━━━━━━━━━━━━━━━━━━━━━\n" +
        "1️⃣ 📑 สมุดบัญชีรายวัน & งบกำไรขาดทุนสด (Google Sheets):\n" +
        ssUrl + "\n\n" +
        "2️⃣ 📁 โฟลเดอร์หลักเก็บเอกสารบัญชีใน Google Drive:\n" +
        driveFolderUrl + "\n" +
        "   ├─ 📂 01_สรุปงบการเงินรายเดือน\n" +
        "   ├─ 📂 02_บิลและใบเสร็จค่าใช้จ่าย\n" +
        "   ├─ 📂 03_สลิปโอนเงินลูกค้า\n" +
        "   └─ 📂 04_ทะเบียนสินทรัพย์และอุปกรณ์ร้าน";
      sendTelegramDirect(chatId, sheetMsg);
      return;
    }

    // 6. Export สมุดบัญชี CSV สำหรับ Excel & สรรพากร
    if (lower.indexOf("/export") !== -1 || lower.indexOf("ดาวน์โหลด") !== -1 || lower.indexOf("excel") !== -1 || lower.indexOf("csv") !== -1 || lower.indexOf("ส่งออก") !== -1) {
      var exportMsg = 
        "📁 [ดาวน์โหลดสมุดบัญชีรายวันทั่วไป (General Ledger)] 🧾\n" +
        "━━━━━━━━━━━━━━━━━━━━━━\n" +
        "ระบบจัดเตรียมข้อมูลสำหรับเปิดใน Microsoft Excel และยื่นภาษีเรียบร้อยแล้วค่ะ ✨\n\n" +
        "📥 ลิงก์ดาวน์โหลดไฟล์ CSV (UTF-8 with BOM):\n" +
        "👉 https://pakhem-line-webhook.regency2919.workers.dev/api/accounting/export-csv\n\n" +
        "💡 จุดเด่นของรายงานบัญชีนี้:\n" +
        "• รองรับภาษาไทย 100% เปิดใน Excel ได้ทันทีโดยไม่เป็นตัวยึกยือ\n" +
        "• รวบรวมทุกธุรกรรม: ยอดขาย (4000s), ต้นทุนสินค้าขาย COGS (5100s), ค่าแอด OPEX (5200s), และสินทรัพย์ตู้แช่ CAPEX (1510)\n" +
        "• ใช้ประกอบการยื่นแบบภาษี ภ.ง.ด. 90/94 (หักค่าใช้จ่ายตามจริง) ช่วยประหยัดภาษีได้สูงสุดค่ะ 💕";
      sendTelegramDirect(chatId, exportMsg);
      return;
    }

    // 5. Links / ลิงก์ร้านและโพสต์
    if (lower.indexOf("/link") !== -1 || lower.indexOf("ลิงก์") !== -1 || lower.indexOf("โพสต์") !== -1 || lower.indexOf("เว็บ") !== -1) {
      var linkMsg = 
        "🌐 [รวมลิงก์ระบบขาย & โฆษณา ป้าเข็ม คัดพิเศษ] ✨\n" +
        "━━━━━━━━━━━━━━━━━━━━━━\n" +
        "🛒 หน้าร้านออนไลน์ (ฝังระบบจับ fbclid & Meta Pixel แล้ว):\n" +
        "• โดเมนหลัก: https://watt29.github.io/\n" +
        "• หน้าปลาสลิด: https://watt29.github.io/pakhem-shop/fish.html\n\n" +
        "🎬 โพสต์วิดีโอโฆษณา Facebook (พร้อมปุ่มสั่งซื้อ):\n" +
        "• เพจ 1 (ป้าเข็ม ปลาสลิดแดดเดียวสุพรรณแท้): https://www.facebook.com/1307380735783361/videos/943186271935444\n" +
        "• เพจ 2 (ครัวแม่บ้าน ชี้เป้าของอร่อยของดี): https://www.facebook.com/1323469404180656/videos/2217772302119681\n\n" +
        "📱 วิดีโอสั้น Reels (9:16):\n" +
        "• เพจ 1: https://www.facebook.com/reel/1797683198138608\n" +
        "• เพจ 2: https://www.facebook.com/reel/2070659433579010\n" +
        "━━━━━━━━━━━━━━━━━━━━━━\n" +
        "🤖 ศูนย์บัญชาการ @pakhem_fish_bot";
      sendTelegramDirect(chatId, linkMsg);
      return;
    }

    sendTelegramDirect(chatId, "รับคำสั่งเรียบร้อยค่ะ แตะปุ่มเมนูด้านล่างเพื่อดูยอดขาย (/report), ดูออเดอร์ (/orders), หรือดูราคาแพ็กเกจ (/fish) ได้เลยนะคะ 😊");
  } catch (err) {
    Logger.log("handleTelegramWebhookUpdate error: " + err);
  }
}

/**
 * ตรวจสุขภาพ Telegram Webhook + ซ่อมอัตโนมัติ (แจ้งเตือนเฉพาะเมื่อพบปัญหาเท่านั้น)
 * ตั้ง Time-driven trigger รายชั่วโมงให้ฟังก์ชันนี้ได้จากหน้า Triggers ของ Apps Script
 */
var TELEGRAM_WEBHOOK_URL = "https://pakhem-line-webhook.regency2919.workers.dev";


// -------------------------------------------------------------
// 📑 ระบบบัญชี Google Sheets อัจฉริยะ (100% REST API Drive Sync — ไม่ติด Permission)
// -------------------------------------------------------------

var MASTER_ACCOUNTING_SHEET_ID = "1gpuHGAJwt-Vq9WKfwjnCySWz_DqtTzKI91Eg_RNCLIE";

function getAccountingSheetUrl() {
  var props = PropertiesService.getScriptProperties();
  var sid = props.getProperty("ACCOUNTING_SPREADSHEET_ID") || MASTER_ACCOUNTING_SHEET_ID;
  return "https://docs.google.com/spreadsheets/d/" + sid + "/edit";
}

function getDriveAccessToken_() {
  var props = PropertiesService.getScriptProperties();
  var clientId = props.getProperty("DRIVE_CLIENT_ID");
  var clientSecret = props.getProperty("DRIVE_CLIENT_SECRET");
  var refreshToken = props.getProperty("DRIVE_REFRESH_TOKEN");

  if (!clientId || !clientSecret || !refreshToken) {
    try {
      var prefRes = UrlFetchApp.fetch(SUPABASE_URL + "/rest/v1/system_preferences?key=eq.google_drive_sheet_sync&select=value", {
        method: "get",
        headers: {
          "apikey": SUPABASE_KEY,
          "Authorization": "Bearer " + SUPABASE_KEY
        },
        muteHttpExceptions: true
      });
      var prefRows = JSON.parse(prefRes.getContentText() || "[]");
      if (prefRows.length > 0 && prefRows[0].value) {
        var cfg = typeof prefRows[0].value === "string" ? JSON.parse(prefRows[0].value) : prefRows[0].value;
        clientId = cfg.client_id;
        clientSecret = cfg.client_secret;
        refreshToken = cfg.refresh_token;
        if (clientId && clientSecret && refreshToken) {
          props.setProperty("DRIVE_CLIENT_ID", clientId);
          props.setProperty("DRIVE_CLIENT_SECRET", clientSecret);
          props.setProperty("DRIVE_REFRESH_TOKEN", refreshToken);
        }
      }
    } catch (prefErr) {
      Logger.log("Load drive prefs error: " + prefErr);
    }
  }
  if (!clientId || !clientSecret || !refreshToken) return null;

  var res = UrlFetchApp.fetch("https://oauth2.googleapis.com/token", {
    method: "post",
    payload: {
      client_id: clientId,
      client_secret: clientSecret,
      refresh_token: refreshToken,
      grant_type: "refresh_token"
    },
    muteHttpExceptions: true
  });
  if (res.getResponseCode() !== 200) {
    Logger.log("Token refresh error: " + res.getContentText());
    return null;
  }
  var data = JSON.parse(res.getContentText());
  return data.access_token || null;
}

function syncSupabaseToGoogleSheet() {
  try {
    var token = getDriveAccessToken_();
    if (!token) return false;

    var props = PropertiesService.getScriptProperties();
    var sheetId = props.getProperty("ACCOUNTING_SPREADSHEET_ID") || MASTER_ACCOUNTING_SHEET_ID;

    // ดึงข้อมูลสดจาก Supabase view_general_ledger
    var supaRes = UrlFetchApp.fetch(SUPABASE_URL + "/rest/v1/view_general_ledger?order=created_at.desc&limit=500", {
      method: "get",
      headers: {
        "apikey": SUPABASE_KEY,
        "Authorization": "Bearer " + SUPABASE_KEY
      },
      muteHttpExceptions: true
    });
    var rows = JSON.parse(supaRes.getContentText() || "[]");
    if (!Array.isArray(rows)) rows = [];

    // คำนวณสรุปงบ P&L สด
    var grossRev = 0;
    var fishCogs = 0;
    var packCogs = 0;
    var shipCogs = 0;
    var adSpend = 0;
    var otherOpex = 0;
    var capex = 0;

    for (var i = 0; i < rows.length; i++) {
      var r = rows[i];
      var amt = Number(r.amount || 0);
      if (r.transaction_type === "INCOME") {
        grossRev += amt;
      } else {
        var cat = (r.category || "").toUpperCase();
        if (cat === "FISH") fishCogs += amt;
        else if (cat === "PACKAGING") packCogs += amt;
        else if (cat === "SHIPPING") shipCogs += amt;
        else if (cat === "ADS") adSpend += amt;
        else if (cat === "ASSET") capex += amt;
        else otherOpex += amt;
      }
    }
    var netProfit = grossRev - (fishCogs + packCogs + shipCogs + adSpend + otherOpex);

    var pnlSummary = [
      ["1. ยอดขายรวม (Gross Revenue)", grossRev.toFixed(2), "รายรับจากออเดอร์ทั้งหมด"],
      ["2. ต้นทุนปลาสลิด (Fish COGS)", fishCogs.toFixed(2), "รหัสบัญชี 5101"],
      ["3. ค่ากล่อง/ซองฟอยล์เก็บอุณหภูมิ (Packaging)", packCogs.toFixed(2), "รหัสบัญชี 5102"],
      ["4. ค่าขนส่งรถห้องเย็น (Shipping)", shipCogs.toFixed(2), "รหัสบัญชี 5103"],
      ["5. ค่าโฆษณา Facebook Ads (Ad Spend)", adSpend.toFixed(2), "รหัสบัญชี 5210"],
      ["6. ค่าใช้จ่ายดำเนินงานอื่นๆ (Other OPEX)", otherOpex.toFixed(2), "ค่าน้ำมัน/อาหาร/ไฟ/อื่นๆ"],
      ["7. กำไรสุทธิจากการดำเนินงาน (Net Profit)", netProfit.toFixed(2), netProfit >= 0 ? "กำไรสุทธิ" : "ขาดทุนสุทธิ"],
      ["8. เงินลงทุนสินทรัพย์ถาวร/ตู้แช่ (CAPEX)", capex.toFixed(2), "รหัสบัญชี 1510 (แยกไม่หักกำไรรายวัน)"]
    ];

    // ดึงข้อมูลออเดอร์ & ทะเบียนลูกค้าแยกกลุ่มจาก Supabase direct_orders
    var ordRes = UrlFetchApp.fetch(SUPABASE_URL + "/rest/v1/direct_orders?order=created_at.desc&limit=300", {
      method: "get",
      headers: {
        "apikey": SUPABASE_KEY,
        "Authorization": "Bearer " + SUPABASE_KEY
      },
      muteHttpExceptions: true
    });
    var ordRows = JSON.parse(ordRes.getContentText() || "[]");
    if (!Array.isArray(ordRows)) ordRows = [];

    var csvLines = [];
    csvLines.push("\ufeffรหัสธุรกรรม,เลขอ้างอิง,วันที่,ประเภท,รหัสบัญชี,หมวดหมู่,จำนวนเงิน (บาท),รายละเอียด,เวลาบันทึก,,📊 สรุปงบกำไรขาดทุน (P&L),จำนวนเงิน (บาท),หมายเหตุ,,👥 กลุ่มฐานข้อมูลลูกค้า,รหัสออเดอร์,ชื่อลูกค้า,เบอร์โทรศัพท์,ที่อยู่จัดส่ง,ยอดเงิน,วิธีชำระ,สถานะ");

    var maxLen = Math.max(rows.length, pnlSummary.length, ordRows.length);
    for (var idx = 0; idx < maxLen; idx++) {
      var leftCols = ["", "", "", "", "", "", "", "", ""];
      if (idx < rows.length) {
        var row = rows[idx];
        var cleanDesc = String(row.description || "").replace(/"/g, '""');
        leftCols = [
          '"' + (row.transaction_id || "") + '"',
          '"' + (row.reference_no || "") + '"',
          '"' + (row.entry_date || "") + '"',
          '"' + (row.transaction_type || "") + '"',
          '"' + (row.account_code || "") + '"',
          '"' + (row.category || "") + '"',
          Number(row.amount || 0).toFixed(2),
          '"' + cleanDesc + '"',
          '"' + String(row.created_at || "").slice(0, 19).replace("T", " ") + '"'
        ];
      }
      var rightCols = ["", "", ""];
      if (idx < pnlSummary.length) {
        rightCols = [
          '"' + pnlSummary[idx][0] + '"',
          pnlSummary[idx][1],
          '"' + pnlSummary[idx][2] + '"'
        ];
      }
      var crmCols = ["", "", "", "", "", "", "", ""];
      if (idx < ordRows.length) {
        var o = ordRows[idx];
        var st = String(o.status || "PENDING").toUpperCase();
        var isCod = String(o.payment_method || "").toUpperCase().indexOf("COD") !== -1;
        var hasSlip = !!(o.slip_url || o.slip_verified);
        var grpLabel = "⏳ รอโอนเงิน (ค้างหน้า QR)";
        if (st === "CANCELLED") grpLabel = "⚪ ยกเลิก / ไม่โอน";
        else if (st === "SHIPPED" || st === "DELIVERED") grpLabel = "🚚 จัดส่งแล้ว";
        else if (st === "CONFIRMED" || isCod || hasSlip) grpLabel = "🟢 พร้อมแพ็กส่ง";
        crmCols = [
          '"' + grpLabel + '"',
          '"' + String(o.order_code || "").replace(/"/g, '""') + '"',
          '"' + String(o.customer_name || "").replace(/"/g, '""') + '"',
          '"' + String(o.phone || "").replace(/"/g, '""') + '"',
          '"' + String(o.address || "").replace(/"/g, '""') + '"',
          Number(o.price || 0).toFixed(2),
          '"' + String(o.payment_method || "").replace(/"/g, '""') + '"',
          '"' + st + '"'
        ];
      }
      csvLines.push(leftCols.join(",") + ",," + rightCols.join(",") + ",," + crmCols.join(","));
    }

    var csvPayload = csvLines.join("\n");
    var patchRes = UrlFetchApp.fetch(
      "https://www.googleapis.com/upload/drive/v3/files/" + sheetId + "?uploadType=media",
      {
        method: "patch",
        contentType: "text/csv; charset=utf-8",
        headers: {
          "Authorization": "Bearer " + token
        },
        payload: Utilities.newBlob(csvPayload, "text/csv", "accounting.csv").getBytes(),
        muteHttpExceptions: true
      }
    );
    return patchRes.getResponseCode() === 200;
  } catch (err) {
    Logger.log("syncSupabaseToGoogleSheet error: " + err);
    return false;
  }
}

function recordExpenseToGoogleSheet(nowStr, todayStr, refNo, category, desc, amount, source) {
  syncSupabaseToGoogleSheet();
}

function recordOrderToGoogleSheet(nowStr, todayStr, orderNo, pkgName, customerName, totalPrice, source) {
  syncSupabaseToGoogleSheet();
}

function checkTelegramWebhookHealth() {
  try {
    var base = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN;
    var r = UrlFetchApp.fetch(base + "/getWebhookInfo", { muteHttpExceptions: true });
    if (r.getResponseCode() !== 200) return { ok: false, reason: "getWebhookInfo_http_" + r.getResponseCode() };
    var info = (JSON.parse(r.getContentText()) || {}).result || {};
    var nowSec = Math.floor(Date.now() / 1000);
    var urlWrong = info.url !== TELEGRAM_WEBHOOK_URL;
    var recentError = info.last_error_date && (nowSec - info.last_error_date) < 3 * 3600;
    var backlog = (info.pending_update_count || 0) > 3;
    if (!urlWrong && !recentError && !backlog) return { ok: true };

    var fix = UrlFetchApp.fetch(base + "/setWebhook?url=" + encodeURIComponent(TELEGRAM_WEBHOOK_URL), { muteHttpExceptions: true });
    var fixed = fix.getResponseCode() === 200;
    pushAdminAlert(
      "🛠️ [Webhook Watchdog] ตรวจพบปัญหาบอท Telegram\n" +
      "━━━━━━━━━━━━━━━━━━━\n" +
      "• URL ถูกต้อง: " + (urlWrong ? "❌" : "✅") + "\n" +
      "• Error ล่าสุด: " + (info.last_error_message || "-") + "\n" +
      "• คิวค้าง: " + (info.pending_update_count || 0) + " ข้อความ\n" +
      "• ซ่อมอัตโนมัติ (setWebhook): " + (fixed ? "✅ สำเร็จ" : "❌ ล้มเหลว")
    );
    return { ok: fixed, repaired: true };
  } catch (e) {
    Logger.log("checkTelegramWebhookHealth error: " + e);
    return { ok: false, error: String(e) };
  }
}


function matchMasterFishFaqGas(rawText, senderName) {
  var t = String(rawText || "").toLowerCase().trim();
  if (!t) return null;
  var greet = senderName ? ("สวัสดีค่ะคุณ " + senderName + " 🙏💕") : "สวัสดีค่ะคุณลูกค้า 🙏💕";
  var promoTail = "\n\n📦 โปรโมชั่นส่งตรงถึงบ้าน:\n• ชุด 500g (2–3 ตัวใหญ่) = โอน 390.- ส่งฟรี!\n• ชุดขายดี 1 กก. (4–6 ตัวใหญ่) = โอน 550.- ส่งฟรี! ⭐\n• ชุดคุ้ม 2 กก. (8–12 ตัวใหญ่) = โอน 1,090.- ส่งฟรีรถห้องเย็น!\n👉 พิมพ์ชุดที่รับพร้อม ชื่อ-ที่อยู่-เบอร์โทร ในแชทนี้ได้เลยนะคะ 😊";

  if (["ค่อยสั่ง", "เดี๋ยวค่อยสั่ง", "ไว้สั่ง", "ไว้ค่อยสั่ง", "ใกล้ปีใหม่", "ปีใหม่ก่อน", "หลังปีใหม่", "ช่วงปีใหม่", "สงกรานต์", "ใกล้สงกรานต์", "รอสิ้นเดือน", "สิ้นเดือนก่อน", "รอเงินออก", "เงินเดือนออก", "ไว้มาอุดหนุน", "ไว้อุดหนุน", "วันหลังค่อย", "รอบหน้าค่อย", "ยังไม่สั่งตอนนี้", "ทักไว้ก่อน", "แปะไว้ก่อน", "บันทึกไว้ก่อน", "ขอคิดดูก่อน", "ตัดสินใจก่อน"].some(function(k) { return t.indexOf(k) !== -1; })) {
    return greet + " ยินดีมากๆ เลยจ้าคุณพี่ ใกล้ปีใหม่หรือสะดวกเมื่อไหร่ เปิดแชทนี้ทักหาป้าเข็มได้ตลอดเลยนะคะ (แชทนี้บันทึกไว้ให้แล้ว ไม่หายจ้า)\n❄️ กระซิบนิดนึงค่ะ: ปลาสลิดป้าเข็มซีลสูญญากาศแช่แข็ง เก็บในช่องฟรีซได้นานถึง 3–6 เดือน โดยรสชาติสดใหม่เหมือนเดิมเลยค่ะ หากกลัวช่วงใกล้เทศกาลขนส่งคิวแน่น สั่งตุนติดตู้ฟรีซไว้ก่อน หรือรอสั่งใกล้ๆ วันใช้ก็ได้เลยนะคะ ป้าเข็มยินดีให้บริการเสมอจ้า 🐟✨";
  }

  if (["คืนสินค้า", "คืนของ", "เปลี่ยนสินค้า", "เปลี่ยนของ", "คืนเงิน", "เคลม", "รับประกัน", "มีประกัน", "ถ้าเสีย", "ถ้าปลาเสีย", "ของเสีย", "สินค้าเสียหาย", "สินค้ามีปัญหา", "ไม่ตรงปก", "ถุงรั่ว", "ถุงแตก"].some(function(k) { return t.indexOf(k) !== -1; })) {
    return greet + " ทางร้านมีรับประกันความสดใหม่และคุณภาพสินค้า 100% ทุกออเดอร์ค่ะ! 🛡️🐟✨\n1️⃣ กรณีเปลี่ยน/เคลมสินค้าใหม่ฟรี หรือคืนเงิน 100%: หากเปิดกล่องแล้วพบว่าถุงซีลสูญญากาศรั่วซึม ปลาเน่าเสีย มีกลิ่นผิดปกติจากการขนส่ง หรือได้รับสินค้าไม่ตรงตามที่สั่ง ป้าเข็มจัดส่งชุดใหม่ให้ฟรีทันที (หรือโอนเงินคืนเต็มจำนวน 100%) โดยไม่ต้องส่งของเสียกลับและไม่มีค่าใช้จ่ายเพิ่มเติมเลยค่ะ\n2️⃣ วิธีแจ้งเคลมง่ายๆ: เพียงถ่ายรูปสินค้าขณะเปิดกล่องส่งมาในแชทเพจนี้ (หรือ LINE @137gsref) ภายในวันที่ได้รับพัสดุ ทีมงานดูแลเคลมให้ทันทีค่ะ\n(หมายเหตุ: เนื่องจากเป็นอาหารสดแช่แข็ง หากสินค้าอยู่ในสภาพสมบูรณ์ปกติ จะไม่สามารถเปลี่ยนหรือคืนจากกรณีเปลี่ยนใจภายหลังได้นะคะ)" + promoTail;
  }
  if (["ปลาอะไร", "คือปลาอะไร", "มีปลาอะไร", "ขายปลาอะไร", "มีปลาอื่นไหม", "ปลาช่อน", "ปลานิล", "ปลาดุก", "ปลาทับทิม", "มีแค่ปลาสลิด", "ในรูปปลาอะไร", "ในคลิปปลาอะไร"].some(function(k) { return t.indexOf(k) !== -1; })) {
    return greet + " ทางร้านป้าเข็มมีจำหน่ายเฉพาะ ปลาสลิดแดดเดียวสุพรรณบุรีแท้ 100% คัดพิเศษไซส์จัมโบ้ อย่างเดียวเลยจ้า! 🐟✨\n✅ สินค้าจริงที่จัดส่งทุกแพ็กเป็น ปลาสลิดสุพรรณแท้ที่ตัดหัว ขอดเกล็ด ควักไส้ ล้างสะอาด และบั้งพร้อมทอด (ได้เนื้อปลาล้วนๆ เต็มกิโล ไม่รวมหัวปลาค่ะ)\n✅ สูตรเค็มน้อย 3% เนื้อแน่นหนาฟู มันแทรก ไร้กลิ่นสาบโคลน ซีลสูญญากาศและแช่แข็ง -18°C สดใหม่ทุกออเดอร์จ้า 😋🍚" + promoTail;
  }
  if (["บางบ่อ", "สุพรรณ", "ที่ไหน", "จังหวัดไหน", "ส่งจากไหน", "แหล่งไหน", "บ่อไหน", "รับมาจากไหน"].some(function(k) { return t.indexOf(k) !== -1; })) {
    return greet + " ขอบพระคุณที่สอบถามนะคะ 🐟✨\nของร้านป้าเข็มเป็น \"ปลาสลิดสุพรรณบุรีแท้ 100% คัดพิเศษไซส์จัมโบ้ (ไซส์จัมโบ้คัดพิเศษ 4–6 ตัวโล คัดพิเศษ)\" ค่ะ (ไม่ใช่บางบ่อจ้า)\n✅ เลี้ยงในบ่อน้ำจืดธรรมชาติ ล้างสะอาด ไร้กลิ่นสาบโคลน 100% เนื้อแน่นหนาฟู มันแทรก เค็มน้อยเพียง 3% อร่อยไม่แพ้บางบ่อเลยค่ะ 😋🍚 (แพ็กส่งตรงจาก อ.บางปะหัน จ.พระนครศรีอยุธยา ค่ะ)" + promoTail;
  }
  if (["มีไข่ไหม", "มีไข่มั้ย", "ปลาไข่", "ไข่เต็มท้อง", "มีไข่ป่าว", "ตัวเมีย", "ตัวผู้", "ไข่ปลา"].some(function(k) { return t.indexOf(k) !== -1; })) {
    return greet + " ของป้าเข็มคัดเฉพาะ \"ปลาสลิดเนื้อล้วน ไซส์จัมโบ้ (ไซส์จัมโบ้คัดพิเศษ 4–6 ตัวโล คัดพิเศษ)\" เน้นเนื้อแน่นหนาฟู มันแทรกเต็มคำ (ไม่ได้คัดแบบมีไข่ค่ะ) ทอดแล้วกรอบนอกนุ่มใน ได้เนื้อปลาล้วนๆ คุ้มน้ำหนักเต็มกิโลเลยจ้า 🐟✨" + promoTail;
  }
  if (["ขอดเกล็ด", "ควักไส้", "ตัดหัว", "มีหัวไหม", "บั้ง", "ทำสะอาด", "ต้องล้างไหม", "ชั่งตอนไหน"].some(function(k) { return t.indexOf(k) !== -1; })) {
    return greet + " ปลาสลิดป้าเข็ม ขอดเกล็ด ตัดหัว ควักไส้ ล้างสะอาด และบั้งพร้อมทอดให้เรียบร้อยแล้วค่ะ 🔪✨\n✅ น้ำหนักที่ระบุคือ น้ำหนักสุทธิหลังตัดหัวควักไส้และตากแดดแล้ว ได้เนื้อปลาล้วนๆ เต็มตาชั่งเลยจ้า!" + promoTail;
  }
  if (["ทอดมาให้ไหม", "ทอดให้ไหม", "แบบทอด", "พร้อมทาน", "ทอดสุก", "ดิบหรือสุก", "ทอดหรือยัง"].some(function(k) { return t.indexOf(k) !== -1; })) {
    return greet + " ทางร้านจำหน่ายเฉพาะแบบ \"ปลาสลิดแดดเดียวแบบดิบ (ต้องนำไปทอดก่อนทาน)\" ค่ะ 🐟✨\n✅ ซีลสูญญากาศและแช่แข็ง -18°C เพื่อให้ลูกค้าไปทอดสดๆ ร้อนๆ หน้าเตาที่บ้าน จะได้ความกรอบนอกนุ่มใน หอมมันที่สุดค่ะ 😋🍳" + promoTail;
  }
  if (["วิธีทอด", "ทอดยังไง", "หม้อทอด", "ไร้น้ำมัน", "air fryer", "airfryer", "ละลายน้ำแข็ง", "ติดกระทะ"].some(function(k) { return t.indexOf(k) !== -1; })) {
    return greet + " เคล็ดลับทอดปลาสลิดป้าเข็มให้กรอบนอกนุ่มฟูค่ะ 🍳🔥\n1️⃣ นำถุงปลาออกมาคลายเย็น และซับผิวปลาให้แห้งสนิท (ไม่ต้องล้างน้ำซ้ำ)\n2️⃣ ทอดกระทะ: ใช้ไฟกลางค่อนอ่อน ทอดด้านละ 4–5 นาทีจนเหลืองทอง\n3️⃣ หม้อทอดไร้น้ำมัน: ทาน้ำมันบางๆ ที่ผิวปลา ตั้งไฟ 180°C ด้านละ 8–10 นาที กรอบอร่อยมากค่ะ!" + promoTail;
  }
  if (["เก็บได้นานไหม", "เก็บได้กี่เดือน", "เก็บยังไง", "แช่แข็ง", "ช่องฟรีซ", "อยู่ได้นานไหม", "วันหมดอายุ"].some(function(k) { return t.indexOf(k) !== -1; })) {
    return greet + " ปลาสลิดป้าเข็มซีลสูญญากาศมิดชิด เก็บไว้ทานได้นานเลยค่ะ ❄️✨\n• ช่องฟรีซแข็ง (-18°C): เก็บได้นาน 6 เดือน\n• ช่องเย็นธรรมดา: เก็บได้ 7–14 วันค่ะ" + promoTail;
  }
  if (["ปลาช่อน", "ปลาดุก", "ปลานิล", "ปลาทับทิม", "ปลาอินทรีย์", "มีแต่ปลาสลิด", "ปลาอื่น"].some(function(k) { return t.indexOf(k) !== -1; })) {
    return greet + " ตอนนี้ทางร้านป้าเข็มคัดทำเฉพาะ \"ปลาสลิดแดดเดียว สุพรรณบุรีแท้ ไซส์จัมโบ้ 4 ตัวโล คัดพิเศษ\" อย่างเดียวเลยจ้า เนื้อหนาฟู มันแทรก เค็มน้อย 3% ไร้ก้างฝอยค่ะ 🐟✨" + promoTail;
  }
  if (["เค็มไหม", "เค็มมั้ย", "เค็มป่าว", "รสชาติ", "เค็มมาก", "อร่อยไหม", "กันบูด", "ฟอร์มาลีน", "ชูรส", "เหม็นโคลน", "สาบโคลน", "กลิ่นโคลน", "ตุไหม"].some(function(k) { return t.indexOf(k) !== -1; })) {
    return greet + " ไม่เค็มจัดและไม่เหม็นสาบโคลนแน่นอนจ้า! ป้าเข็มใช้สูตรโบราณ เนื้อปลาสลิดสุพรรณแท้ 97% หมักเกลือสมุทรธรรมชาติเพียง 3% (ไร้สารกันบูด ไร้ฟอร์มาลีน ไร้ผงชูรส 0%) เค็มน้อยกลมกล่อมกำลังดี เนื้อหนาฟู หอมมันค่ะ 🐟✨" + promoTail;
  }
  if (["กี่วันถึง", "ส่งวันไหน", "สั่งวันนี้", "ได้วันไหน", "ตัดรอบ", "ขนส่งอะไร", "ส่งด่วนไหม", "รอนานไหม"].some(function(k) { return t.indexOf(k) !== -1; })) {
    return greet + " 🚚 ป้าเข็มแพ็กและจัดส่งออกจากร้านที่ อ.บางปะหัน จ.พระนครศรีอยุธยา ภายใน 1–2 วัน หลังรับออเดอร์จ้า!\n• กทม./ปริมณฑล/ภาคกลาง: ขนส่งจัดส่งถึงหน้าบ้านภายใน 1–2 วัน\n• ต่างจังหวัดไกล: มีบริการส่งรถห้องเย็นควบคุมอุณหภูมิถึงหน้าบ้าน สดใหม่แน่นอนค่ะ" + promoTail;
  }
  if (["2 กิโลปลายทาง", "2กิโลปลายทาง", "2 กก.ปลายทาง", "2กก.ปลายทาง", "ทำไมไม่มีปลายทาง", "ไม่มีเก็บเงินปลายทาง", "ไม่มีเก็บปลายทาง", "ทำไมเก็บปลายทางไม่ได้", "เก็บเงินปลายทางไม่ได้", "รถเย็นปลายทาง", "2 โลปลายทาง", "2โลปลายทาง"].some(function(k) { return t.indexOf(k) !== -1; })) {
    return greet + " ขออนุญาตชี้แจงเหตุผลที่ ชุดสุดคุ้ม 2 กิโลกรัม (1,090.-) และพื้นที่ไกล 3–4 วัน รับเฉพาะการโอนเงินนะคะ ❄️🚚\n1️⃣ เนื่องจากชุด 2 กก. ป้าเข็มอัปเกรดจัดส่งด้วย รถควบคุมอุณหภูมิ (รถห้องเย็น Cold-Chain) เพื่อให้ปลาสดแข็งถึงหน้าบ้าน 100%\n2️⃣ บริษัทขนส่งรถห้องเย็นไม่มีระบบเก็บเงินปลายทาง (COD) ค่ะ (ซึ่งคุ้มมากเพราะป้าเข็มออกค่ารถห้องเย็นให้ฟรีทั้งหมด!)\n3️⃣ หากต้องการเก็บปลายทาง แนะนำชุด 1 กก. (งดรับ COD) หรือ 500g (งดรับ COD) สำหรับพื้นที่ส่งถึงใน 1–2 วันได้เลยจ้า!";
  }
  if (["มีรับประกัน", "รับประกัน", "เคลม", "ต่างจังหวัด", "ตจว", "เสียไหม", "เสียมั้ย", "เน่าไหม", "บูดไหม", "ละลาย", "แพ็กยังไง", "แพ็คยังไง", "เก็บความเย็น", "ซองฟอยล์", "ส่งไกล", "อากาศร้อน", "รถห้องเย็น", "รถเย็น"].some(function(k) { return t.indexOf(k) !== -1; })) {
    return greet + " ทางร้านมีรับประกันความสดใหม่ทุกออเดอร์ และส่งต่างจังหวัดไกลแค่ไหนก็ไม่เสีย มั่นใจได้ 100% เลยจ้า! 🛡️🧊🚚\n1️⃣ การแพ็กความเย็น: ซีลสูญญากาศมิดชิด + แช่เยือกแข็ง ≤ -18°C นานกว่า 12 ชม. + บรรจุซองฟอยล์เก็บอุณหภูมิ\n2️⃣ เงื่อนไขการจัดส่งตามพื้นที่:\n   • 🚚 พื้นที่ส่งถึงใน 1–2 วัน: จัดส่งสินค้าแช่แข็งพร้อมซองฟอยล์เก็บอุณหภูมิ (เลือกเก็บเงินปลายทางได้)\n   • ❄️ พื้นที่ส่งใช้เวลา 3–4 วัน: จัดส่งด้วยรถควบคุมอุณหภูมิ (รถห้องเย็น) คงความสดเหมือนออกจากตู้ฟรีซ (สงวนสิทธิ์จัดส่งหลังชำระเงินเต็มจำนวน งด COD ค่ะ)\n3️⃣ รับประกันเคลมฟรี 100%: หากเปิดกล่องแล้วสินค้ามีปัญหา ทักแชทเคลมชุดใหม่ฟรีทันทีค่ะ!" + promoTail;
  }
  if (["กี่ตัว", "โลละกี่ตัว", "ตัวละ", "ราคาตัวละ", "ขายเป็นตัว", "แยกตัว", "ตัวใหญ่ไหม", "ตัวใหญ่มั้ย", "ไซส์ไหน", "ขนาดไหน", "ราคาเท่าไหร่", "กิโลละเท่าไหร่", "โลละเท่าไหร่"].some(function(k) { return t.indexOf(k) !== -1; })) {
    return greet + " ปลาสลิดแดดเดียวสุพรรณแท้ ป้าเข็ม คัดเฉพาะไซส์ใหญ่จัมโบ้ เนื้อแน่นหนาฟู (ไซส์จัมโบ้คัดพิเศษ 4–6 ตัวโล คัดพิเศษ) จ้า 🐟✨ (จำหน่ายเป็นแพ็กซีลสูญญากาศ ไม่ได้แยกขายเป็นตัวนะคะ)" + promoTail;
  }
  if (["ค่าส่ง", "ส่งฟรี", "ค่าจัดส่ง", "รวมส่ง", "บวกเพิ่ม"].some(function(k) { return t.indexOf(k) !== -1; })) {
    return greet + " 🚚 ทางร้านจัดส่งแบบโอนเงินล่วงหน้า ส่งฟรีถึงหน้าบ้านทุกชุดค่ะ (งดรับเก็บเงินปลายทาง No COD ทุกชุด 100% เพื่อความสดใหม่ของอาหารแช่แข็งค่ะ) ❄️" + promoTail;
  }
  if (["สั่งยังไง", "สั่งซื้อยังไง", "วิธีสั่ง", "สั่งทางไหน", "กดสั่งตรงไหน", "สั่งไม่เป็น", "ทำไม่เป็น", "ต้องทำยังไง", "สั่งตรงนี้ได้ไหม", "สั่งในแชทได้ไหม", "ต้องแจ้งอะไรบ้าง"].some(function(k) { return t.indexOf(k) !== -1; })) {
    return greet + " สั่งซื้อง่ายมากๆ เลยจ้า! ไม่ต้องกดลิงก์ให้ยุ่งยาก พิมพ์สั่งในแชทนี้ได้เลยค่ะ 😊🐟✨\nเพียงพิมพ์แจ้ง 3 อย่างส่งมาในแชทนะคะ:\n1️⃣ ชุดที่ต้องการ: พิมพ์ 1 (500g 390.- ส่งฟรี) หรือ พิมพ์ 2 (1 กก. 550.- ส่งฟรี) หรือ พิมพ์ 3 (2 กก. 1,090.- ส่งฟรีรถห้องเย็น)\n2️⃣ ชำระเงิน: โอนเงินส่งฟรี (งดรับ COD ทุกชุด)\n3️⃣ ชื่อ – ที่อยู่จัดส่ง – เบอร์โทรศัพท์ 10 หลัก\n💌 เพียงเท่านี้ระบบออกรหัสออเดอร์จัดส่งให้ทันทีค่ะ!";
  }
  if (["ขอเบอร์", "เบอร์โทรร้าน", "โทรสั่ง", "โทรไปสั่ง", "โทรกลับ", "ติดต่อทางโทรศัพท์", "มีเบอร์ไหม", "มีเบอร์โทรไหม", "คุยโทรศัพท์"].some(function(k) { return t.indexOf(k) !== -1; })) {
    return greet + " ขออนุญาตเรียนแจ้งนะคะ ทางร้านป้าเข็ม รับออเดอร์ผ่านทางแชทเพจ / LINE @137gsref และหน้าเว็บเท่านั้นค่ะ (ไม่ได้รับสั่งทางโทรศัพท์และไม่ได้โทรกลับ เพื่อป้องกันการจดที่อยู่ผิดพลาดค่ะ) 🙏🐟" + promoTail;
  }
  if (["เลขบัญชี", "ขอเลขบัญชี", "บัญชีอะไร", "ธนาคารอะไร", "ชื่อบัญชี", "จีรวัฒน์", "โอนยังไง", "โอนเข้าไหน", "สแกนจ่าย", "พร้อมเพย์", "ส่งสลิป", "แจ้งโอน", "เพจจริงไหม", "มิจฉาชีพไหม"].some(function(k) { return t.indexOf(k) !== -1; })) {
    return greet + " สำหรับการโอนเงินล่วงหน้า (ส่งฟรีทุกชุด!) โอนเข้าบัญชีทางการของร้านป้าเข็มได้เลยค่ะ 🏦✨\n• ธนาคารกรุงไทย (สาขาท่าพระ)\n• เลขที่บัญชี: 038-0-25363-1\n• ชื่อบัญชี: นายจีรวัฒน์ พลอาจ (บัญชีทางการของร้านปลาสลิดป้าเข็มโดยตรง ปลอดภัย 100% ค่ะ)\n📸 โอนแล้วส่งรูปสลิป + ชื่อ-ที่อยู่-เบอร์โทร ในแชทนี้ได้เลยจ้า!";
  }
  if (["หน้าร้าน", "ไปซื้อเอง", "รับเอง", "นัดรับ", "แวะไปซื้อ", "ร้านอยู่ตรงไหน", "เข้าไปซื้อ", "ขายส่งไหม", "ราคาส่ง"].some(function(k) { return t.indexOf(k) !== -1; })) {
    return greet + " ทางร้านป้าเข็มเป็นสถานที่ผลิตและแพ็กส่งตรงอยู่ที่ ต.เสาธง อ.บางปะหัน จ.พระนครศรีอยุธยา (จัดส่งออนไลน์ถึงบ้านอย่างเดียว ไม่ได้เปิดหน้าร้าน Walk-in เพราะต้องซีลสูญญากาศและแช่แข็ง -18°C นาน 12 ชม. ตามคิวส่งค่ะ) 🏠🐟❄️" + promoTail;
  }
  if (["ทวง", "ทวงปลา", "ทวงของ", "ตามปลา", "ตามของ", "ยังไม่ได้ปลา", "ยังไม่ได้ของ", "ยังไม่ได้รับ", "ของถึงไหน", "ปลาถึงไหน", "ของยังไม่ถึง", "ปลายังไม่ถึง", "ส่งของยัง", "ส่งปลายัง", "ปลาส่งยัง", "เลขพัสดุ", "เช็คพัสดุ", "เช็คของ", "ส่งหรือยัง", "ส่งรึยัง", "เช็คสถานะ", "แก้ที่อยู่", "เปลี่ยนที่อยู่", "เปลี่ยนเบอร์", "สั่งไปแล้ว"].some(function(k) { return t.indexOf(k) !== -1; })) {
    return greet + " 🚚 ทันทีที่แพ็กส่งออก (ภายใน 1–2 วัน) ระบบบอทป้าเข็มจะส่งเลขพัสดุแจ้งเข้าทางแชทนี้ให้อัตโนมัติค่ะ! หากต้องการเช็คสถานะออเดอร์หรือแก้ไขที่อยู่/เบอร์โทร รบกวนพิมพ์ ชื่อผู้รับ หรือ เบอร์โทร 10 หลัก แจ้งไว้ในแชทได้เลยนะคะ 🙏💕";
  }
  var isQuestion = ["ไหม", "มั้ย", "ป่าว", "เปล่า", "เหรอ", "หรือคะ", "เท่าไหร่", "ยังไง", "ที่ไหน", "บ่น้อ", "บ่จ้า", "บ่คะ", "จักบาท", "?"].some(function(q) { return t.indexOf(q) !== -1; });
  if (!isQuestion && ["ตาแชบ", "ตาแซ่บ", "เป็นตาแซ่บ", "เป็นตาแชบ", "แซ่บคัก", "แชบคัก", "น่าแซ่บ", "น่าแชบ", "คือสิแซ่บ", "มักหลาย", "ลำขนาด", "น่ากิ๋น", "หรอยแรง", "หรอยจังฮู้"].some(function(k) { return t.indexOf(k) !== -1; })) {
    return greet + " ขอบพระคุณหลายๆ จ้า! ปลาสลิดสุพรรณแท้ป้าเข็ม ไซส์จัมโบ้ (4 ตัวโล คัดพิเศษ) ทอดไฟกลางให้หนังกรอบๆ เนื้อข้างในนุ่มฟู มันแทรก เค็มน้อย 3% จ้ำกับข้าวเหนียวฮ้อนๆ ตำบักหุ่ง แจ่วบอง หรือข้าวสวยร้อนๆ แซ่บคักอีหลีจ้า! 😋🐟🍚" + promoTail;
  }
  if (!isQuestion && ["อร่อย", "น่ากิน", "น่าทาน", "ติดใจ", "ของดี", "เนื้อฟู", "ตัวใหญ่", "กำลังงาม", "น้ำลายสอ"].some(function(k) { return t.indexOf(k) !== -1; })) {
    return greet + " ขอบพระคุณมากๆ เลยนะคะ ปลาสลิดแดดเดียวสุพรรณแท้ ไซส์จัมโบ้ 4 ตัวโล คัดพิเศษ เนื้อหนาฟู มันแทรก เค็มน้อย 3% ทอดทานกับข้าวสวยร้อนๆ อร่อยฟินทุกมื้อเลยค่ะ 🐟💖" + promoTail;
  }
  return null;
}
