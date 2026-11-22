// popup.js - 🐟 ป้าเข็ม: ผู้ช่วยปิดการขายในแชท & เปิดบิลรับออเดอร์ (v8.0)

const IMAGES = {
  price: "https://watt29.github.io/pakhem-shop/fish_real_basket_clean.jpg",
  fried: "https://watt29.github.io/pakhem-shop/fish_fried_plate.jpg"
};

const CLOSED_NOTICE = `🙏 สวัสดีค่ะ ขอขอบพระคุณที่ให้ความสนใจร้านป้าเข็มนะคะ

ขณะนี้ทางร้านได้ยุติการจำหน่ายสินค้าและปิดรับออเดอร์ทุกรายการเรียบร้อยแล้ว จึงไม่มีสินค้าและราคาให้เสนอในตอนนี้ค่ะ
กราบขออภัยในความไม่สะดวก และขอบพระคุณที่ให้การสนับสนุนด้วยดีตลอดมาค่ะ ❤️`;

const QUICK_REPLIES = {
  price: CLOSED_NOTICE,
  bank: CLOSED_NOTICE,
  askAddress: CLOSED_NOTICE,
  shipping: CLOSED_NOTICE
};

function showToast(msg, color = "#0c5460", bg = "#e8f4fd") {
  const toast = document.getElementById("popup-toast");
  if (toast) {
    toast.innerHTML = msg;
    toast.style.color = color;
    toast.style.background = bg;
  }
}

async function copyImageFromUrl(url, label) {
  showToast(`⏳ กำลังโหลดรูป${label}...`);
  try {
    const res = await fetch(url);
    const blob = await res.blob();
    const img = new Image();
    img.crossOrigin = "anonymous";
    const blobUrl = URL.createObjectURL(blob);

    img.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(img, 0, 0);
      URL.revokeObjectURL(blobUrl);

      canvas.toBlob(async (pngBlob) => {
        if (pngBlob && navigator.clipboard && navigator.clipboard.write) {
          try {
            await navigator.clipboard.write([new ClipboardItem({ "image/png": pngBlob })]);
            showToast(`✅ ก๊อปรูป${label}ลงคลิปบอร์ดแล้ว! (กด Ctrl+V ในช่องแชทได้เลย)`, "#155724", "#d4edda");
          } catch (e) {
            showToast("❌ เบราว์เซอร์ปฏิเสธคลิปบอร์ด", "#721c24", "#f8d7da");
          }
        }
      }, "image/png");
    };
    img.src = blobUrl;
  } catch (e) {
    showToast("❌ โหลดรูปภาพไม่สำเร็จ", "#721c24", "#f8d7da");
  }
}

async function sendTextToActiveTabChat(text, label, autoSend = false) {
  try {
    await navigator.clipboard.writeText(text);
  } catch (e) {}

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab && tab.id) {
      chrome.tabs.sendMessage(
        tab.id,
        { action: "INSERT_CHAT_TEXT", text: text, autoSend: autoSend },
        (res) => {
          if (chrome.runtime.lastError || !res || !res.ok) {
            showToast(`📋 ก๊อปปี้ <b>${label}</b> ลงคลิปบอร์ดแล้ว! (กด Ctrl+V ในช่องแชทได้เลย)`, "#004085", "#e8f4fd");
          } else {
            showToast(`✅ ส่ง <b>${label}</b> ลงช่องแชทเรียบร้อยแล้ว!`, "#155724", "#d4edda");
          }
        }
      );
      return;
    }
  } catch (e) {}

  showToast(`📋 ก๊อปปี้ <b>${label}</b> ลงคลิปบอร์ดแล้ว! (กด Ctrl+V วางได้เลย)`, "#004085", "#e8f4fd");
}

function buildConfirmationBillText(orderId, customerName, phone, address, pkgLabel, priceNum, payMethod) {
  const payText =
    payMethod === "COD"
      ? `เก็บปลายทาง ${priceNum.toLocaleString()}.-`
      : `โอนส่งฟรี ${priceNum.toLocaleString()}.- (ธ.กรุงไทย 038-0-25363-1 นายจีรวัฒน์ พลอาจ)`;

  return `✅ รับออเดอร์เรียบร้อยจ้า (${orderId}) 🙏🐟
1️⃣ สินค้า: ${pkgLabel}
2️⃣ ยอดชำระ: ${payText}
3️⃣ จัดส่ง: คุณ${customerName} (${phone}) ${address}`;
}

