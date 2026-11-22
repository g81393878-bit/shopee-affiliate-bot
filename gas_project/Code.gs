
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
 "คุณลูกค้าสนใจรับเป็นชุดยอดฮิต 1 กิโลกรัม (ปิดจำหน่ายแล้ว) หรือชุดพอดีมื้อ 500g (ปิดจำหน่ายแล้ว) โอนเงินส่งฟรีถึงหน้าบ้านดีคะ? 😊\n" +
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

/**
 * =========================================================================
 * 🐟 ปลาสลิดแดดเดียว สุพรรณบุรีแท้ ป้าเข็ม คัดพิเศษ — LINE OA & Messenger Engine (@137gsref)
 * Google Apps Script Master Unified Engine (100% Direct Fish Storefront & CRM)
 * =========================================================================
 * 1. 🐟 ระบบรับออเดอร์และแนะนำแพ็กเกจปลาสลิดแดดเดียว สุพรรณบุรีแท้ (ไซส์จัมโบ้ 4 ตัวโล คัดพิเศษ)
 * 2. 🧊 มาตรฐานแพ็กเย็น 6 ขั้นตอน (Cold-Chain Packaging) & รับประกันเคลมฟรี 100%
 * 3. 💳 ข้อมูลชำระเงินโอนเงิน (กรุงไทย ปิดรับโอน) & ตรวจสอบสลิปอัตโนมัติ
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
const SUPABASE_KEY = "REDACTED_SECRET";

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

// ===== [CLOSED SALES] ร้านยุติการจำหน่ายแล้ว — ไม่มีราคา/แพ็กเกจ/ปิดรับออเดอร์ ทุกช่องทาง =====
var SALES_CLOSED = true;
function getClosedNotice() {
  return "🙏 สวัสดีค่ะ ขอขอบพระคุณที่ให้ความสนใจร้านป้าเข็มนะคะ\n\n" +
    "ขณะนี้ทางร้านได้ยุติการจำหน่ายสินค้าและปิดรับออเดอร์ทุกรายการเรียบร้อยแล้ว " +
    "จึงไม่มีสินค้าจำหน่ายและไม่มีราคาให้เสนอในขณะนี้ค่ะ\n\n" +
    "กราบขออภัยในความไม่สะดวก และขอขอบพระคุณทุกท่านที่ให้การสนับสนุนด้วยดีตลอดมาค่ะ ❤️";
}

function getColdPackReplyText() {
  return getClosedNotice();
}

function sendFishProductFlexCard(replyToken) {
  replyLine(replyToken, [{ type: "text", text: getClosedNotice() }]);
}

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
  return getClosedNotice();
}


function replyFacebook(recipientId, text, quickReplies) {
  try {
    var url = "https://graph.facebook.com/v21.0/me/messages?access_token=" + encodeURIComponent(FB_PAGE_ACCESS_TOKEN);
    var defaultReplies = [
      { content_type: "text", title: "ชุด 500g", payload: "QR_PKG_500G" },
      { content_type: "text", title: "ชุด 1 กก.", payload: "QR_PKG_1KG" },
      { content_type: "text", title: "ชุด 2 กก.", payload: "QR_PKG_2KG" }
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
  if (SALES_CLOSED) {
    var _entries = (data && data.entry) || [];
    for (var _ei = 0; _ei < _entries.length; _ei++) {
      var _msgs = _entries[_ei].messaging || [];
      for (var _mi = 0; _mi < _msgs.length; _mi++) {
        var _sid = String((_msgs[_mi].sender || {}).id || "");
        if (_sid && _sid !== "1307380735783361" && _sid !== "1323469404180656") {
          replyFacebook(_sid, getClosedNotice());
        }
      }
      var _chs = _entries[_ei].changes || [];
      for (var _ci = 0; _ci < _chs.length; _ci++) {
        var _ch = _chs[_ci];
        if (_ch.field === "feed" && _ch.value && _ch.value.item === "comment" && _ch.value.verb === "add") {
          handleCommentWebhook(_ch.value.comment_id, _ch.value.sender_id || (_ch.value.from || {}).id,
                               _ch.value.sender_name || "ลูกค้า", _ch.value.message || "");
        }
      }
    }
    return;
  }

}

function handleCommentWebhook(commentId, senderId, senderName, text) {
  if (SALES_CLOSED) {
    if (commentId) { replyCommentFacebook(commentId, getClosedNotice()); }
    return;
  }

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
 { type: "action", action: { type: "message", label: "🏦 ปิดจำหน่ายแล้วส่งฟรี", text: "เลือกโอนเงิน ชุด 500 กรัม (ปิดจำหน่ายแล้ว)" } },
        
 { type: "action", action: { type: "message", label: "❄️ ส่งรถเย็น ปิดจำหน่ายแล้ว", text: "เลือกส่งรถห้องเย็น ชุด 500 กรัม (ปิดจำหน่ายแล้ว)" } },
        { type: "action", action: { type: "clipboard", label: "📋 คัดลอกเลขบัญชี", clipboardText: "0380253631" } },
        { type: "action", action: { type: "uri", label: "🛒 กรอกผ่านเว็บง่ายๆ", uri: "https://watt29.github.io/pakhem-shop/fish.html" } }
      ]
    };
  }
  if (pkgCode === "SKU-SLID-MD-2KG") {
    return {
      items: [
 { type: "action", action: { type: "message", label: "🏦 ปิดจำหน่ายแล้ว", text: "เลือกโอนเงิน ชุด 2 กิโลกรัม (ปิดจำหน่ายแล้ว)" } },
        { type: "action", action: { type: "clipboard", label: "📋 คัดลอกเลขบัญชี", clipboardText: "0380253631" } },
        { type: "action", action: { type: "uri", label: "🛒 กรอกผ่านเว็บง่ายๆ", uri: "https://watt29.github.io/pakhem-shop/fish.html" } }
      ]
    };
  }
  // Default: 1KG
  return {
    items: [
 { type: "action", action: { type: "message", label: "🏦 ปิดจำหน่ายแล้วส่งฟรี", text: "เลือกโอนเงิน ชุด 1 กิโลกรัม (ปิดจำหน่ายแล้ว)" } },
      
 { type: "action", action: { type: "message", label: "❄️ ส่งรถเย็น ปิดจำหน่ายแล้ว", text: "เลือกส่งรถห้องเย็น ชุด 1 กิโลกรัม (ปิดจำหน่ายแล้ว)" } },
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
/**
 * คำนวณระยะทางจริง (กม.) จากจุดผลิต ต.เสาธง อ.บางปะหัน จ.พระนครศรีอยุธยา (14.4746, 100.5385)
 * และประเมินจำนวนวันจัดส่ง (1–2 วัน vs 3–4 วัน) พร้อมสิทธิ์การปิดรับออเดอร์ ตามพื้นที่
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
/**
 * การ์ดให้ลูกค้ากดเลือก "ตำบล/แขวง" ใน 1 คลิก เมื่อกรอกรหัสไปรษณีย์แล้วแต่ยังขาดชื่อตำบล
 */
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

  // ขั้นที่ 2/5 : แจ้งระยะทาง (กม.) + ใช้เวลากี่วันถึง
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
  if (SALES_CLOSED) { replyLine(replyToken, [{ type: "text", text: getClosedNotice() }]); return; }

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

 // ชั้นที่ 2: ตรวจชื่อผู้รับโอน (นายจีรวัฒน์ พลอาจ) หรือเลขบัญชีปลายทาง (ปิดรับโอน)
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
 var minPkgPrice = ปิดจำหน่ายแล้ว; // ราคาสินค้าขั้นต่ำสุดของร้าน (ชุด 500g = ปิดจำหน่ายแล้วบาท ส่งฟรี)
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
 rejectReason = "ชื่อผู้รับโอนในสลิป (" + recName + ") ไม่ตรงกับบัญชีร้าน (นายจีรวัฒน์ พลอาจ • ปิดรับโอน)";
          } else if (expAmt > 0 && amt < expAmt - 0.5) {
            rejectReason = "ยอดโอนน้อยกว่าราคาสินค้าค่ะ! โอนมา " + amt.toLocaleString("th-TH") + " บาท แต่ยอดที่ต้องชำระคือ " + expAmt.toLocaleString("th-TH") + " บาท (ยังขาดอีก " + shortfallAmount.toLocaleString("th-TH") + " บาท)";
          } else if (expAmt === 0 && amt < minPkgPrice - 0.5) {
 rejectReason = "ยอดโอนในสลิป (" + amt.toLocaleString("th-TH") + " บาท) น้อยกว่าราคาสินค้าขั้นต่ำของร้าน (ชุด 500 กรัม ปิดจำหน่ายแล้วบาท ส่งฟรี • ยังขาดอีกอย่างน้อย " + shortfallAmount.toLocaleString("th-TH") + " บาท)";
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
  if (SALES_CLOSED) { replyLine(replyToken, [{ type: "text", text: getClosedNotice() }]); return; }

}

