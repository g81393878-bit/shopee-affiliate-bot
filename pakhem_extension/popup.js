const CAPTIONS = [
  {
    title: "สูตรทองคำ 3 บรรทัด (แนะนำที่สุด - จบใน 3 วินาที)",
    text: "🐟 ปลาสลิดสุพรรณแดดเดียวแท้ ป้าเข็ม (ไซส์จัมโบ้ เนื้อแน่นหนาฟู มันแทรก เค็มน้อย 3% ไร้สาร ไร้ชูรส)\n📦 ราคามาตรฐานส่งฟรีถึงบ้าน: 500g 390.- | 1 กก. 550.- | 2 กก. 1,090.- (ส่งฟรีรถห้องเย็น!)\n💬 สั่งซื้อ: ทักแชท Inbox หรือพิมพ์คำว่า \"สนใจ\" ในคอมเมนต์ได้เลยจ้า มีรอบส่งสดใหม่ทุกวัน!"
  },
  {
    title: "สูตร 2: เน้นชุดยอดฮิต 1 กิโลกรัม (550.- ส่งฟรี)",
    text: "🔥 ปลาสลิดสุพรรณแดดเดียวแท้ 100% ตัวใหญ่เนื้อหนาฟู ทอดกรอบนอกนุ่มใน เค็มน้อย ไม่แสบคอ\n📦 ชุดขายดี 1 กิโล (ประมาณ 5-7 ตัวจัมโบ้) เพียง 550 บาท ส่งฟรี! (เก็บเงินปลายทาง 570.-)\n💬 ทักแชท Inbox แจ้งชื่อที่อยู่เบอร์โทรได้เลยจ้า จัดส่ง 1-2 วันถึงหน้าบ้าน!"
  },
  {
    title: "สูตร 3: สายรักสุขภาพ ผู้สูงอายุ (เค็มน้อย 3% คลีนแท้)",
    text: "🌿 ปลาสลิดแดดเดียวเพื่อสุขภาพ เกลือสมุทรธรรมชาติ 3% ไร้สารกันบูด ไร้ชูรส ตัดหัวขอดเกล็ดเรียบร้อย\n👉 500g 390.- ส่งฟรี | 1 กก. 550.- ส่งฟรี | 2 กก. 1,090.- ส่งฟรีรถห้องเย็น\n💬 สนใจสั่งซื้อ ทักแชทข้อความ Inbox หรือ LINE: @137gsref ได้เลยครับผม"
  }
];

const IMAGES = {
  price: "https://watt29.github.io/pakhem-shop/fish_real_basket_clean.jpg",
  fried: "https://watt29.github.io/pakhem-shop/fish_fried_plate.jpg"
};

const QUEUE_TARGETS = [
  { name: "ตลาดขายส่ง-ปลีก อาหารแห้ง แดดเดียว", url: "https://www.facebook.com/groups/203180857683381" },
  { name: "ตลาดนัดคนสุขสำราญ (ซื้อขายอาหาร)", url: "https://www.facebook.com/groups/562879874340349" },
  { name: "ตลาดนัด อาหารอร่อย (ขายของกิน)", url: "https://www.facebook.com/groups/1585596445047346" }
];

let currentCapIndex = 0;
let isQueueRunning = false;
let queueTimerInterval = null;

function showToast(msg, color="#0c5460", bg="#e8f4fd") {
  const toast = document.getElementById("popup-toast");
  if (toast) {
    toast.textContent = msg;
    toast.style.color = color;
    toast.style.background = bg;
  }
}

function updateCaptionUI() {
  const capTitle = document.getElementById("popup-cap-title");
  const capArea = document.getElementById("popup-caption-area");
  if (capTitle && capArea) {
    capTitle.textContent = CAPTIONS[currentCapIndex].title;
    capArea.value = CAPTIONS[currentCapIndex].text;
  }
}

// 📊 โควตาปลอดภัยประจำวัน (Safe Daily Quota Guard)
async function updateDailyQuotaUI() {
  const todayStr = new Date().toLocaleDateString('th-TH');
  const data = await chrome.storage.local.get(["pkh_daily_date", "pkh_daily_count"]);
  let count = 0;

  if (data.pkh_daily_date === todayStr) {
    count = data.pkh_daily_count || 0;
  } else {
    await chrome.storage.local.set({ pkh_daily_date: todayStr, pkh_daily_count: 0 });
  }

  const badge = document.getElementById("queue-daily-quota");
  if (badge) {
    badge.textContent = `วันนี้: ${count}/10 โพสต์`;
    if (count >= 10) {
      badge.style.background = "#f8d7da";
      badge.style.color = "#721c24";
    }
  }
  return count;
}