async function extractFromActiveTab(silent = false) {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.id) {
      if (!silent) showToast("⚠️ ไม่พบแท็บแชทที่เปิดอยู่ครับ", "#856404", "#fff3cd");
      return;
    }
    chrome.tabs.sendMessage(tab.id, { action: "EXTRACT_CHAT_ORDER" }, (res) => {
      if (chrome.runtime.lastError || !res || !res.ok || !res.data) {
        if (!silent) {
          showToast("⚠️ กรุณาเปิดหน้าแชท Facebook / Messenger ก่อนแล้วกดดึงข้อมูลอีกครั้งครับ", "#856404", "#fff3cd");
        }
        return;
      }
      const d = res.data;
      const nameInput = document.getElementById("ord-name");
      const phoneInput = document.getElementById("ord-phone");
      const addrInput = document.getElementById("ord-addr");
      const pkgSelect = document.getElementById("ord-pkg");

      if (nameInput && d.customerName) nameInput.value = d.customerName;
      if (phoneInput && d.phone) phoneInput.value = d.phone;
      if (addrInput && d.address) addrInput.value = d.address;
      if (pkgSelect && d.pkgValue) pkgSelect.value = d.pkgValue;

      if (!silent) {
        if (d.phone || d.address) {
          showToast("✅ ดึงชื่อ-เบอร์โทร-ที่อยู่จากแชทสำเร็จ! กดบันทึกออเดอร์ได้เลย", "#155724", "#d4edda");
        } else if (d.customerName) {
          showToast(`ℹ️ พบชื่อลูกค้า "${d.customerName}" (ยังไม่มีที่อยู่/เบอร์โทรในแชท)`, "#856404", "#fff3cd");
        } else {
          showToast("ℹ️ ยังไม่พบที่อยู่/เบอร์โทรในหน้านี้ กรอกข้อมูลด้านบนได้เลยครับ", "#856404", "#fff3cd");
        }
      }
    });
  } catch (e) {}
}

async function loadOrdersHistory() {
  const listEl = document.getElementById("orders-history-list");
  const countEl = document.getElementById("orders-count");
  if (!listEl) return;

  chrome.runtime.sendMessage({ action: "GET_ORDERS_HISTORY" }, (res) => {
    const history = res && Array.isArray(res.history) ? res.history : [];
    if (countEl) countEl.textContent = String(history.length);

    if (history.length === 0) {
      listEl.innerHTML = `<div style="color:#6c757d; text-align:center; padding:8px;">ยังไม่มีประวัติออเดอร์ที่บันทึก</div>`;
      return;
    }

    listEl.innerHTML = "";
    history.slice(0, 20).forEach((item) => {
      const row = document.createElement("div");
      row.style.cssText =
        "display:flex; justify-content:space-between; align-items:center; padding:5px 6px; margin-bottom:4px; background:#f8f9fa; border:1px solid #dee2e6; border-radius:5px; gap:6px;";

      const left = document.createElement("div");
      left.style.cssText = "overflow:hidden; text-overflow:ellipsis; white-space:nowrap; flex:1;";
      left.innerHTML = `<b>${item.customerName}</b> (${item.phone}) <span style="color:#1b5e20;font-weight:bold;">${item.price}.-</span>`;
      left.title = `${item.orderId}\nผู้รับ: ${item.customerName} (${item.phone})\nที่อยู่: ${item.address}\nสินค้า: ${item.pkgLabel}`;

      const copyBtn = document.createElement("button");
      copyBtn.textContent = "📋 ก๊อปใบปะหน้า";
      copyBtn.style.cssText =
        "background:#007bff; color:#fff; border:none; border-radius:4px; padding:3px 6px; font-size:10px; font-weight:bold; cursor:pointer; flex-shrink:0;";
      copyBtn.addEventListener("click", async () => {
        const shippingLabel = `ผู้รับ: คุณ${item.customerName}\nโทร: ${item.phone}\nที่อยู่: ${item.address}\nสินค้า: ${item.pkgLabel} (${item.price} บาท - ${item.payMethod})`;
        try {
          await navigator.clipboard.writeText(shippingLabel);
          showToast(`📋 ก๊อปปี้ใบปะหน้าของ คุณ${item.customerName} แล้ว!`, "#155724", "#d4edda");
        } catch (e) {}
      });

      row.appendChild(left);
      row.appendChild(copyBtn);
      listEl.appendChild(row);
    });
  });
}