/**
 * ข้อความต้อนรับ
 */
function sendWelcomeMessage(replyToken) {
  sendFishProductFlexCard(replyToken);
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
/**
 * การ์ด Flex Message ขั้นที่ 2: นำทางส่งที่อยู่แบบไม่ต้องพิมพ์ยาว (ปุ่มปักหมุดแผนที่ในการ์ด + ปุ่มใช้ที่อยู่เดิม + ปุ่มคัดลอกเลขบัญชี)
 */
function buildFinalPaymentConfirmCard(ctx, stepBadge) {
  var badge = stepBadge || "2/5";
  var pkgCode = ctx.packageCode || "SKU-SLID-MD-1KG";
  var is500 = pkgCode === "SKU-SLID-MD-500G";
  var is2kg = pkgCode === "SKU-SLID-MD-2KG";
  var titleText = is2kg ? "ชุดตุนสุดคุ้ม 2 กิโลกรัม" : (is500 ? "ชุดพอดีมื้อ 500 กรัม" : "ชุดยอดฮิต 1 กิโลกรัม");
  var trPrice = 0;
  var codPrice = 0;
  var coldPrice = 0;

  var rInfo = calculateShippingRouteInfo(ctx.savedAddress || "");
  var distKm = ctx.distanceKm || rInfo.distanceKm;
  var estDays = ctx.estDays || rInfo.estDays;
  var allowCod = (typeof ctx.allowCod === "boolean") ? ctx.allowCod : rInfo.allowCod;

  var payButtons = [];
  if (!allowCod && !is2kg) {
 // พื้นที่ 3–4 วัน (> 350 กม.): แนะนำส่งรถห้องเย็น / โอนเงินล่วงหน้า (งดปิดรับออเดอร์ ปิดรับออเดอร์)
    payButtons.push({
      type: "button",
      style: "primary",
      color: "#0284c7",
      height: "sm",
      margin: "md",
      action: {
        type: "message",
        label: "❄️ ปิดรับออเดอร์",
        text: "ปิดรับออเดอร์"
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
        label: "🏦 ปิดรับออเดอร์",
        text: "ปิดรับออเดอร์"
      }
    });
  } else {
 // พื้นที่ 1–2 วัน (≤ 350 กม.): มีปุ่มกดเลือกทั้ง "โอนชำระเงิน (ส่งฟรี)" และ "ปิดรับออเดอร์"
    payButtons.push({
      type: "button",
      style: "primary",
      color: "#059669",
      height: "sm",
      margin: "md",
      action: {
        type: "message",
 label: "❄️ ปิดรับออเดอร์",
        text: "ปิดรับออเดอร์"
      }
    });
 // ปิดรับออเดอร์ completely disabled
    if (coldPrice > 0) {
      payButtons.push({
        type: "button",
        style: "secondary",
        height: "sm",
        margin: "sm",
        action: {
          type: "message",
          label: "❄️ ปิดรับออเดอร์",
          text: "ปิดรับออเดอร์"
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
  replyLine(replyToken, [{ type: "text", text: getClosedNotice() }]);
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

function handleDirectWebOrder(data) {
  if (SALES_CLOSED) {
    return ContentService.createTextOutput(JSON.stringify({ ok: false, sales_closed: true, message: getClosedNotice() }))
      .setMimeType(ContentService.MimeType.JSON);
  }

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
          "• การสรุปยอดซื้อ: 🟢 บันทึกและแจ้งเตือนเข้า Telegram นี้ทันทีเมื่อมีรายการค่ะ ✨");
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
 " - ชุด 500g (ปิดจำหน่ายแล้ว): " + count500g + " กล่อง\n" +
 " - ชุด 1kg (ปิดจำหน่ายแล้ว): " + count1kg + " กล่อง\n" +
 " - ชุด 2kg (ปิดจำหน่ายแล้ว): " + count2kg + " กล่อง\n" +
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
 " • ราคาขาย: ปิดจำหน่ายแล้ว (ส่งด่วนแพ็กซองฟอยล์เก็บความเย็น ฟรี!)\n" +
        "   • กำไรสุทธิ: ~150 – 165 บาท/กล่อง\n\n" +
        "2️⃣ ⭐ ชุดยอดฮิต 1 กิโลกรัม (ประมาณ 4–6 ตัวใหญ่)\n" +
 " • ราคาขาย: ปิดจำหน่ายแล้ว (ส่งด่วนแพ็กซองฟอยล์เก็บความเย็น ฟรี!)\n" +
        "   • กำไรสุทธิ: ~155 บาท/กล่อง\n\n" +
        "3️⃣ 🔥 ชุดตุนสุดคุ้ม 2 กิโลกรัม (ประมาณ 8–12 ตัวใหญ่)\n" +
 " • ราคาขาย: ปิดจำหน่ายแล้ว (ส่งฟรีแพ็กซองฟอยล์เก็บความเย็น / รถห้องเย็น)\n" +
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