async function incrementDailyCount() {
  const todayStr = new Date().toLocaleDateString('th-TH');
  const data = await chrome.storage.local.get(["pkh_daily_count"]);
  const newCount = (data.pkh_daily_count || 0) + 1;
  await chrome.storage.local.set({ pkh_daily_date: todayStr, pkh_daily_count: newCount });
  await updateDailyQuotaUI();
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
            await navigator.clipboard.write([
              new ClipboardItem({ "image/png": pngBlob })
            ]);
            showToast(`✅ ก๊อปรูป${label}ลงคลิปบอร์ดแล้ว! (กด Ctrl+V วางได้)`, "#155724", "#d4edda");
          } catch(e) {
            showToast("❌ เบราว์เซอร์ปฏิเสธคลิปบอร์ด", "#721c24", "#f8d7da");
          }
        }
      }, "image/png");
    };
    img.src = blobUrl;
  } catch(e) {
    showToast("❌ โหลดรูปภาพไม่สำเร็จ", "#721c24", "#f8d7da");
  }
}

// 📡 ระบบ Message Passing ตรวจสอบสถานะแท็บปัจจุบัน
async function initLiveTab() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id || !tab.url || !tab.url.includes("facebook.com")) {
      return;
    }

    chrome.tabs.sendMessage(tab.id, { action: "GET_GROUP_STATUS" }, (res) => {
      if (chrome.runtime.lastError || !res) return;

      const liveCard = document.getElementById("popup-live-card");
      const liveName = document.getElementById("live-group-name");
      const liveBadge = document.getElementById("live-badge-status");
      const btnPost = document.getElementById("btn-popup-post");

      if (liveCard && liveName && liveBadge) {
        liveCard.style.display = "block";
        liveName.textContent = res.name || "Facebook Group";
        liveBadge.textContent = res.badgeText || "ตรวจแล้ว";
        liveBadge.style.background = res.badgeBg || "#d4edda";
        liveBadge.style.color = res.badgeColor || "#155724";

        if (res.status === "not_member") {
          liveCard.style.borderLeftColor = "#d9534f";
          if (btnPost) {
            btnPost.textContent = "👉 ขอเข้ากลุ่มนี้ก่อน";
            btnPost.style.background = "#d9534f";
          }
        } else if (res.status === "pending") {
          liveCard.style.borderLeftColor = "#e67e22";
          if (btnPost) {
            btnPost.textContent = "⏳ รออนุมัติ (ยังโพสต์ไม่ได้)";
            btnPost.disabled = true;
            btnPost.style.background = "#6c757d";
          }
        } else {
          liveCard.style.borderLeftColor = "#28a745";
          if (btnPost) {
            btnPost.textContent = "🚀 สั่งโพสต์แท็บนี้ทันที";
            btnPost.disabled = false;
            btnPost.style.background = "#28a745";
          }
        }
      }
    });
  } catch(e) {}
}

// ==============================================================
// 🎯 รันเนอร์ระบบคิวโพสต์หลายกลุ่มแบบปลอดภัย (Safe Queue Runner)
// ==============================================================
function stopQueue() {
  isQueueRunning = false;
  if (queueTimerInterval) clearInterval(queueTimerInterval);
  const statusBox = document.getElementById("queue-status-box");
  const btnStart = document.getElementById("btn-start-queue");
  const btnStop = document.getElementById("btn-stop-queue");

  if (statusBox) statusBox.style.display = "none";
  if (btnStart) btnStart.style.display = "block";
  if (btnStop) btnStop.style.display = "none";
  showToast("⏹️ หยุดคิวโพสต์อัตโนมัติแล้วครับ", "#6c757d", "#e9ecef");
}

