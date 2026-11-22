// service-worker.js - Background Service Worker (Manifest V3)
// 🐟 ป้าเข็ม: ผู้ช่วยปิดการขายในแชท Messenger / Inbox (บันทึกออเดอร์เข้า Supabase + Google Sheets + Telegram)

const SUPABASE_URL = "https://usqhvujqmnxqrdoovvnp.supabase.co/rest/v1/direct_orders";
const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVzcWh2dWpxbW54cXJkb292dm5wIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTQyOTc4NjAsImV4cCI6MjA2OTg3Mzg2MH0.3kCGGAe1OoSJ_SCN_NDSdnKep1hXIMgMxR1lBd_i2eI";
const GAS_WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbxHAfBm0V67wkiXb1dlAFNbG3NQudcN35zuQ3xjFo0FRHY2ja8TB3-Xj0l_xOWxeF404Q/exec";

chrome.runtime.onInstalled.addListener(() => {
  // ล้างสถานะคิวแชร์กลุ่มแบบเก่าออกทั้งหมดเพื่อไม่ให้ค้างหรือเปลี่ยนหน้าเอง
  chrome.storage.local.remove([
    "pkh_persistent_queue",
    "pkh_auto_share_video_on_load",
    "pkh_daily_count"
  ]);
  chrome.storage.local.set({
    pkh_active_profile: "ป้าเข็ม ปลาสลิดแดดเดียวสุพรรณแท้",
    pkh_version: "8.0",
    pkh_last_updated: new Date().toISOString()
  });
});

async function handleSaveInboxOrder(payload) {
  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  const orderId =
    payload.orderId ||
    `PKF-${pad(now.getMonth() + 1)}${pad(now.getDate())}${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;

  const customerName = (payload.customerName || "ลูกค้า Facebook").trim();
  const phone = (payload.phone || "").replace(/[\s\-]/g, "").trim();
  const address = (payload.address || "").trim();
  const sku = payload.sku || "SKU-SLID-MD-1KG";
  const pkgLabel = payload.pkgLabel || "ปลาสลิดแดดเดียว ชุดยอดฮิต 1 กิโลกรัม (โอนส่งฟรี)";
  const priceNum = Number(payload.price) || 550;
  const payMethod = payload.payMethod || "TRANSFER";
  const sourceUrl = payload.sourceUrl || "Facebook Messenger";

  const orderRow = {
    order_code: orderId,
    product_name: "ปลาสลิดแดดเดียวสุพรรณแท้ ป้าเข็ม คัดพิเศษ",
    package_code: sku,
    package_name: pkgLabel,
    price: priceNum,
    customer_name: customerName,
    phone: phone,
    address: address,
    payment_method: payMethod,
    status: "PENDING",
    note: `[InboxHelper v8.0] ${sourceUrl}`,
    created_at: now.toISOString()
  };

  let supaOk = false;
  let gasOk = false;

  // 1. บันทึกลง Supabase (ตาราง direct_orders)
  try {
    const rSupa = await fetch(SUPABASE_URL, {
      method: "POST",
      headers: {
        apikey: SUPABASE_ANON_KEY,
        Authorization: "Bearer " + SUPABASE_ANON_KEY,
        "Content-Type": "application/json",
        Prefer: "return=minimal"
      },
      body: JSON.stringify(orderRow)
    });
    if (rSupa.ok || rSupa.status === 201 || rSupa.status === 409) {
      supaOk = true;
    }
  } catch (err) {
    console.warn("Supabase order save error:", err);
  }

  // 2. ส่งเข้า Google Apps Script (บันทึกลง Google Sheets + แจ้งเตือน Telegram ทันที)
  try {
    const rGas = await fetch(GAS_WEBHOOK_URL, {
      method: "POST",
      headers: { "Content-Type": "text/plain;charset=utf-8" },
      body: JSON.stringify({
        action: "order_fish",
        order_id: orderId,
        skip_db: supaOk,
        name: customerName,
        phone: phone,
        address: address,
        package: sku,
        package_name: pkgLabel,
        price: priceNum,
        payment_method: payMethod,
        note: `[InboxHelper v8.0] ${sourceUrl}`
      })
    });
    if (rGas.ok || rGas.type === "opaque" || rGas.status === 200) {
      gasOk = true;
    }
  } catch (err) {
    console.warn("GAS order save error:", err);
  }

  // 3. บันทึกประวัติออเดอร์ลง chrome.storage.local (เก็บสูงสุด 100 รายการล่าสุด)
  try {
    const store = await chrome.storage.local.get(["pkh_orders_history"]);
    const history = Array.isArray(store.pkh_orders_history) ? store.pkh_orders_history : [];
    const newEntry = {
      orderId,
      customerName,
      phone,
      address,
      sku,
      pkgLabel,
      price: priceNum,
      payMethod,
      sourceUrl,
      createdAt: now.toISOString(),
      supaOk,
      gasOk
    };
    const updated = [newEntry, ...history.filter((h) => h.orderId !== orderId)].slice(0, 100);
    await chrome.storage.local.set({ pkh_orders_history: updated });
  } catch (err) {
    console.warn("Storage history save error:", err);
  }

  return {
    ok: supaOk || gasOk,
    orderId,
    supaOk,
    gasOk
  };
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || !msg.action) return false;

  if (msg.action === "SAVE_INBOX_ORDER") {
    handleSaveInboxOrder(msg.payload || {})
      .then((res) => sendResponse(res))
      .catch((err) => sendResponse({ ok: false, error: String(err) }));
    return true; // keep async channel open
  }

  if (msg.action === "GET_ORDERS_HISTORY") {
    chrome.storage.local.get(["pkh_orders_history"], (data) => {
      sendResponse({
        ok: true,
        history: Array.isArray(data.pkh_orders_history) ? data.pkh_orders_history : []
      });
    });
    return true;
  }

  return false;
});