document.addEventListener("DOMContentLoaded", () => {
  // ดึงข้อมูลจากแชทปัจจุบันอัตโนมัติเมื่อเปิดป๊อปอัป
  extractFromActiveTab(true);
  loadOrdersHistory();

  const btnExtract = document.getElementById("btn-extract-chat");
  if (btnExtract) {
    btnExtract.addEventListener("click", () => extractFromActiveTab(false));
  }

  const btnClear = document.getElementById("btn-clear-form");
  if (btnClear) {
    btnClear.addEventListener("click", () => {
      document.getElementById("ord-name").value = "";
      document.getElementById("ord-phone").value = "";
      document.getElementById("ord-addr").value = "";
      showToast("🧹 ล้างฟอร์มเรียบร้อยแล้ว", "#0c5460", "#e8f4fd");
    });
  }

  const btnSubmit = document.getElementById("btn-submit-order");
  if (btnSubmit) {
    btnSubmit.addEventListener("click", async () => {
      const customerName = (document.getElementById("ord-name").value || "").trim() || "ลูกค้า Facebook";
      const phone = (document.getElementById("ord-phone").value || "").replace(/[\s\-]/g, "").trim();
      const address = (document.getElementById("ord-addr").value || "").trim();
      const pkgRaw = document.getElementById("ord-pkg").value;
      const [sku, payMethod, priceStr, pkgLabel] = pkgRaw.split("|");
      const priceNum = parseFloat(priceStr) || 550;

      if (!/^0\d{8,9}$/.test(phone)) {
        showToast("⚠️ กรุณากรอกเบอร์โทรศัพท์ 10 หลักให้ถูกต้องก่อนครับ", "#721c24", "#f8d7da");
        document.getElementById("ord-phone").focus();
        return;
      }
      if (address.length < 8) {
        showToast("⚠️ กรุณากรอกที่อยู่จัดส่งให้ครบถ้วนก่อนครับ", "#721c24", "#f8d7da");
        document.getElementById("ord-addr").focus();
        return;
      }

      btnSubmit.disabled = true;
      btnSubmit.textContent = "⏳ กำลังบันทึกออเดอร์...";
      showToast("⏳ กำลังส่งออเดอร์เข้าฐานข้อมูล Supabase + Google Sheets + Telegram...", "#004085", "#e8f4fd");

      let tabUrl = "Facebook Messenger";
      try {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        if (tab && tab.url) tabUrl = tab.url;
      } catch (e) {}

      chrome.runtime.sendMessage(
        {
          action: "SAVE_INBOX_ORDER",
          payload: {
            customerName,
            phone,
            address,
            sku,
            pkgLabel,
            price: priceNum,
            payMethod,
            sourceUrl: tabUrl
          }
        },
        async (res) => {
          btnSubmit.disabled = false;
          btnSubmit.textContent = "💾 บันทึกออเดอร์ + ส่งบิลสรุปยอดเข้าแชท";

          const orderId = (res && res.orderId) || `PKF-${Date.now().toString().slice(-8)}`;
          const billMsg = buildConfirmationBillText(orderId, customerName, phone, address, pkgLabel, priceNum, payMethod);

          await sendTextToActiveTabChat(billMsg, `บิลสรุปยอด ${orderId}`, true);
          loadOrdersHistory();
          showToast(`🎉 บันทึกออเดอร์ ${orderId} + ส่งบิลสรุปยอดสำเร็จ!`, "#155724", "#d4edda");
        }
      );
    });
  }

  // ปุ่มข้อความตอบแชทด่วน
  const btnPrice = document.getElementById("btn-reply-price");
  if (btnPrice) btnPrice.addEventListener("click", () => sendTextToActiveTabChat(QUICK_REPLIES.price, "ราคา 3 แพ็กเกจ"));

  const btnBank = document.getElementById("btn-reply-bank");
  if (btnBank) btnBank.addEventListener("click", () => sendTextToActiveTabChat(QUICK_REPLIES.bank, "เลขบัญชีกรุงไทย"));

  const btnAskAddr = document.getElementById("btn-reply-ask-addr");
  if (btnAskAddr) btnAskAddr.addEventListener("click", () => sendTextToActiveTabChat(QUICK_REPLIES.askAddress, "ขอชื่อ-ที่อยู่ลูกค้า"));

  const btnShipping = document.getElementById("btn-reply-shipping");
  if (btnShipping) btnShipping.addEventListener("click", () => sendTextToActiveTabChat(QUICK_REPLIES.shipping, "มาตรฐานจัดส่ง"));

  const btnCopyImg = document.getElementById("btn-copy-img");
  if (btnCopyImg) btnCopyImg.addEventListener("click", () => copyImageFromUrl(IMAGES.price, "ป้ายราคา"));

  const btnCopyFried = document.getElementById("btn-copy-fried");
  if (btnCopyFried) btnCopyFried.addEventListener("click", () => copyImageFromUrl(IMAGES.fried, "ปลาสลิดทอด"));

  const btnInviteLikers = document.getElementById("btn-invite-likers");
  if (btnInviteLikers) {
    btnInviteLikers.addEventListener("click", async () => {
      try {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        if (!tab || !tab.id) {
          showToast("⚠️ ไม่พบแท็บ Facebook ที่เปิดอยู่ครับ", "#856404", "#fff3cd");
          return;
        }
        showToast("👍 กำลังสั่งกดเชิญคนถูกใจโพสต์บนหน้า Facebook...", "#004085", "#e8f4fd");
        chrome.tabs.sendMessage(tab.id, { action: "INVITE_POST_LIKERS" }, (res) => {
          if (chrome.runtime.lastError || !res) {
            showToast("⚠️ กรุณาเปิดหน้าเพจ Facebook แล้วคลิกตัวเลขคนกดถูกใจก่อนครับ", "#856404", "#fff3cd");
            return;
          }
          if (res.ok && res.invitedCount > 0) {
            showToast(`🎉 กดเชิญคนถูกใจโพสต์สำเร็จรวม ${res.invitedCount} คน!`, "#155724", "#d4edda");
          } else if (res.reason === "no_dialog") {
            showToast("👉 คลิกตัวเลขคนกดถูกใจ (👍) ใต้โพสต์ก่อน แล้วกดปุ่มนี้อีกครั้งครับ", "#856404", "#fff3cd");
          } else if (res.reason === "personal_profile_mode") {
            showToast("⚠️ กรุณาสลับโปรไฟล์มุมขวาบนเป็นเพจป้าเข็มก่อน จะขึ้นปุ่ม 'เชิญ' ครับ", "#721c24", "#f8d7da");
          } else {
            showToast("✅ เชิญครบทุกคนในรายการแล้วจ้า!", "#155724", "#d4edda");
          }
        });
      } catch (e) {}
    });
  }

  // ส่งออกประวัติออเดอร์เป็นไฟล์ CSV
  const btnExportCsv = document.getElementById("btn-export-orders-csv");
  if (btnExportCsv) {
    btnExportCsv.addEventListener("click", () => {
      chrome.runtime.sendMessage({ action: "GET_ORDERS_HISTORY" }, (res) => {
        const history = res && Array.isArray(res.history) ? res.history : [];
        if (history.length === 0) {
          showToast("⚠️ ยังไม่มีประวัติออเดอร์ให้ส่งออกครับ", "#856404", "#fff3cd");
          return;
        }
        let csv = '\uFEFF"รหัสออเดอร์","ชื่อผู้รับ","เบอร์โทรศัพท์","ที่อยู่จัดส่ง","แพ็กเกจสินค้า","ยอดเงิน(บาท)","วิธีชำระเงิน","วันที่บันทึก"\n';
        history.forEach((h) => {
          const esc = (v) => String(v || "").replace(/"/g, '""');
          csv += `"${esc(h.orderId)}","${esc(h.customerName)}","${esc(h.phone)}","${esc(h.address)}","${esc(h.pkgLabel)}","${esc(h.price)}","${esc(h.payMethod)}","${esc(h.createdAt)}"\n`;
        });
        const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `pakhem_inbox_orders_${new Date().toISOString().slice(0, 10)}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        showToast(`📥 ดาวน์โหลดไฟล์ CSV (${history.length} ออเดอร์) สำเร็จ!`, "#155724", "#d4edda");
      });
    });
  }
});