async function startQueue() {
  const currentCount = await updateDailyQuotaUI();
  if (currentCount >= 10) {
    alert("⚠️ วันนี้คุณโพสต์ครบ 10 กลุ่มแล้วครับ! เพื่อความปลอดภัยสูงสุดของบัญชี Facebook แนะนำให้พักก่อนแล้วเริ่มใหม่ในวันพรุ่งนี้ครับ");
    return;
  }

  isQueueRunning = true;
  const statusBox = document.getElementById("queue-status-box");
  const statusText = document.getElementById("queue-status-text");
  const timerText = document.getElementById("queue-timer-text");
  const btnStart = document.getElementById("btn-start-queue");
  const btnStop = document.getElementById("btn-stop-queue");
  const countSelect = document.getElementById("queue-count-select");

  const totalGroups = parseInt(countSelect ? countSelect.value : 3, 10);
  const queueToRun = QUEUE_TARGETS.slice(0, Math.min(totalGroups, QUEUE_TARGETS.length));

  if (statusBox) statusBox.style.display = "block";
  if (btnStart) btnStart.style.display = "none";
  if (btnStop) btnStop.style.display = "block";

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) {
    showToast("❌ ไม่พบแท็บเบราว์เซอร์ที่เปิดอยู่", "#721c24", "#f8d7da");
    stopQueue();
    return;
  }

  for (let i = 0; i < queueToRun.length; i++) {
    if (!isQueueRunning) break;

    const group = queueToRun[i];
    statusText.textContent = `⏳ [กลุ่ม ${i + 1}/${queueToRun.length}] กำลังเปิด: ${group.name}...`;
    timerText.textContent = "";

    // 1. นำทางแท็บไปยังกลุ่มเป้าหมาย
    await chrome.tabs.update(tab.id, { url: group.url });

    // รอหน้าเว็บโหลด 5 วินาที
    await new Promise(r => setTimeout(r, 5000));
    if (!isQueueRunning) break;

    // 2. ตรวจสอบสถานะสมาชิกกลุ่ม
    statusText.textContent = `🔍 [กลุ่ม ${i + 1}/${queueToRun.length}] กำลังตรวจสอบสถานะสมาชิก...`;
    const groupInfo = await new Promise((resolve) => {
      chrome.tabs.sendMessage(tab.id, { action: "GET_GROUP_STATUS" }, (res) => {
        resolve(chrome.runtime.lastError ? null : res);
      });
    });

    if (!groupInfo || groupInfo.status !== "member") {
      statusText.textContent = `⚠️ กลุ่มนี้ยังไม่ได้เป็นสมาชิก ข้ามไปกลุ่มถัดไป...`;
      await new Promise(r => setTimeout(r, 2000));
      continue;
    }

    // 3. สั่งโพสต์อัตโนมัติ
    statusText.textContent = `🚀 [กลุ่ม ${i + 1}/${queueToRun.length}] กำลังพิมพ์และแนบรูปโพสต์...`;
    await new Promise((resolve) => {
      chrome.tabs.sendMessage(tab.id, { action: "START_POST" }, (res) => {
        resolve(res);
      });
    });

    await incrementDailyCount();
    statusText.textContent = `✅ [กลุ่ม ${i + 1}/${queueToRun.length}] โพสต์สำเร็จแล้ว!`;

    // ถ้ายังไม่ใช่กลุ่มสุดท้าย ให้พัก Cooldown ปลอดภัย 180 วินาที (3 นาที)
    if (i < queueToRun.length - 1) {
      let cooldownSeconds = 180; // 3 นาที
      statusText.textContent = `🛡️ พัก Cooldown ปลอดภัย (กลุ่ม ${i + 1}/${queueToRun.length} เสร็จแล้ว):`;

      while (cooldownSeconds > 0 && isQueueRunning) {
        const m = Math.floor(cooldownSeconds / 60);
        const s = cooldownSeconds % 60;
        timerText.textContent = `⏳ ${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
        await new Promise(r => setTimeout(r, 1000));
        cooldownSeconds--;
      }
    }
  }

  if (isQueueRunning) {
    statusText.textContent = `🎉 เสร็จสิ้นคิวโพสต์ทั้งหมด ${queueToRun.length} กลุ่มเรียบร้อยแล้ว!`;
    timerText.textContent = "✅ ปลอดภัย 100%";
    showToast("🎉 โพสต์ครบตามคิวทั้งหมดเรียบร้อยแล้วครับ!", "#155724", "#d4edda");
    setTimeout(stopQueue, 4000);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  updateCaptionUI();
  updateDailyQuotaUI();
  initLiveTab();

  // ปุ่มเริ่ม/หยุดคิว
  const btnStartQueue = document.getElementById("btn-start-queue");
  const btnStopQueue = document.getElementById("btn-stop-queue");
  if (btnStartQueue) btnStartQueue.addEventListener("click", startQueue);
  if (btnStopQueue) btnStopQueue.addEventListener("click", stopQueue);

  // สั่งโพสต์แท็บปัจจุบันผ่าน Message Passing
  const btnPopupPost = document.getElementById("btn-popup-post");
  if (btnPopupPost) {
    btnPopupPost.addEventListener("click", async () => {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (tab?.id) {
        showToast("⏳ กำลังส่งคำสั่งโพสต์ไปยังแท็บ...", "#007bff");
        chrome.tabs.sendMessage(tab.id, { action: "START_POST" }, (res) => {
          showToast("🚀 สั่งเริ่มโพสต์บนแท็บ Facebook แล้วครับ!", "#155724", "#d4edda");
        });
      }
    });
  }

  // สั่งตอบคำถามเข้ากลุ่มผ่าน Message Passing
  const btnPopupAnswer = document.getElementById("btn-popup-answer");
  if (btnPopupAnswer) {
    btnPopupAnswer.addEventListener("click", async () => {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (tab?.id) {
        showToast("⏳ กำลังสั่งตอบคำถามเข้ากลุ่ม...", "#007bff");
        chrome.tabs.sendMessage(tab.id, { action: "ANSWER_QUESTIONS" }, (res) => {
          if (res && res.success) {
            showToast(`✅ ตอบคำถาม + ยอมรับกฎให้แล้ว (${res.count} ข้อ)!`, "#155724", "#d4edda");
          } else {
            showToast("💡 หากมีหน้าต่างคำถาม ให้กดปุ่มนี้เพื่อตอบทันทีครับ", "#856404", "#fff3cd");
          }
        });
      }
    });
  }

  // สุ่มแคปชั่น
  const randBtn = document.getElementById("popup-btn-rand");
  if (randBtn) {
    randBtn.addEventListener("click", () => {
      currentCapIndex = (currentCapIndex + 1) % CAPTIONS.length;
      updateCaptionUI();
      showToast("สุ่มแคปชั่นใหม่แล้ว!", "#155724", "#d4edda");
    });
  }

  // ค้นหากลุ่ม
  const searchInput = document.getElementById("popup-search-input");
  const searchBtn = document.getElementById("popup-btn-search");

  function triggerSearch() {
    const query = searchInput ? searchInput.value.trim() : "";
    if (query) {
      const url = `https://www.facebook.com/search/groups/?q=${encodeURIComponent(query)}`;
      chrome.tabs.create({ url });
    } else {
      showToast("⚠️ กรุณาพิมพ์คำค้นหากลุ่มก่อนครับ", "#856404", "#fff3cd");
    }
  }

  if (searchBtn) searchBtn.addEventListener("click", triggerSearch);
  if (searchInput) {
    searchInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") triggerSearch();
    });
  }

  // ลิงก์ดู 'กลุ่มที่คุณเข้าร่วมแล้วทั้งหมด'
  const joinsBtn = document.getElementById("btn-open-joins");
  if (joinsBtn) {
    joinsBtn.addEventListener("click", () => {
      chrome.tabs.create({ url: "https://www.facebook.com/groups/joins/" });
    });
  }

  // ปุ่มเปิดลิงก์กลุ่มอื่นๆ
  document.querySelectorAll(".btn-item[data-url]").forEach((el) => {
    el.addEventListener("click", () => {
      const url = el.getAttribute("data-url");
      if (url) chrome.tabs.create({ url });
    });
  });

  // ก๊อปปี้รูปป้ายราคา
  const copyImgBtn = document.getElementById("btn-copy-img");
  if (copyImgBtn) {
    copyImgBtn.addEventListener("click", () => {
      copyImageFromUrl(IMAGES.price, "ป้ายราคา");
    });
  }

  // ก๊อปปี้รูปปลาทอด
  const copyFriedBtn = document.getElementById("btn-copy-fried");
  if (copyFriedBtn) {
    copyFriedBtn.addEventListener("click", () => {
      copyImageFromUrl(IMAGES.fried, "ปลาทอด");
    });
  }

  // ก๊อปปี้ข้อความแคปชั่น
  const copyTextBtn = document.getElementById("btn-copy-text");
  if (copyTextBtn) {
    copyTextBtn.addEventListener("click", async () => {
      const capArea = document.getElementById("popup-caption-area");
      if (capArea && capArea.value) {
        await navigator.clipboard.writeText(capArea.value.trim());
        showToast("📋 ก๊อปปี้ข้อความราคา 3 บรรทัดแล้ว!", "#155724", "#d4edda");
      }
    });
  }

    // ==============================================================
    // 📝 ระบบจดบันทึกโน้ตลูกค้าเฉพาะหน้าเว็บ (URL-based CRM + CSV Export)
    // ==============================================================
    const crmNoteInput = document.getElementById("crm-note-input");
    const crmUrlPreview = document.getElementById("crm-url-preview");
    const btnSaveCrmNote = document.getElementById("btn-save-crm-note");
    const btnClearCrmNote = document.getElementById("btn-clear-crm-note");
    const btnExportNotesCsv = document.getElementById("btn-export-notes-csv");
    const crmTagBtns = document.querySelectorAll(".crm-tag-btn");

    let currentCrmKey = "";
    let currentTabUrl = "";
    let currentTabTitle = "";

    async function initCrmNotes() {
        try {
            const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
            if (!tab || !tab.url) {
                if (crmUrlPreview) crmUrlPreview.textContent = "ไม่พบแท็บเปิดอยู่";
                return;
            }
            currentTabUrl = tab.url;
            currentTabTitle = tab.title || "ลูกค้า";

            try {
                const u = new URL(tab.url);
                currentCrmKey = u.origin + u.pathname;
            } catch(e) {
                currentCrmKey = tab.url;
            }

            if (crmUrlPreview) {
                crmUrlPreview.textContent = (currentTabTitle.length > 25 ? currentTabTitle.substring(0, 25) + "..." : currentTabTitle);
                crmUrlPreview.title = currentCrmKey;
            }

            // โหลดโน้ตที่มีอยู่แล้วใน chrome.storage.local
            const store = await chrome.storage.local.get(["pakhem_customer_notes"]);
            const allNotes = store.pakhem_customer_notes || {};
            const existing = allNotes[currentCrmKey];
            if (existing && crmNoteInput) {
                crmNoteInput.value = existing.note || "";
            }
        } catch(e) {
            console.warn("CRM init error:", e);
        }
    }

    if (btnSaveCrmNote) {
        btnSaveCrmNote.addEventListener("click", async () => {
            const noteText = crmNoteInput ? crmNoteInput.value.trim() : "";
            if (!currentCrmKey) {
                showToast("⚠️ ไม่พบ URL หน้าเว็บที่จะบันทึกโน้ตครับ", "#d9534f");
                return;
            }
            const store = await chrome.storage.local.get(["pakhem_customer_notes"]);
            const allNotes = store.pakhem_customer_notes || {};

            allNotes[currentCrmKey] = {
                key: currentCrmKey,
                url: currentTabUrl,
                title: currentTabTitle,
                note: noteText,
                updated_at: new Date().toLocaleString("th-TH")
            };

            await chrome.storage.local.set({ pakhem_customer_notes: allNotes });
            showToast("💾 บันทึกโน้ตลูกค้าลงเครื่องเรียบร้อยแล้ว!", "#28a745");
        });
    }

    if (btnClearCrmNote) {
        btnClearCrmNote.addEventListener("click", async () => {
            if (!currentCrmKey) return;
            const store = await chrome.storage.local.get(["pakhem_customer_notes"]);
            const allNotes = store.pakhem_customer_notes || {};
            if (allNotes[currentCrmKey]) {
                delete allNotes[currentCrmKey];
                await chrome.storage.local.set({ pakhem_customer_notes: allNotes });
            }
            if (crmNoteInput) crmNoteInput.value = "";
            showToast("🗑️ ลบโน้ตของหน้านี้แล้วครับ", "#6c757d");
        });
    }

    if (crmTagBtns) {
        crmTagBtns.forEach(btn => {
            btn.addEventListener("click", () => {
                const tag = btn.getAttribute("data-tag") || "";
                if (crmNoteInput && tag) {
                    const cur = crmNoteInput.value.trim();
                    crmNoteInput.value = cur ? cur + " | " + tag : tag;
                }
            });
        });
    }

    if (btnExportNotesCsv) {
        btnExportNotesCsv.addEventListener("click", async () => {
            const store = await chrome.storage.local.get(["pakhem_customer_notes"]);
            const allNotes = store.pakhem_customer_notes || {};
            const items = Object.values(allNotes);

            if (items.length === 0) {
                showToast("⚠️ ยังไม่มีรายการโน้ตลูกค้าที่บันทึกไว้ครับ", "#e67e22");
                return;
            }

            let csv = "\ufeffวันเวลาที่บันทึก,ชื่อลูกค้า/หัวข้อ,URL หน้าแชท/เพจ,โน้ตลูกค้า (CRM)\r\n";
            for (const it of items) {
                const time = `"${(it.updated_at || "").replace(/"/g, '""')}"`;
                const title = `"${(it.title || "").replace(/"/g, '""')}"`;
                const url = `"${(it.url || it.key || "").replace(/"/g, '""')}"`;
                const note = `"${(it.note || "").replace(/"/g, '""')}"`;
                csv += `${time},${title},${url},${note}\r\n`;
            }

            const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
            const downloadUrl = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = downloadUrl;
            a.download = `pakhem_customer_notes_${new Date().toISOString().slice(0, 10)}.csv`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(downloadUrl);
            showToast(`🎉 ส่งออก CSV โน้ตลูกค้า ${items.length} รายการสำเร็จ!`, "#28a745");
        });
    }

    initCrmNotes();

});
