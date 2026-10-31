// service-worker.js - Background Service Worker (Manifest V3)
// จัดการสถานะและการเริ่มต้นส่วนขยายป้าเข็ม

chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason === "install") {
    // กำหนดค่าเริ่มต้นเมื่อติดตั้งครั้งแรก
    chrome.storage.local.set({
      pkh_post_count: 0,
      pkh_active_profile: "ป้าเข็ม ปลาสลิดแดดเดียวสุพรรณแท้",
      pkh_last_updated: new Date().toISOString()
    });
    console.log("🐟 Pa Khem Group Assistant Extension installed successfully!");
  }
});

// ดักจับคำสั่งลัดแป้นพิมพ์ (Keyboard Commands)
chrome.commands.onCommand.addListener((command) => {
  if (command === "_execute_action") {
    console.log("Opening Pa Khem popup via keyboard shortcut...");
  }
});
