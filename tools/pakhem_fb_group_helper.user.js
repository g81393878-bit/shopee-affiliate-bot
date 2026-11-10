// ==UserScript==
// @name         🐟 ป้าเข็ม — ผู้ช่วยปิดการขายในแชท & เปิดบิลรับออเดอร์ (v8.7)
// @namespace    https://watt29.github.io/pakhem-shop/
// @version      8.7
// @description  ผู้ช่วยปิดการขายในแชท Messenger / Inbox + กดเชิญคนถูกใจโพสต์ให้ติดตามเพจต่อเนื่องครบทุกคน + ดึงชื่อ-ที่อยู่-เบอร์โทร + บันทึกออเดอร์เข้าฐานข้อมูล/Telegram
// @author       ป้าเข็ม ปลาสลิดแดดเดียวสุพรรณแท้
// @match        https://www.facebook.com/*
// @match        https://web.facebook.com/*
// @match        https://business.facebook.com/*
// @match        https://www.messenger.com/*
// @grant        none
// @run-at       document-idle
// ==/UserScript==
(function () {
    "use strict";
    if (window.__PA_KHEM_INBOX_V87__) return;
    window.__PA_KHEM_INBOX_V87__ = true;
    window.__PA_KHEM_LOADED__ = true;

    // 🧹 ล้างสถานะคิวแชร์กลุ่มแบบเก่าออกทั้งหมดทันที เพื่อไม่ให้เด้งเปลี่ยนหน้าเองหรือค้างตัวเลขถอยหลัง
    try {
        localStorage.removeItem("pkh_persistent_queue");
        localStorage.removeItem("pkh_auto_share_video_on_load");
        sessionStorage.removeItem("pkh_shared_live_groups");
    } catch (e) {}

    const SUPABASE_URL = "https://usqhvujqmnxqrdoovvnp.supabase.co/rest/v1/direct_orders";
    const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVzcWh2dWpxbW54cXJkb292dm5wIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTQyOTc4NjAsImV4cCI6MjA2OTg3Mzg2MH0.3kCGGAe1OoSJ_SCN_NDSdnKep1hXIMgMxR1lBd_i2eI";
    const GAS_WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbxHAfBm0V67wkiXb1dlAFNbG3NQudcN35zuQ3xjFo0FRHY2ja8TB3-Xj0l_xOWxeF404Q/exec";

    const IMAGES = {
        price: "https://watt29.github.io/pakhem-shop/fish_real_basket_clean.jpg",
        fried: "https://watt29.github.io/pakhem-shop/fish_fried_plate.jpg"
    };

    const MESSENGER_REPLIES = {
        price: `🐟 ปลาสลิดสุพรรณแท้ ป้าเข็ม (ไซส์จัมโบ้ เนื้อล้วน เค็มน้อย 3%)
1️⃣ 500g (2-3 ตัวใหญ่): โอน 390.- ส่งฟรี (งดรับ COD)
2️⃣ 1 กก. (4-6 ตัวใหญ่): โอน 550.- ส่งฟรี ⭐ขายดี (งดรับ COD)
3️⃣ 2 กก. (8-12 ตัวใหญ่): โอน 1,090.- ส่งฟรีรถห้องเย็น! (งดรับ COD)
👉 รับชุดไหน พิมพ์เลข 1, 2 หรือ 3 ได้เลยจ้า`,

        bank: `🏦 โอนเงินส่งฟรี ร้านป้าเข็ม:
• ธ.กรุงไทย: 038-0-25363-1 (นายจีรวัฒน์ พลอาจ)
👉 โอนแล้วส่งสลิป + พิมพ์ชื่อ-ที่อยู่-เบอร์โทร ได้เลยจ้า 🙏`,

        askAddress: `📍 พิมพ์แจ้ง 3 อย่างเพื่อจัดส่งได้เลยจ้า:
1️⃣ ชุดที่รับ: พิมพ์ 1 (500g) / 2 (1 กก.) / 3 (2 กก.)
2️⃣ ชำระแบบ: โอนส่งฟรี หรือ เก็บปลายทาง
3️⃣ ชื่อ - ที่อยู่จัดส่ง - เบอร์โทร 10 หลัก (หรือส่งรูปหน้าซองจดหมายได้จ้า)`,

        shipping: `❄️ ซีลสูญญากาศแช่แข็ง -18°C แพ็กซองฟอยล์เก็บความเย็น
🚚 จัดส่ง 1-2 วันถึงบ้าน (เสียเคลมฟรี 100%)
👉 พิมพ์เลข 1 (500g), 2 (1 กก.) หรือ 3 (2 กก.) เพื่อสั่งซื้อได้เลยจ้า`
    };

    let cachedPricePngBlob = null;
    let cachedFriedPngBlob = null;

    function convertBlobToPng(blob) {
        return new Promise((resolve) => {
            const img = new Image();
            img.crossOrigin = "anonymous";
            const url = URL.createObjectURL(blob);
            img.onload = () => {
                const canvas = document.createElement("canvas");
                canvas.width = img.naturalWidth;
                canvas.height = img.naturalHeight;
                const ctx = canvas.getContext("2d");
                ctx.drawImage(img, 0, 0);
                URL.revokeObjectURL(url);
                canvas.toBlob((pngBlob) => resolve(pngBlob), "image/png");
            };
            img.onerror = () => resolve(null);
            img.src = url;
        });
    }

    async function prefetchImageBlobs() {
        try {
            if (!cachedPricePngBlob) {
                const res = await fetch(IMAGES.price, { mode: "cors" });
                const rawBlob = await res.blob();
                cachedPricePngBlob = await convertBlobToPng(rawBlob);
            }
        } catch (e) {}
        try {
            if (!cachedFriedPngBlob) {
                const res2 = await fetch(IMAGES.fried, { mode: "cors" });
                const rawBlob2 = await res2.blob();
                cachedFriedPngBlob = await convertBlobToPng(rawBlob2);
            }
        } catch (e) {}
    }

    async function copyPngBlobToClipboard(pngBlob) {
        if (!pngBlob) return false;
        try {
            if (navigator.clipboard && navigator.clipboard.write) {
                await navigator.clipboard.write([new ClipboardItem({ "image/png": pngBlob })]);
                return true;
            }
        } catch (e) {}
        return false;
    }

    function isElementVisible(el) {
        if (!el) return false;
        try {
            const rect = el.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0;
        } catch (e) {
            return false;
        }
    }

    function getElementByXPath(xpath, context = document) {
        try {
            const result = document.evaluate(xpath, context, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
            return result.singleNodeValue;
        } catch (e) {
            return null;
        }
    }

    // ==============================================================
    // 🔍 ค้นหากล่องพิมพ์ข้อความแชท Messenger / Meta Business Suite Inbox
    // ==============================================================
    function findMessengerComposer() {
        // 1. Meta Business Suite / Messenger Lexical Editor
        const lexicals = Array.from(document.querySelectorAll('div[data-lexical-editor="true"][contenteditable="true"], div[role="textbox"][contenteditable="true"]'))
            .filter((el) => !el.closest("#pakhem-group-helper") && isElementVisible(el));

        // ให้ความสำคัญกับกล่องที่มี aria-label เกี่ยวกับแชท/ข้อความ/ความคิดเห็น
        const chatBox = lexicals.find((el) => {
            const label = ((el.getAttribute("aria-label") || "") + " " + (el.getAttribute("aria-placeholder") || "")).toLowerCase();
            return (
                label.includes("ข้อความ") ||
                label.includes("ตอบกลับ") ||
                label.includes("ความคิดเห็น") ||
                label.includes("message") ||
                label.includes("reply") ||
                label.includes("comment") ||
                label.includes("aa")
            );
        });
        if (chatBox) return chatBox;
        if (lexicals.length > 0) return lexicals[lexicals.length - 1];

        // 2. XPath fallback
        const xp = getElementByXPath(
            '//div[contains(@aria-label, "ข้อความ") and @contenteditable="true"] | ' +
            '//div[contains(@aria-label, "ตอบกลับ") and @contenteditable="true"] | ' +
            '//div[contains(@aria-label, "ความคิดเห็น") and @contenteditable="true"] | ' +
            '//div[contains(@aria-label, "Message") and @contenteditable="true"]'
        );
        if (xp && !xp.closest("#pakhem-group-helper") && isElementVisible(xp)) return xp;

        return null;
    }

    async function insertTextIntoEditor(composer, text) {
        if (!composer) return false;
        composer.focus();
        await new Promise((r) => setTimeout(r, 80));

        // เคลียร์ข้อความค้างเดิมถ้ามี หรือวางต่อท้าย
        try {
            const sel = window.getSelection();
            sel.removeAllRanges();
            const range = document.createRange();
            range.selectNodeContents(composer);
            range.collapse(false);
            sel.addRange(range);
            document.execCommand("insertText", false, text);
        } catch (e) {}

        await new Promise((r) => setTimeout(r, 120));

        const currentContent = (composer.textContent || "").trim();
        if (!currentContent || currentContent.length < 5) {
            try {
                const dt = new DataTransfer();
                dt.setData("text/plain", text);
                const pasteEvt = new ClipboardEvent("paste", {
                    bubbles: true,
                    cancelable: true,
                    clipboardData: dt
                });
                composer.dispatchEvent(pasteEvt);
            } catch (e) {}
        }

        await new Promise((r) => setTimeout(r, 100));
        return (composer.textContent || "").trim().length >= 5;
    }

    // ==============================================================
    // 🧠 ระบบสกัด ชื่อ-เบอร์โทร-ที่อยู่-แพ็กเกจ จากหน้าแชทอัจฉริยะ
    // ==============================================================
    function getChatCustomerName() {
        const ignoreNames = [
            "ป้าเข็ม", "ครัวแม่บ้าน", "แชท", "ข้อความ", "เพจ", "กล่องข้อความ",
            "messenger", "facebook", "meta business suite", "ความคิดเห็น",
            "การแจ้งเตือน", "ค้นหา", "รายละเอียด", "ข้อมูลติดต่อ"
        ];

        const isValidCustomerName = (txt) => {
            if (!txt || txt.length < 2 || txt.length > 45) return false;
            const lower = txt.toLowerCase();
            if (ignoreNames.some((w) => lower.includes(w))) return false;
            if (/^\d+$/.test(txt)) return false;
            if (txt.includes("ใช้งานเมื่อ") || txt.includes("กำลังใช้งาน") || txt.includes("Active")) return false;
            return true;
        };

        // 1. หัวแชทในหน้า Messenger / Meta Business Suite (div[role="main"] h2 / h1 / span)
        const headerCandidates = Array.from(
            document.querySelectorAll(
                'div[role="main"] h1, div[role="main"] h2, div[role="main"] a[role="link"] span[dir="auto"], div[aria-label*="การสนทนากับ"] h2, div[aria-label*="Conversation with"] h2'
            )
        ).filter((el) => !el.closest("#pakhem-group-helper") && isElementVisible(el));

        for (const el of headerCandidates) {
            const t = (el.textContent || "").trim();
            if (isValidCustomerName(t)) return t;
        }

        // 2. ตรวจจาก aria-label ของกล่องสนทนา เช่น "การสนทนากับ สมชาย ใจดี"
        const convBox = document.querySelector('div[aria-label^="การสนทนากับ "], div[aria-label^="Conversation with "]');
        if (convBox) {
            const label = (convBox.getAttribute("aria-label") || "")
                .replace(/^การสนทนากับ\s+/i, "")
                .replace(/^Conversation with\s+/i, "")
                .trim();
            if (isValidCustomerName(label)) return label;
        }

        return "";
    }

    function isOurOwnShopText(line) {
        if (!line) return true;
        const shopMarkers = [
            "ปลาสลิดแดดเดียวสุพรรณแท้",
            "ราคามาตรฐานส่งฟรี",
            "โปรโมชั่นส่งฟรี",
            "038-0-25363-1",
            "0380253631",
            "093-532-5959",
            "0935325959",
            "นายจีรวัฒน์ พลอาจ",
            "รหัสสั่งซื้อ: PKF-",
            "ป้าเข็มบันทึกออเดอร์",
            "ต.เสาธง อ.บางปะหัน",
            "กดปุ่มเลือก",
            "สูตรทองคำ"
        ];
        return shopMarkers.some((m) => line.includes(m));
    }

    function extractOrderFromChat() {
        const widget = document.getElementById("pakhem-group-helper");
        const selectors = [
            'div[data-scope="messages_table"] div[dir="auto"]',
            'div[role="main"] div[role="row"] div[dir="auto"]',
            'div[role="main"] div[dir="auto"]',
            'div[data-lexical-text="true"]',
            'span[dir="auto"]'
        ];

        let collectedLines = [];
        const seenText = new Set();

        for (const sel of selectors) {
            const els = Array.from(document.querySelectorAll(sel));
            for (const el of els) {
                if (widget && widget.contains(el)) continue;
                // ข้ามสิ่งที่อยู่ในกล่องพิมพ์แชทของเราเอง
                if (el.closest('div[contenteditable="true"]')) continue;
                const raw = (el.innerText || el.textContent || "").trim();
                if (!raw || raw.length < 2) continue;
                for (const subLine of raw.split(/\r?\n/)) {
                    const clean = subLine.trim();
                    if (clean.length >= 2 && !seenText.has(clean)) {
                        seenText.add(clean);
                        collectedLines.push(clean);
                    }
                }
            }
            if (collectedLines.length >= 15) break;
        }

        // กรองข้อความของร้านออกเพื่อให้ได้เฉพาะข้อความฝั่งลูกค้า
        const customerLines = collectedLines.filter((l) => !isOurOwnShopText(l));
        const customerText = customerLines.join("\n");

        // 1. สกัดเบอร์โทรศัพท์ผู้รับ (06, 08, 09 หรือเบอร์บ้าน 02-07) ยกเว้นเบอร์ร้าน 0935325959 และเลขบัญชี 0380253631
        const phoneRegex = /(?:0[689]\d[\s\-]?\d{3}[\s\-]?\d{4}|0[23457]\d[\s\-]?\d{3}[\s\-]?\d{3,4})/g;
        let detectedPhone = "";
        let match;
        while ((match = phoneRegex.exec(customerText)) !== null) {
            const digits = match[0].replace(/[\s\-]/g, "");
            if (digits !== "0935325959" && digits !== "0380253631") {
                detectedPhone = digits; // เอาเบอร์ล่าสุดที่ลูกค้าพิมพ์
            }
        }

        // 2. สกัดรหัสไปรษณีย์ 5 หลัก (ยกเว้น 13220 ถ้าอยู่ในประโยคเสาธง บางปะหัน)
        const zipRegex = /\b([1-9]\d{4})\b/g;
        let detectedZip = "";
        while ((match = zipRegex.exec(customerText)) !== null) {
            const z = match[1];
            // ข้ามถ้าเป็นตัวเลขราคาหรือปี พ.ศ. เช่น 2567, 2568, 2569
            if (z.startsWith("256")) continue;
            detectedZip = z;
        }

        // 3. สกัดบรรทัดที่อยู่จัดส่ง
        const addrKeywords = [
            "บ้านเลขที่", "เลขที่", "ม.", "หมู่", "หมู่บ้าน", "ซ.", "ซอย", "ถ.", "ถนน",
            "ต.", "ตำบล", "แขวง", "อ.", "อำเภอ", "เขต", "จ.", "จังหวัด", "กทม", "กรุงเทพ",
            "คอนโด", "อาคาร", "ชั้น", "ห้อง"
        ];
        const addressParts = [];
        for (const line of customerLines) {
            if (line.length < 4 || line.length > 260) continue;
            // ข้ามบรรทัดที่เป็นแค่เวลาหรือสถานะแชท
            if (/^\d{1,2}:\d{2}/.test(line) || line.includes("ส่งเมื่อ") || line.includes("เห็นแล้ว")) continue;

            const hasAddrKw = addrKeywords.some((kw) => line.includes(kw));
            const hasHouseNum = /\b\d{1,5}(\/\d{1,4})?\b/.test(line) && (hasAddrKw || (detectedZip && line.includes(detectedZip)));
            const hasZipInLine = detectedZip && line.includes(detectedZip);

            if (hasAddrKw || hasHouseNum || hasZipInLine) {
                // ลบเบอร์โทรออกจากบรรทัดที่อยู่ถ้าปนมา
                let cleanedAddr = line;
                if (detectedPhone) {
                    cleanedAddr = cleanedAddr.replace(new RegExp(detectedPhone.split("").join("[\\s\\-]*"), "g"), "").trim();
                }
                if (cleanedAddr && !addressParts.includes(cleanedAddr)) {
                    addressParts.push(cleanedAddr);
                }
            }
        }

        let fullAddress = addressParts.join(" ").replace(/\s{2,}/g, " ").trim();
        if (detectedZip && fullAddress && !fullAddress.includes(detectedZip)) {
            fullAddress = `${fullAddress} ${detectedZip}`.trim();
        }

        // 4. สกัดชื่อลูกค้า (จากหัวแชท หรือจากข้อความที่ขึ้นต้นด้วย ชื่อ / คุณ)
        let detectedName = getChatCustomerName();
        if (!detectedName) {
            for (const line of customerLines) {
                const mName = line.match(/^(?:ชื่อ|ผู้รับ|คุณ)\s*([ก-๙a-zA-Z\s]{3,35})$/);
                if (mName && mName[1]) {
                    detectedName = mName[1].trim();
                    break;
                }
            }
        }

        // 5. สกัดแพ็กเกจและวิธีชำระเงินจากบริบทแชท
        let detectedPkgValue = "SKU-SLID-MD-1KG|TRANSFER|550|ปลาสลิดแดดเดียว ชุดยอดฮิต 1 กิโลกรัม (โอนส่งฟรี)";
        const isCod = customerText.includes("ปลายทาง") || customerText.toUpperCase().includes("COD") || customerText.includes("เก็บเงินปลายทาง");

        if (
            customerText.includes("2 โล") ||
            customerText.includes("2โล") ||
            customerText.includes("2 กก") ||
            customerText.includes("2 กิโล") ||
            customerText.includes("2กิโล") ||
            customerText.includes("1,090") ||
            customerText.includes("1090") ||
            customerText.includes("ชุด 3") ||
            customerText.includes("ชุดที่ 3")
        ) {
            // กฎเหล็กข้อ 7: ชุด 2 กก. ส่งฟรีรถห้องเย็น รับเฉพาะโอนเงินเท่านั้น
            detectedPkgValue = "SKU-SLID-MD-2KG|TRANSFER|1090|ปลาสลิดแดดเดียว ชุดตุนสุดคุ้ม 2 กิโลกรัม (ส่งฟรีรถห้องเย็น)";
        } else if (
            customerText.includes("ครึ่งโล") ||
            customerText.includes("500") ||
            customerText.includes("390") ||
            customerText.includes("410") ||
            customerText.includes("ชุด 1") ||
            customerText.includes("ชุดที่ 1")
        ) {
            detectedPkgValue = isCod
                ? "SKU-SLID-MD-500G|COD|410|ปลาสลิดแดดเดียว ชุดพอดีมื้อ 500 กรัม (เก็บปลายทาง COD)"
                : "SKU-SLID-MD-500G|TRANSFER|390|ปลาสลิดแดดเดียว ชุดพอดีมื้อ 500 กรัม (โอนส่งฟรี)";
        } else {
            detectedPkgValue = isCod
                ? "SKU-SLID-MD-1KG|COD|570|ปลาสลิดแดดเดียว ชุดยอดฮิต 1 กิโลกรัม (เก็บปลายทาง COD)"
                : "SKU-SLID-MD-1KG|TRANSFER|550|ปลาสลิดแดดเดียว ชุดยอดฮิต 1 กิโลกรัม (โอนส่งฟรี)";
        }

        return {
            customerName: detectedName,
            phone: detectedPhone,
            zip: detectedZip,
            address: fullAddress,
            pkgValue: detectedPkgValue,
            rawCustomerText: customerText
        };
    }

    // ==============================================================
    // 💾 บันทึกออเดอร์เข้า Supabase + Google Sheets + Telegram
    // ==============================================================
    async function saveOrderToBackend(orderPayload) {
        const now = new Date();
        const pad = (n) => String(n).padStart(2, "0");
        const orderId =
            orderPayload.orderId ||
            `PKF-${pad(now.getMonth() + 1)}${pad(now.getDate())}${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;

        const fullPayload = {
            ...orderPayload,
            orderId,
            sourceUrl: window.location.href
        };

        // 1. ส่งผ่าน Background Service Worker ก่อน (ไม่ติด CSP ของ Facebook 100%)
        if (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.sendMessage) {
            try {
                const bgRes = await new Promise((resolve) => {
                    chrome.runtime.sendMessage({ action: "SAVE_INBOX_ORDER", payload: fullPayload }, (res) => {
                        if (chrome.runtime.lastError) {
                            resolve(null);
                        } else {
                            resolve(res);
                        }
                    });
                });
                if (bgRes && bgRes.ok) {
                    saveLocalOrderHistory(fullPayload);
                    return { ok: true, orderId: bgRes.orderId || orderId };
                }
            } catch (e) {}
        }

        // 2. Fallback: ยิงตรงจาก Content Script (กรณีรันผ่าน Userscript หรือ Service Worker หลับ)
        let saved = false;
        try {
            const rSupa = await fetch(SUPABASE_URL, {
                method: "POST",
                headers: {
                    apikey: SUPABASE_ANON_KEY,
                    Authorization: "Bearer " + SUPABASE_ANON_KEY,
                    "Content-Type": "application/json",
                    Prefer: "return=minimal"
                },
                body: JSON.stringify({
                    order_code: orderId,
                    product_name: "ปลาสลิดแดดเดียวสุพรรณแท้ ป้าเข็ม คัดพิเศษ",
                    package_code: fullPayload.sku,
                    package_name: fullPayload.pkgLabel,
                    price: fullPayload.price,
                    customer_name: fullPayload.customerName,
                    phone: fullPayload.phone,
                    address: fullPayload.address,
                    payment_method: fullPayload.payMethod,
                    status: "PENDING",
                    note: `[InboxHelper v8.0] ${fullPayload.sourceUrl}`,
                    created_at: now.toISOString()
                })
            });
            if (rSupa.ok || rSupa.status === 201 || rSupa.status === 409) saved = true;
        } catch (e) {}

        try {
            await fetch(GAS_WEBHOOK_URL, {
                method: "POST",
                mode: "no-cors",
                headers: { "Content-Type": "text/plain;charset=utf-8" },
                body: JSON.stringify({
                    action: "order_fish",
                    order_id: orderId,
                    skip_db: saved,
                    name: fullPayload.customerName,
                    phone: fullPayload.phone,
                    address: fullPayload.address,
                    package: fullPayload.sku,
                    package_name: fullPayload.pkgLabel,
                    price: fullPayload.price,
                    payment_method: fullPayload.payMethod,
                    note: `[InboxHelper v8.0] ${fullPayload.sourceUrl}`
                })
            });
            saved = true;
        } catch (e) {}

        saveLocalOrderHistory(fullPayload);
        return { ok: saved, orderId };
    }

    function getLocalOrdersHistory() {
        try {
            const raw = localStorage.getItem("pkh_saved_orders_history_v8");
            return raw ? JSON.parse(raw) : [];
        } catch (e) {
            return [];
        }
    }

    function saveLocalOrderHistory(entry) {
        try {
            const list = getLocalOrdersHistory();
            const newItem = {
                orderId: entry.orderId,
                customerName: entry.customerName,
                phone: entry.phone,
                address: entry.address,
                pkgLabel: entry.pkgLabel,
                price: entry.price,
                payMethod: entry.payMethod,
                createdAt: new Date().toLocaleString("th-TH")
            };
            const updated = [newItem, ...list.filter((x) => x.orderId !== entry.orderId)].slice(0, 50);
            localStorage.setItem("pkh_saved_orders_history_v8", JSON.stringify(updated));
        } catch (e) {}
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

    // ==============================================================
    // 🖥️ สร้างแผงควบคุมลอยตัว: ผู้ช่วยปิดการขายในแชท + เชิญคนถูกใจ (v8.4)
    // ==============================================================
    function createWidget() {
        const existing = document.getElementById("pakhem-group-helper");
        if (existing && existing.getAttribute("data-pkh-ver") === "8.7") {
            return;
        }
        if (existing) {
            existing.remove();
        }

        const widget = document.createElement("div");
        widget.id = "pakhem-group-helper";
        widget.setAttribute("data-pkh-ver", "8.7");
        widget.style.cssText = `
            position: fixed;
            bottom: 14px;
            right: 14px;
            z-index: 2147483647;
            background: #ffffff;
            border-radius: 12px;
            box-shadow: 0 8px 28px rgba(0,0,0,0.28);
            width: 270px;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            border: 2px solid #1b5e20;
            overflow: hidden;
            box-sizing: border-box;
            user-select: none;
        `;

        const savedPos = localStorage.getItem("pkh_widget_pos_v8");
        if (savedPos) {
            try {
                const pos = JSON.parse(savedPos);
                const safeLeft = Math.max(4, Math.min(window.innerWidth - 200, Number(pos.left) || 14));
                const safeTop = Math.max(4, Math.min(window.innerHeight - 60, Number(pos.top) || 60));
                widget.style.top = `${safeTop}px`;
                widget.style.left = `${safeLeft}px`;
                widget.style.bottom = "auto";
                widget.style.right = "auto";
            } catch (e) {}
        }

        widget.innerHTML = `
            <div id="pkh-header" title="คลิกค้างเพื่อลากย้ายตำแหน่ง" style="background: linear-gradient(135deg, #0d47a1, #1976d2); color: #fff; padding: 7px 9px; font-weight: bold; font-size: 12px; display: flex; justify-content: space-between; align-items: center; cursor: move; user-select: none; touch-action: none;">
                <span id="pkh-header-text" style="pointer-events: none; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">🐟 ป้าเข็ม v8.7: ปิดการขาย</span>
                <div style="display: flex; align-items: center; gap: 3px; flex-shrink: 0;">
                    <button type="button" id="pkh-snap-left" style="background: rgba(255,255,255,0.22); color: #fff; border: none; border-radius: 4px; padding: 1px 5px; font-size: 10px; cursor: pointer;" title="ชิดซ้าย">◀ซ้าย</button>
                    <button type="button" id="pkh-snap-right" style="background: rgba(255,255,255,0.22); color: #fff; border: none; border-radius: 4px; padding: 1px 5px; font-size: 10px; cursor: pointer;" title="ชิดขวา">ขวา▶</button>
                    <button type="button" id="pkh-toggle" style="background: rgba(255,255,255,0.28); color: #fff; border: none; border-radius: 4px; padding: 1px 6px; font-size: 12px; font-weight: bold; cursor: pointer;" title="พับเก็บ/ขยาย">—</button>
                </div>
            </div>

            <div id="pkh-body" style="padding: 8px; font-size: 11px; color: #222; background: #ffffff;">
                <!-- 🔍 ปุ่มดึงข้อมูลลูกค้าจากแชทอัตโนมัติ -->
                <button type="button" id="pkh-btn-extract-addr" style="width: 100%; background: linear-gradient(135deg, #0062cc, #007bff); color: #fff; border: none; border-radius: 7px; padding: 7px 6px; font-weight: bold; font-size: 11.5px; cursor: pointer; margin-bottom: 6px; box-shadow: 0 2px 5px rgba(0,123,255,0.25);">
                    🔍 ดึงชื่อ-ที่อยู่-เบอร์โทรจากแชทนี้
                </button>

                <!-- 📝 ฟอร์มตรวจสอบและเปิดบิลรับออเดอร์ -->
                <div style="background: #f8fafd; border: 1px solid #cfe2ff; border-radius: 8px; padding: 6px; margin-bottom: 6px;">
                    <div style="display: flex; gap: 4px; margin-bottom: 4px;">
                        <input type="text" id="pkh-ord-name" placeholder="👤 ชื่อลูกค้า" style="flex: 1; width: 48%; padding: 5px 6px; font-size: 11px; border: 1px solid #ced4da; border-radius: 5px; background: #fff; color: #222; box-sizing: border-box;">
                        <input type="text" id="pkh-ord-phone" placeholder="📞 เบอร์โทร 10 หลัก" style="flex: 1; width: 52%; padding: 5px 6px; font-size: 11px; border: 1px solid #ced4da; border-radius: 5px; background: #fff; color: #222; font-weight: bold; box-sizing: border-box;">
                    </div>

                    <textarea id="pkh-ord-addr" placeholder="📍 ที่อยู่จัดส่ง (บ้านเลขที่ ตำบล อำเภอ จังหวัด รหัสปณ.)" style="width: 100%; height: 42px; padding: 5px 6px; font-size: 11px; border: 1px solid #ced4da; border-radius: 5px; background: #fff; color: #222; resize: none; margin-bottom: 4px; font-family: inherit; box-sizing: border-box;"></textarea>

                    <select id="pkh-ord-pkg" style="width: 100%; padding: 5px; font-size: 10.5px; font-weight: bold; border: 1px solid #28a745; border-radius: 5px; background: #e8f5e9; color: #1b5e20; margin-bottom: 6px; cursor: pointer; box-sizing: border-box;">
                        <option value="SKU-SLID-MD-1KG|TRANSFER|550|ปลาสลิดแดดเดียว ชุดยอดฮิต 1 กิโลกรัม (โอนส่งฟรี)">⭐ ชุด 1 กก. (5-7 ตัว) — โอน 550.- ส่งฟรี</option>
                        <option value="SKU-SLID-MD-1KG|TRANSFER|550|ปลาสลิดแดดเดียว ชุดยอดฮิต 1 กิโลกรัม (โอนเงินส่งฟรี)">📦 ชุด 1 กก. (4-6 ตัวใหญ่) — โอน 550.- ส่งฟรี</option>
                        <option value="SKU-SLID-MD-500G|TRANSFER|390|ปลาสลิดแดดเดียว ชุดพอดีมื้อ 500 กรัม (โอนส่งฟรี)">🐟 ชุด 500g (3-4 ตัว) — โอน 390.- ส่งฟรี</option>
                        <option value="SKU-SLID-MD-500G|TRANSFER|390|ปลาสลิดแดดเดียว ชุดพอดีมื้อ 500 กรัม (โอนเงินส่งฟรี)">📦 ชุด 500g (2-3 ตัวใหญ่) — โอน 390.- ส่งฟรี</option>
                        <option value="SKU-SLID-MD-2KG|TRANSFER|1090|ปลาสลิดแดดเดียว ชุดตุนสุดคุ้ม 2 กิโลกรัม (ส่งฟรีรถห้องเย็น)">❄️ ชุด 2 กก. (10-14 ตัว) — โอน 1,090.- รถห้องเย็น</option>
                    </select>

                    <button type="button" id="pkh-btn-submit-order" style="width: 100%; background: linear-gradient(135deg, #1b5e20, #28a745); color: #fff; border: none; border-radius: 6px; padding: 8px 4px; font-weight: bold; font-size: 11.5px; cursor: pointer; box-shadow: 0 2px 6px rgba(40,167,69,0.3);">
                        💾 บันทึกออเดอร์ + ส่งบิลสรุปยอด
                    </button>
                </div>

                <!-- ⚡ ปุ่มส่งข้อความตอบแชทด่วน 1-คลิก -->
                <div style="font-size: 10px; font-weight: bold; color: #555; margin-bottom: 3px;">⚡ ส่งข้อความด่วนเข้าแชท 1-คลิก:</div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 4px; margin-bottom: 5px;">
                    <button type="button" id="pkh-btn-send-price" style="background: #e8f5e9; color: #1b5e20; border: 1px solid #a5d6a7; border-radius: 5px; padding: 5px 3px; font-size: 10px; font-weight: bold; cursor: pointer;">
                        📋 แจ้งราคา 3 ชุด
                    </button>
                    <button type="button" id="pkh-btn-send-bank" style="background: #fff3cd; color: #856404; border: 1px solid #ffeeba; border-radius: 5px; padding: 5px 3px; font-size: 10px; font-weight: bold; cursor: pointer;">
                        🏦 เลขบัญชีกรุงไทย
                    </button>
                    <button type="button" id="pkh-btn-ask-addr" style="background: #e8f4fd; color: #004085; border: 1px solid #b8daff; border-radius: 5px; padding: 5px 3px; font-size: 10px; font-weight: bold; cursor: pointer;">
                        📍 ขอชื่อ-ที่อยู่ลูกค้า
                    </button>
                    <button type="button" id="pkh-btn-send-shipping" style="background: #f3e5f5; color: #4a148c; border: 1px solid #e1bee7; border-radius: 5px; padding: 5px 3px; font-size: 10px; font-weight: bold; cursor: pointer;">
                        ❄️ แจ้งรอบส่ง/วิธีเก็บ
                    </button>
                </div>

                <!-- 🖼️ ปุ่มก๊อปปี้รูปภาพส่งให้ลูกค้าในแชท -->
                <div style="display: flex; gap: 4px; margin-bottom: 5px;">
                    <button type="button" id="pkh-btn-copy-img" style="flex: 1; background: #f0f2f5; color: #333; border: 1px solid #ced4da; border-radius: 5px; padding: 4px 2px; font-size: 10px; font-weight: bold; cursor: pointer;">
                        🖼️ ก๊อปรูปป้ายราคา
                    </button>
                    <button type="button" id="pkh-btn-copy-fried" style="flex: 1; background: #f0f2f5; color: #333; border: 1px solid #ced4da; border-radius: 5px; padding: 4px 2px; font-size: 10px; font-weight: bold; cursor: pointer;">
                        🍳 ก๊อปรูปปลาทอด
                    </button>
                </div>

                <!-- 💬 ปุ่มตอบคอมเมนต์ลูกค้าในโพสต์กลุ่ม/ไลฟ์สดอัตโนมัติ (Guided Navigator 1-2-3) -->
                <button type="button" id="pkh-btn-reply-comments" style="width: 100%; background: linear-gradient(135deg, #00897b, #26a69a); color: #fff; border: none; border-radius: 6px; padding: 6px 4px; font-weight: bold; font-size: 11px; cursor: pointer; margin-bottom: 4px; box-shadow: 0 2px 5px rgba(0,137,123,0.25);">
                    💬 ตอบเม้นต์ในโพสต์นี้ทันที (ออโต้: เปิด ✅)
                </button>

                <!-- 👍 ปุ่มเชิญคนกดถูกใจโพสต์ให้ติดตามเพจ 1-คลิก -->
                <button type="button" id="pkh-btn-invite-likers" style="width: 100%; background: linear-gradient(135deg, #e65100, #f57c00); color: #fff; border: none; border-radius: 6px; padding: 6px 4px; font-weight: bold; font-size: 11px; cursor: pointer; margin-bottom: 6px; box-shadow: 0 2px 5px rgba(245,124,0,0.25);">
                    👍 เชิญคนถูกใจโพสต์ให้ติดตามเพจ (1-คลิก)
                </button>

                <!-- 📜 ประวัติออเดอร์ล่าสุด (พับ/กางได้) -->
                <div style="border-top: 1px solid #e9ecef; padding-top: 4px; margin-bottom: 4px;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <button type="button" id="pkh-btn-toggle-history" style="background: transparent; border: none; font-size: 10px; font-weight: bold; color: #0d47a1; cursor: pointer; padding: 0;">
                            📜 ออเดอร์ที่บันทึกแล้ว (<span id="pkh-history-count">0</span>) ▼
                        </button>
                        <button type="button" id="pkh-btn-clear-form" style="background: transparent; border: none; font-size: 10px; color: #6c757d; cursor: pointer; padding: 0;" title="ล้างช่องกรอกเพื่อรับลูกค้าคนต่อไป">
                            🧹 ล้างฟอร์ม
                        </button>
                    </div>
                    <div id="pkh-history-box" style="display: none; max-height: 95px; overflow-y: auto; margin-top: 4px; background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 5px; padding: 4px; font-size: 10px;"></div>
                </div>

                <div id="pkh-toast" style="font-size: 10px; color: #0c5460; text-align: center; min-height: 20px; line-height: 1.35; padding: 4px; background: #e8f4fd; border-radius: 5px; font-weight: bold;">
                    💡 เปิดแชทลูกค้า แล้วกด "🔍 ดึงชื่อ-ที่อยู่" ได้เลยจ้า
                </div>
            </div>
        `;

        document.body.appendChild(widget);

        // อ้างอิง Elements
        const header = widget.querySelector("#pkh-header");
        const toggleBtn = widget.querySelector("#pkh-toggle");
        const bodyDiv = widget.querySelector("#pkh-body");
        const snapLeftBtn = widget.querySelector("#pkh-snap-left");
        const snapRightBtn = widget.querySelector("#pkh-snap-right");
        const toastEl = widget.querySelector("#pkh-toast");

        const btnExtractAddr = widget.querySelector("#pkh-btn-extract-addr");
        const ordNameInput = widget.querySelector("#pkh-ord-name");
        const ordPhoneInput = widget.querySelector("#pkh-ord-phone");
        const ordAddrInput = widget.querySelector("#pkh-ord-addr");
        const ordPkgSelect = widget.querySelector("#pkh-ord-pkg");
        const btnSubmitOrder = widget.querySelector("#pkh-btn-submit-order");

        const btnSendPrice = widget.querySelector("#pkh-btn-send-price");
        const btnSendBank = widget.querySelector("#pkh-btn-send-bank");
        const btnAskAddr = widget.querySelector("#pkh-btn-ask-addr");
        const btnSendShipping = widget.querySelector("#pkh-btn-send-shipping");
        const btnCopyImg = widget.querySelector("#pkh-btn-copy-img");
        const btnCopyFried = widget.querySelector("#pkh-btn-copy-fried");

        const btnToggleHistory = widget.querySelector("#pkh-btn-toggle-history");
        const historyCountSpan = widget.querySelector("#pkh-history-count");
        const historyBox = widget.querySelector("#pkh-history-box");
        const btnClearForm = widget.querySelector("#pkh-btn-clear-form");

        function showToast(msg, color = "#0c5460", bg = "#e8f4fd") {
            if (!toastEl) return;
            toastEl.innerHTML = msg;
            toastEl.style.color = color;
            toastEl.style.background = bg;
        }

        // ==============================================================
        // ✥ ระบบลากย้ายตำแหน่งและพับเก็บวิดเจ็ต
        // ==============================================================
        let isDragging = false;
        let dragOffsetX = 0;
        let dragOffsetY = 0;

        header.addEventListener("pointerdown", (e) => {
            if (e.button !== 0 || e.target.closest("button")) return;
            e.preventDefault();
            isDragging = true;
            const rect = widget.getBoundingClientRect();
            dragOffsetX = e.clientX - rect.left;
            dragOffsetY = e.clientY - rect.top;
            try {
                header.setPointerCapture(e.pointerId);
            } catch (err) {}

            const onMove = (ev) => {
                if (!isDragging) return;
                const newLeft = Math.max(4, Math.min(window.innerWidth - widget.offsetWidth - 4, ev.clientX - dragOffsetX));
                const newTop = Math.max(4, Math.min(window.innerHeight - 45, ev.clientY - dragOffsetY));
                widget.style.left = `${newLeft}px`;
                widget.style.top = `${newTop}px`;
                widget.style.right = "auto";
                widget.style.bottom = "auto";
            };

            const onUp = (ev) => {
                isDragging = false;
                try {
                    header.releasePointerCapture(ev.pointerId);
                } catch (err) {}
                const rectNow = widget.getBoundingClientRect();
                localStorage.setItem("pkh_widget_pos_v8", JSON.stringify({ left: Math.round(rectNow.left), top: Math.round(rectNow.top) }));
                window.removeEventListener("pointermove", onMove, true);
                window.removeEventListener("pointerup", onUp, true);
            };

            window.addEventListener("pointermove", onMove, true);
            window.addEventListener("pointerup", onUp, true);
        });

        if (snapLeftBtn) {
            snapLeftBtn.addEventListener("click", (e) => {
                e.stopPropagation();
                widget.style.right = "auto";
                widget.style.bottom = "14px";
                widget.style.top = "auto";
                widget.style.left = "10px";
                const rect = widget.getBoundingClientRect();
                localStorage.setItem("pkh_widget_pos_v8", JSON.stringify({ left: Math.round(rect.left), top: Math.round(rect.top) }));
            });
        }

        if (snapRightBtn) {
            snapRightBtn.addEventListener("click", (e) => {
                e.stopPropagation();
                widget.style.left = "auto";
                widget.style.top = "auto";
                widget.style.right = "14px";
                widget.style.bottom = "14px";
                const rect = widget.getBoundingClientRect();
                localStorage.setItem("pkh_widget_pos_v8", JSON.stringify({ left: Math.round(rect.left), top: Math.round(rect.top) }));
            });
        }

        let isMinimized = false;
        if (toggleBtn) {
            toggleBtn.addEventListener("click", (e) => {
                e.stopPropagation();
                isMinimized = !isMinimized;
                bodyDiv.style.display = isMinimized ? "none" : "block";
                widget.style.width = isMinimized ? "195px" : "270px";
                toggleBtn.textContent = isMinimized ? "➕" : "—";
            });
        }

        // ==============================================================
        // 💬 ฟังก์ชันวางข้อความลงช่องแชท Messenger + ก๊อปปี้ลงคลิปบอร์ด
        // ==============================================================
        async function sendOrInsertChatReply(replyText, label, autoPressEnter = false) {
            try {
                await navigator.clipboard.writeText(replyText);
            } catch (e) {}

            const composer = findMessengerComposer();
            if (!composer) {
                showToast(`📋 ก๊อปปี้ <b>${label}</b> ลงคลิปบอร์ดแล้ว! (กด Ctrl+V ในช่องแชทได้เลย)`, "#004085", "#e8f4fd");
                return false;
            }

            const ok = await insertTextIntoEditor(composer, replyText);
            if (ok && autoPressEnter) {
                await new Promise((r) => setTimeout(r, 300));
                try {
                    const enterEvt = new KeyboardEvent("keydown", {
                        bubbles: true,
                        cancelable: true,
                        key: "Enter",
                        code: "Enter",
                        keyCode: 13,
                        which: 13
                    });
                    composer.dispatchEvent(enterEvt);
                    const sendBtn = document.querySelector(
                        'div[aria-label="กด Enter เพื่อส่ง"][role="button"], div[aria-label="Press enter to send"][role="button"], div[aria-label="ส่ง"][role="button"], div[aria-label="Send"][role="button"]'
                    );
                    if (sendBtn) sendBtn.click();
                } catch (e) {}
            }

            if (ok) {
                showToast(`✅ วาง <b>${label}</b> ในช่องแชทแล้ว! (กด Enter ส่งได้เลย)`, "#155724", "#d4edda");
                return true;
            } else {
                showToast(`📋 ก๊อปปี้ <b>${label}</b> แล้ว! คลิกช่องแชทแล้วกด <b>Ctrl+V</b> ได้เลย`, "#004085", "#e8f4fd");
                return false;
            }
        }

        // ==============================================================
        // 🔍 ปุ่มดึงข้อมูลลูกค้าจากแชทปัจจุบัน
        // ==============================================================
        function populateFormFromChat(showFeedback = true) {
            const info = extractOrderFromChat();
            let foundAny = false;

            if (info.customerName && ordNameInput) {
                ordNameInput.value = info.customerName;
                foundAny = true;
            }
            if (info.phone && ordPhoneInput) {
                ordPhoneInput.value = info.phone;
                foundAny = true;
            }
            if (info.address && ordAddrInput) {
                ordAddrInput.value = info.address;
                foundAny = true;
            }
            if (info.pkgValue && ordPkgSelect) {
                ordPkgSelect.value = info.pkgValue;
            }

            if (showFeedback) {
                if (info.phone || info.address) {
                    const labelSummary = `${info.customerName || "ลูกค้า"} | โทร: ${info.phone || "-"} | ที่อยู่: ${info.address || "-"}`;
                    try {
                        navigator.clipboard.writeText(labelSummary);
                    } catch (e) {}
                    showToast(
                        `✅ ดึงข้อมูลสำเร็จ! ตรวจทานแล้วกด <b>"💾 บันทึกออเดอร์"</b> ได้เลย`,
                        "#155724",
                        "#d4edda"
                    );
                } else if (foundAny) {
                    showToast(
                        `ℹ️ พบชื่อ <b>"${info.customerName}"</b> (รอลูกค้าพิมพ์ที่อยู่และเบอร์โทร หรือพิมพ์กรอกด้านบนได้เลย)`,
                        "#856404",
                        "#fff3cd"
                    );
                } else {
                    showToast(
                        `ℹ️ ยังไม่พบเบอร์โทร/ที่อยู่ในหน้าต่างนี้ (กดปุ่ม <b>"📍 ขอชื่อ-ที่อยู่ลูกค้า"</b> ส่งในแชทได้เลย)`,
                        "#856404",
                        "#fff3cd"
                    );
                }
            }
            return info;
        }

        if (btnExtractAddr) {
            btnExtractAddr.addEventListener("click", () => populateFormFromChat(true));
        }

        if (btnClearForm) {
            btnClearForm.addEventListener("click", () => {
                if (ordNameInput) ordNameInput.value = "";
                if (ordPhoneInput) ordPhoneInput.value = "";
                if (ordAddrInput) ordAddrInput.value = "";
                showToast("🧹 ล้างข้อมูลในฟอร์มเรียบร้อย พร้อมรับออเดอร์ถัดไปจ้า", "#0c5460", "#e8f4fd");
            });
        }

        // ==============================================================
        // 💾 ปุ่มบันทึกออเดอร์ + ส่งบิลสรุปยอดในแชท
        // ==============================================================
        function renderHistoryList() {
            const list = getLocalOrdersHistory();
            if (historyCountSpan) historyCountSpan.textContent = String(list.length);
            if (!historyBox) return;
            if (list.length === 0) {
                historyBox.innerHTML = `<div style="color:#6c757d; text-align:center; padding:4px;">ยังไม่มีประวัติออเดอร์ในเครื่องนี้</div>`;
                return;
            }
            historyBox.innerHTML = "";
            list.slice(0, 15).forEach((item) => {
                const row = document.createElement("div");
                row.style.cssText =
                    "padding: 4px 5px; margin-bottom: 3px; background: #fff; border: 1px solid #e9ecef; border-radius: 4px; display: flex; justify-content: space-between; align-items: center; gap: 4px;";
                const infoDiv = document.createElement("div");
                infoDiv.style.cssText = "overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1;";
                infoDiv.innerHTML = `<b>${item.customerName}</b> (${item.phone}) - <span style="color:#1b5e20;font-weight:bold;">${item.price}.-</span>`;
                infoDiv.title = `${item.orderId}\nผู้รับ: ${item.customerName} (${item.phone})\nที่อยู่: ${item.address}\nสินค้า: ${item.pkgLabel}`;

                const copyBtn = document.createElement("button");
                copyBtn.type = "button";
                copyBtn.textContent = "📋 ก๊อป";
                copyBtn.style.cssText =
                    "background: #007bff; color: #fff; border: none; border-radius: 3px; padding: 2px 5px; font-size: 9.5px; cursor: pointer; flex-shrink: 0;";
                copyBtn.addEventListener("click", async () => {
                    const labelTxt = `ผู้รับ: คุณ${item.customerName}\nโทร: ${item.phone}\nที่อยู่: ${item.address}\nสินค้า: ${item.pkgLabel} (${item.price} บาท - ${item.payMethod})`;
                    try {
                        await navigator.clipboard.writeText(labelTxt);
                        showToast(`📋 ก๊อปปี้ใบปะหน้าของ <b>คุณ${item.customerName}</b> แล้ว!`, "#155724", "#d4edda");
                    } catch (e) {}
                });

                row.appendChild(infoDiv);
                row.appendChild(copyBtn);
                historyBox.appendChild(row);
            });
        }

        if (btnToggleHistory && historyBox) {
            btnToggleHistory.addEventListener("click", () => {
                const isHidden = historyBox.style.display === "none";
                historyBox.style.display = isHidden ? "block" : "none";
                renderHistoryList();
            });
        }
        renderHistoryList();

        async function submitCurrentOrder() {
            const customerName = (ordNameInput ? ordNameInput.value.trim() : "") || getChatCustomerName() || "ลูกค้า Facebook";
            const phone = (ordPhoneInput ? ordPhoneInput.value.trim() : "").replace(/[\s\-]/g, "");
            const address = ordAddrInput ? ordAddrInput.value.trim() : "";
            const pkgRaw =
                ordPkgSelect && ordPkgSelect.value
                    ? ordPkgSelect.value
                    : "SKU-SLID-MD-1KG|TRANSFER|550|ปลาสลิดแดดเดียว ชุดยอดฮิต 1 กิโลกรัม (โอนส่งฟรี)";
            const [sku, payMethod, priceStr, pkgLabel] = pkgRaw.split("|");
            const priceNum = parseFloat(priceStr) || 550;

            if (!/^0\d{8,9}$/.test(phone)) {
                showToast("⚠️ กรุณากรอก <b>เบอร์โทรศัพท์ 10 หลัก</b> ของลูกค้าให้ถูกต้องก่อนครับ", "#721c24", "#f8d7da");
                if (ordPhoneInput) ordPhoneInput.focus();
                return { ok: false, error: "invalid_phone" };
            }

            if (address.length < 8) {
                showToast("⚠️ กรุณากรอก <b>ที่อยู่จัดส่ง</b> ของลูกค้าให้ครบก่อนครับ", "#721c24", "#f8d7da");
                if (ordAddrInput) ordAddrInput.focus();
                return { ok: false, error: "invalid_address" };
            }

            if (btnSubmitOrder) {
                btnSubmitOrder.disabled = true;
                btnSubmitOrder.textContent = "⏳ กำลังบันทึกออเดอร์...";
            }
            showToast("⏳ กำลังบันทึกออเดอร์เข้า Supabase + Google Sheets + Telegram...", "#004085", "#e8f4fd");

            const saveRes = await saveOrderToBackend({
                customerName,
                phone,
                address,
                sku,
                pkgLabel,
                price: priceNum,
                payMethod
            });

            const billMsg = buildConfirmationBillText(
                saveRes.orderId,
                customerName,
                phone,
                address,
                pkgLabel,
                priceNum,
                payMethod
            );

            await sendOrInsertChatReply(billMsg, `บิลสรุปยอด ${saveRes.orderId}`, true);
            renderHistoryList();

            if (btnSubmitOrder) {
                btnSubmitOrder.disabled = false;
                btnSubmitOrder.textContent = "💾 บันทึกออเดอร์ + ส่งบิลสรุปยอด";
            }

            showToast(
                `🎉 บันทึกออเดอร์ <b>${saveRes.orderId}</b> + ส่งบิลสรุปยอดสำเร็จ!`,
                "#155724",
                "#d4edda"
            );
            return { ok: true, orderId: saveRes.orderId, billMsg };
        }

        if (btnSubmitOrder) {
            btnSubmitOrder.addEventListener("click", submitCurrentOrder);
        }

        // ==============================================================
        // ⚡ ปุ่มส่งข้อความตอบแชทด่วน 1-คลิก
        // ==============================================================
        if (btnSendPrice) {
            btnSendPrice.addEventListener("click", () => sendOrInsertChatReply(MESSENGER_REPLIES.price, "ราคา 3 แพ็กเกจ"));
        }
        if (btnSendBank) {
            btnSendBank.addEventListener("click", () => sendOrInsertChatReply(MESSENGER_REPLIES.bank, "เลขบัญชีกรุงไทย"));
        }
        if (btnAskAddr) {
            btnAskAddr.addEventListener("click", () => sendOrInsertChatReply(MESSENGER_REPLIES.askAddress, "ข้อความขอชื่อ-ที่อยู่"));
        }
        if (btnSendShipping) {
            btnSendShipping.addEventListener("click", () => sendOrInsertChatReply(MESSENGER_REPLIES.shipping, "มาตรฐานจัดส่ง"));
        }

        if (btnCopyImg) {
            btnCopyImg.addEventListener("click", async () => {
                showToast("⏳ กำลังดึงรูปป้ายราคาลงคลิปบอร์ด...", "#004085", "#e8f4fd");
                await prefetchImageBlobs();
                const ok = await copyPngBlobToClipboard(cachedPricePngBlob);
                if (ok) {
                    showToast("🖼️ ก๊อปรูปป้ายราคาแล้ว! คลิกช่องแชทแล้วกด <b>Ctrl+V</b> วางได้เลย", "#155724", "#d4edda");
                } else {
                    showToast("❌ คลิปบอร์ดถูกบล็อก กรุณาลองคลิกอีกครั้งครับ", "#721c24", "#f8d7da");
                }
            });
        }

        if (btnCopyFried) {
            btnCopyFried.addEventListener("click", async () => {
                showToast("⏳ กำลังดึงรูปปลาทอดลงคลิปบอร์ด...", "#004085", "#e8f4fd");
                await prefetchImageBlobs();
                const ok = await copyPngBlobToClipboard(cachedFriedPngBlob);
                if (ok) {
                    showToast("🍳 ก๊อปรูปปลาทอดแล้ว! คลิกช่องแชทแล้วกด <b>Ctrl+V</b> วางได้เลย", "#155724", "#d4edda");
                } else {
                    showToast("❌ คลิปบอร์ดถูกบล็อก กรุณาลองคลิกอีกครั้งครับ", "#721c24", "#f8d7da");
                }
            });
        }

        // ==============================================================
        // 👍 ระบบเชิญคนกดถูกใจโพสต์ให้กดติดตามเพจอัตโนมัติ (1-Click Invite Post Likers v8.2)
        // ==============================================================
        const btnInviteLikers = widget.querySelector("#pkh-btn-invite-likers");
        let isInvitingLikers = false;

        function triggerReactClick(el) {
            if (!el) return;
            const target = el.closest('div[role="button"], span[role="button"], a[role="button"]') || el;
            try {
                target.scrollIntoView({ behavior: "instant", block: "nearest" });
            } catch (e) {}
            const opts = { bubbles: true, cancelable: true, view: window };
            try {
                target.dispatchEvent(new PointerEvent("pointerdown", opts));
                target.dispatchEvent(new MouseEvent("mousedown", opts));
                target.dispatchEvent(new PointerEvent("pointerup", opts));
                target.dispatchEvent(new MouseEvent("mouseup", opts));
                target.click();
            } catch (e) {
                try {
                    target.click();
                } catch (err) {}
            }
        }

        function findOpenReactionsDialog() {
            // ตรวจเฉพาะ Dialog ที่เป็นหน้าต่าง "คนที่แสดงความรู้สึก" เท่านั้น (ห้ามจำสลับกับ Dialog โพสต์หลัก!)
            const dialogs = Array.from(document.querySelectorAll('div[role="dialog"]'))
                .filter((d) => d.id !== "pakhem-group-helper" && isElementVisible(d))
                .reverse();

            for (const d of dialogs) {
                const aria = (d.getAttribute("aria-label") || "").trim();
                const txt = d.innerText || d.textContent || "";

                // ข้ามทันทีถ้าเป็น Dialog ของตัวโพสต์หลัก (ซึ่งจะมีช่องเขียนความคิดเห็น หรือปุ่มแชร์/แสดงความคิดเห็น)
                const isPostOrComposerModal =
                    txt.includes("สร้างโพสต์") ||
                    txt.includes("เขียนความคิดเห็น") ||
                    txt.includes("แสดงความคิดเห็นในชื่อ") ||
                    !!d.querySelector('div[aria-label="แสดงความคิดเห็น"][role="button"], div[aria-label="แชร์"][role="button"]');

                if (
                    aria.includes("คนที่แสดงความรู้สึก") ||
                    aria.includes("People who reacted") ||
                    txt.includes("คนที่แสดงความรู้สึก") ||
                    txt.includes("People who reacted")
                ) {
                    return d;
                }

                if (isPostOrComposerModal) continue;

                // ตรวจหาแถบแท็บ "ทั้งหมด" (All) ของหน้าต่าง Reactions
                const hasAllReactionTab = Array.from(d.querySelectorAll('div[role="tab"], span[role="tab"]')).some((tab) => {
                    const tt = (tab.textContent || "").trim();
                    const ta = (tab.getAttribute("aria-label") || "").trim();
                    return tt === "ทั้งหมด" || tt === "All" || ta.startsWith("ทั้งหมด") || ta.includes("แสดงความรู้สึก");
                });

                const inviteBtnsCount = Array.from(d.querySelectorAll('div[role="button"], span[role="button"], button')).filter((b) => {
                    const bt = (b.textContent || "").trim();
                    return bt === "เชิญ" || bt === "เชิญแล้ว" || bt === "Invite" || bt === "Invited";
                }).length;

                if (hasAllReactionTab || inviteBtnsCount >= 1) {
                    return d;
                }
            }
            return null;
        }

        function findReactionCountTriggersOnPage() {
            const found = [];
            const seen = new Set();
            const addCandidate = (el) => {
                if (!el || el.closest("#pakhem-group-helper") || !isElementVisible(el)) return;
                // ข้ามถ้าปุ่มนี้อยู่ในหน้าต่างคนที่แสดงความรู้สึกที่เปิดอยู่แล้ว
                const clickable =
                    el.closest('div[role="button"], span[role="button"], a[role="button"], span[tabindex="0"], div[tabindex="0"]') || el;
                const txt = (clickable.textContent || "").trim();
                const aria = (clickable.getAttribute("aria-label") || "").trim();
                // ห้ามกดปุ่ม "ถูกใจ" ตัวหลัก หรือปุ่ม "แสดงความคิดเห็น" หรือปุ่ม "แชร์" เด็ดขาด
                if (
                    txt === "ถูกใจ" ||
                    txt === "Like" ||
                    txt === "แสดงความคิดเห็น" ||
                    txt === "แชร์" ||
                    aria === "ถูกใจ" ||
                    aria === "Like" ||
                    aria === "แสดงความคิดเห็น" ||
                    aria === "แชร์"
                ) {
                    return;
                }
                if (clickable.getAttribute("data-pkh-opened-react") === "1") return;
                if (!seen.has(clickable)) {
                    seen.add(clickable);
                    found.push(clickable);
                }
            };

            // 1. ค้นหาจากแถบปุ่ม [ถูกใจ] [แสดงความคิดเห็น] ของแต่ละโพสต์ แล้วมองหาตัวเลขยอดไลก์ที่อยู่ด้านบนซ้ายของปุ่ม [ถูกใจ]
            const likeActionBtns = Array.from(
                document.querySelectorAll('div[aria-label="ถูกใจ"][role="button"], div[aria-label="Like"][role="button"]')
            ).filter((b) => !b.closest("#pakhem-group-helper") && isElementVisible(b));

            for (const likeBtn of likeActionBtns) {
                const postContainer =
                    likeBtn.closest('div[role="article"], div[data-pagelet*="FeedUnit"], div[role="dialog"]') ||
                    likeBtn.parentElement?.parentElement?.parentElement?.parentElement;
                if (!postContainer) continue;
                const likeRect = likeBtn.getBoundingClientRect();

                const innerClickables = Array.from(
                    postContainer.querySelectorAll('span[role="toolbar"] div[role="button"], div[role="button"], span[role="button"], span[tabindex="0"]')
                ).filter((el) => isElementVisible(el));

                for (const c of innerClickables) {
                    const cRect = c.getBoundingClientRect();
                    // ต้องอยู่เหนือปุ่ม [ถูกใจ] ไม่เกิน 65px และอยู่ฝั่งซ้ายของโพสต์
                    const isJustAboveLikeBtn =
                        cRect.bottom <= likeRect.top + 8 &&
                        cRect.top >= likeRect.top - 70 &&
                        cRect.left <= likeRect.left + 220;
                    if (!isJustAboveLikeBtn) continue;

                    const cTxt = (c.textContent || "").trim();
                    const cAria = (c.getAttribute("aria-label") || "").trim();
                    if (
                        cAria.includes("แสดงความรู้สึก") ||
                        cAria.includes("ถูกใจ:") ||
                        cAria.includes("รักเลย:") ||
                        cTxt.includes("และคนอื่นๆ") ||
                        /^\d+([.,]\d+)?(\s*(พัน|หมื่น|K|M))?$/.test(cTxt)
                    ) {
                        addCandidate(c);
                    }
                }
            }

            // 2. ค้นหาจาก aria-label ทุกชนิดที่เกี่ยวข้องกับยอดกดถูกใจ/แสดงความรู้สึก
            const ariaEls = Array.from(document.querySelectorAll("[aria-label]"));
            for (const el of ariaEls) {
                if (el.closest("#pakhem-group-helper") || !isElementVisible(el)) continue;
                const aria = (el.getAttribute("aria-label") || "").trim();
                if (
                    aria.includes("ดูว่าใครแสดงความรู้สึก") ||
                    aria.includes("คนที่แสดงความรู้สึก") ||
                    aria.includes("ความรู้สึกทั้งหมด") ||
                    aria.includes("See who reacted") ||
                    aria.includes("All reactions") ||
                    /^(ถูกใจ|รักเลย|ห่วงใย|ว้าว|ฮ่าๆ|เศร้า|โกรธ|Like|Love)\s*[:：]?\s*\d+/i.test(aria)
                ) {
                    addCandidate(el);
                }
            }

            // 3. ค้นหาจากแถบ Toolbar ไอคอน 👍❤️ (span[role="toolbar"])
            const toolbars = Array.from(document.querySelectorAll('span[role="toolbar"], div[role="toolbar"]'));
            for (const tb of toolbars) {
                if (tb.closest("#pakhem-group-helper") || !isElementVisible(tb)) continue;
                const parentRow = tb.parentElement;
                if (parentRow) {
                    const btns = Array.from(parentRow.querySelectorAll('div[role="button"], span[role="button"], span[tabindex="0"]'));
                    for (const b of btns) {
                        const t = (b.textContent || "").trim();
                        if (t && !t.includes("ความคิดเห็น") && !t.includes("แชร์")) {
                            addCandidate(b);
                        }
                    }
                }
            }

            return found;
        }

        async function runInvitePostLikers() {
            if (isInvitingLikers) {
                isInvitingLikers = false;
                if (btnInviteLikers) {
                    btnInviteLikers.textContent = "👍 เชิญคนถูกใจโพสต์ให้ติดตามเพจ (1-คลิก)";
                    btnInviteLikers.style.background = "linear-gradient(135deg, #e65100, #f57c00)";
                }
                showToast("⏹️ หยุดกดเชิญคนถูกใจเรียบร้อยแล้วครับ", "#856404", "#fff3cd");
                return { ok: true, invitedCount: 0, stopped: true };
            }

            // ตรวจว่าอยู่หน้าแชท Messenger หรือไม่ (หน้าแชทไม่มีโพสต์)
            const pth = window.location.pathname || "";
            if (pth.includes("/messages") || pth.includes("/inbox") || window.location.hostname.includes("messenger.com")) {
                showToast(
                    `📌 หน้านี้เป็นหน้าแชท (ไม่มีโพสต์) — <a href="https://www.facebook.com/1307380735783361" target="_blank" style="color:#0d47a1;font-weight:bold;text-decoration:underline;">คลิกที่นี่เพื่อเปิดหน้าเพจป้าเข็ม</a> แล้วกดปุ่มสีส้มนี้ได้เลยครับ!`,
                    "#856404",
                    "#fff3cd"
                );
                return { ok: false, reason: "in_chat_page" };
            }

            isInvitingLikers = true;
            if (btnInviteLikers) {
                btnInviteLikers.textContent = "⏹️ กำลังค้นหาและเชิญ... (กดซ้ำเพื่อหยุด)";
                btnInviteLikers.style.background = "#dc3545";
            }

            // ล้างมาร์กเกอร์เก่าเพื่อให้กดซ้ำได้เสมอ
            document.querySelectorAll('[data-pkh-opened-react="1"]').forEach((el) => el.removeAttribute("data-pkh-opened-react"));

            // 1. ตรวจว่าหน้าต่างรายชื่อคนกดถูกใจเปิดอยู่แล้วหรือไม่ ถ้ายังไม่เปิด ให้ค้นหาและคลิกเปิดให้อัตโนมัติ (พร้อมเลื่อนหน้าจอหาโพสต์ที่มีคนกดไลก์)
            let dialog = findOpenReactionsDialog();
            if (!dialog) {
                showToast("🔍 กำลังค้นหาปุ่มคนกดถูกใจ (👍) บนหน้านี้ให้อัตโนมัติ...", "#004085", "#e8f4fd");
                for (let scrollStep = 0; scrollStep < 5 && isInvitingLikers && !dialog; scrollStep++) {
                    const triggers = findReactionCountTriggersOnPage();
                    for (const trig of triggers) {
                        if (!isInvitingLikers) break;
                        trig.setAttribute("data-pkh-opened-react", "1");
                        try {
                            trig.style.outline = "3px solid #ff5722";
                        } catch (e) {}
                        showToast("⏳ พบโพสต์ที่มีคนกดถูกใจ! กำลังเปิดรายชื่อ...", "#004085", "#e8f4fd");
                        triggerReactClick(trig);

                        for (let w = 0; w < 10; w++) {
                            await new Promise((r) => setTimeout(r, 300));
                            dialog = findOpenReactionsDialog();
                            if (dialog) break;
                        }
                        try {
                            trig.style.outline = "";
                        } catch (e) {}
                        if (dialog) break;
                    }

                    if (!dialog && scrollStep < 4 && isInvitingLikers) {
                        showToast(`🔍 กำลังเลื่อนหน้าจอหาโพสต์ที่มีคนกดถูกใจ (${scrollStep + 1}/4)...`, "#004085", "#e8f4fd");
                        window.scrollBy({ top: 500, behavior: "smooth" });
                        await new Promise((r) => setTimeout(r, 1200));
                    }
                }
            }

            if (!dialog) {
                isInvitingLikers = false;
                if (btnInviteLikers) {
                    btnInviteLikers.textContent = "👍 เชิญคนถูกใจโพสต์ให้ติดตามเพจ (1-คลิก)";
                    btnInviteLikers.style.background = "linear-gradient(135deg, #e65100, #f57c00)";
                }
                showToast(
                    `ℹ️ ไม่พบโพสต์ที่มียอดกดถูกใจในหน้านี้ — <a href="https://www.facebook.com/1307380735783361" target="_blank" style="color:#0d47a1;font-weight:bold;text-decoration:underline;">เปิดหน้าเพจป้าเข็ม</a> หรือคลิกตัวเลข 👍 ใต้โพสต์แล้วกดปุ่มนี้อีกครั้งครับ`,
                    "#856404",
                    "#fff3cd"
                );
                return { ok: false, reason: "no_dialog" };
            }

            let totalInvited = 0;
            let emptyRounds = 0;
            const triedLikerNames = new Set();

            function getLikerRowName(btn) {
                let row = btn;
                const btnTxt = (btn.textContent || "").trim();
                for (let i = 0; i < 7 && row && row !== dialog; i++) {
                    row = row.parentElement;
                    if (!row) break;
                    const rowTxt = (row.innerText || "").replace(btnTxt, "").trim();
                    if (rowTxt.length >= 2) return rowTxt.split(/\r?\n/)[0].trim();
                }
                return "";
            }

            function scrollReactionsDialog(dialogEl) {
                if (!dialogEl) return false;
                let scrolled = false;

                // 1. ค้นหาทุก Container ที่มีแถบเลื่อนแนวตั้ง
                const scrollables = Array.from(dialogEl.querySelectorAll("*")).filter((el) => {
                    if (el.clientHeight < 80) return false;
                    const style = window.getComputedStyle(el);
                    const isScrollStyle = style.overflowY === "auto" || style.overflowY === "scroll";
                    return isScrollStyle || el.scrollHeight > el.clientHeight + 15;
                });

                for (const scroller of scrollables) {
                    const before = scroller.scrollTop;
                    // ขยับสะกิดขึ้นเล็กน้อยแล้วดีดลงล่างสุด (Jiggle Scroll เพื่อกระตุ้น Virtual DOM & GraphQL Fetch ของ Facebook 100%)
                    try {
                        scroller.scrollTop = Math.max(0, scroller.scrollTop - 40);
                    } catch (e) {}
                    scroller.scrollTop = scroller.scrollTop + 650;
                    if (scroller.scrollTop !== before || scroller.scrollHeight > scroller.clientHeight + 20) {
                        scrolled = true;
                        try {
                            scroller.dispatchEvent(new Event("scroll", { bubbles: true }));
                            scroller.dispatchEvent(new WheelEvent("wheel", { deltaY: 800, bubbles: true, cancelable: true }));
                        } catch (e) {}
                    }
                }

                // 2. ดึงรายการล่างสุดในหน้าต่างให้เลื่อนลงมาในจอ
                const allRows = Array.from(
                    dialogEl.querySelectorAll('div[role="button"], span[role="button"], a[role="link"], div[role="listitem"]')
                ).filter((el) => isElementVisible(el));
                if (allRows.length > 0) {
                    try {
                        allRows[allRows.length - 1].scrollIntoView({ behavior: "instant", block: "end" });
                        scrolled = true;
                    } catch (e) {}
                }

                // 3. ยิง Wheel Event ใส่ Dialog โดยตรง
                try {
                    dialogEl.dispatchEvent(new WheelEvent("wheel", { deltaY: 850, bubbles: true, cancelable: true }));
                } catch (e) {}

                return scrolled;
            }

            const maxInvitesPerRun = 500; // เชิญได้สูงสุด 500 คนต่อการกด 1 ครั้ง

            while (isInvitingLikers && totalInvited < maxInvitesPerRun && emptyRounds < 15) {
                dialog = findOpenReactionsDialog();
                if (!dialog) break;

                // ตรวจว่าโดน Facebook ขึ้นหน้าต่างเตือนบล็อกหรือไม่
                const isBlockedModal = document.querySelector('div[role="alertdialog"], div[aria-label*="ถูกจำกัด"], div[aria-label*="บล็อก"]');
                if (isBlockedModal) {
                    isInvitingLikers = false;
                    if (btnInviteLikers) {
                        btnInviteLikers.textContent = "👍 เชิญคนถูกใจโพสต์ให้ติดตามเพจ (1-คลิก)";
                        btnInviteLikers.style.background = "linear-gradient(135deg, #e65100, #f57c00)";
                    }
                    showToast(
                        `⛔ Facebook ขึ้นเตือนจำกัดชั่วคราว — เชิญสำเร็จรวม <b>${totalInvited} คน</b> พักไว้ 2–3 ชม. แล้วค่อยกดใหม่ครับ`,
                        "#721c24",
                        "#f8d7da"
                    );
                    return { ok: false, reason: "facebook_blocked", invitedCount: totalInvited };
                }

                const allButtons = Array.from(dialog.querySelectorAll('div[role="button"], span[role="button"], button')).filter(
                    (b) => isElementVisible(b) && b.getAttribute("aria-disabled") !== "true"
                );

                // คัดเฉพาะปุ่มที่เขียนว่า "เชิญ" หรือ "Invite" เท่านั้น (ไม่กด "เชิญแล้ว" หรือ "เพิ่มเพื่อน")
                const inviteBtns = allButtons.filter((b) => {
                    const txt = (b.textContent || "").trim();
                    const aria = (b.getAttribute("aria-label") || "").trim();
                    const isExactInvite =
                        txt === "เชิญ" ||
                        txt === "Invite" ||
                        aria === "เชิญ" ||
                        aria === "Invite" ||
                        aria.startsWith("เชิญให้กดถูกใจ") ||
                        aria.startsWith("เชิญ ");
                    const isAlreadyInvited =
                        txt.includes("เชิญแล้ว") ||
                        txt.includes("Invited") ||
                        aria.includes("เชิญแล้ว") ||
                        aria.includes("Invited");
                    const personKey = getLikerRowName(b);
                    const alreadyTried = personKey && triedLikerNames.has(personKey);
                    return isExactInvite && !isAlreadyInvited && !alreadyTried;
                });

                // ตรวจว่าติดโหมดโปรไฟล์ส่วนตัว ("เพิ่มเพื่อน") หรือไม่
                if (inviteBtns.length === 0 && totalInvited === 0) {
                    const hasAddFriend = allButtons.some((b) => {
                        const t = (b.textContent || "").trim();
                        return t === "เพิ่มเพื่อน" || t === "Add friend" || t === "Add Friend";
                    });
                    if (hasAddFriend) {
                        isInvitingLikers = false;
                        if (btnInviteLikers) {
                            btnInviteLikers.textContent = "👍 เชิญคนถูกใจโพสต์ให้ติดตามเพจ (1-คลิก)";
                            btnInviteLikers.style.background = "linear-gradient(135deg, #e65100, #f57c00)";
                        }
                        showToast(
                            "⚠️ ตอนนี้อยู่ในโหมดเฟซส่วนตัว (ปุ่มเป็น 'เพิ่มเพื่อน') — กรุณา<b>สลับโปรไฟล์มุมขวาบนเป็นเพจป้าเข็ม</b>ก่อน จะขึ้นปุ่ม 'เชิญ' ครับ!",
                            "#721c24",
                            "#f8d7da"
                        );
                        return { ok: false, reason: "personal_profile_mode" };
                    }
                }

                if (inviteBtns.length > 0) {
                    emptyRounds = 0;
                    for (const btn of inviteBtns) {
                        if (!isInvitingLikers || totalInvited >= maxInvitesPerRun) break;
                        const personKey = getLikerRowName(btn);
                        if (personKey) triedLikerNames.add(personKey);

                        triggerReactClick(btn);
                        totalInvited++;

                        if (btnInviteLikers) {
                            btnInviteLikers.textContent = `⏹️ เชิญแล้ว ${totalInvited} คน... (กดเพื่อหยุด)`;
                        }
                        showToast(`👍 กดเชิญคนถูกใจให้ติดตามเพจแล้ว <b>${totalInvited} คน</b>...`, "#155724", "#d4edda");

                        // พักหายใจสั้นๆ 4 วินาทีทุกๆ 40 คนเพื่อไม่ให้ Facebook มองว่าเป็นสแปม แล้วเดินหน้ากดเชิญต่ออัตโนมัติทันที
                        if (totalInvited % 40 === 0 && totalInvited < maxInvitesPerRun && isInvitingLikers) {
                            for (let restSec = 4; restSec > 0 && isInvitingLikers; restSec--) {
                                showToast(
                                    `⏳ พัก <b>${restSec} วินาที</b> ป้องกัน Facebook บล็อก แล้วลุยเชิญต่ออัตโนมัติ... (เชิญแล้ว ${totalInvited} คน)`,
                                    "#856404",
                                    "#fff3cd"
                                );
                                await new Promise((r) => setTimeout(r, 1000));
                            }
                        } else {
                            // หน่วงเวลาแบบมนุษย์กดจริง (800 - 1,150 มิลลิวินาที)
                            const safeDelay = 800 + Math.floor(Math.random() * 350);
                            await new Promise((r) => setTimeout(r, safeDelay));
                        }
                    }
                } else {
                    emptyRounds++;
                    showToast(
                        `⏳ กำลังเลื่อนหน้าจอลงด้านล่างเพื่อโหลดรายชื่อเพิ่ม (${emptyRounds}/15)... (หรือใช้เมาส์ช่วยรูด Scroll ลงได้จ้า)`,
                        "#004085",
                        "#e8f4fd"
                    );
                }

                // สั่งเลื่อนหน้าต่างเพื่อดึงรายชื่อชุดถัดไป
                scrollReactionsDialog(dialog);
                await new Promise((r) => setTimeout(r, 1300));
            }

            isInvitingLikers = false;
            if (btnInviteLikers) {
                btnInviteLikers.textContent = "👍 เชิญคนถูกใจโพสต์ให้ติดตามเพจ (1-คลิก)";
                btnInviteLikers.style.background = "linear-gradient(135deg, #e65100, #f57c00)";
            }

            if (totalInvited > 0) {
                showToast(`🎉 กดเชิญคนถูกใจโพสต์ให้ติดตามเพจสำเร็จรวม <b>${totalInvited} คน</b> จ้า!`, "#155724", "#d4edda");
            } else {
                showToast(`✅ คนที่กดถูกใจโพสต์นี้ถูกกดเชิญหรือติดตามเพจครบทุกคนแล้วจ้า!`, "#0c5460", "#e8f4fd");
            }
            return { ok: true, invitedCount: totalInvited };
        }

        if (btnInviteLikers) {
            btnInviteLikers.addEventListener("click", runInvitePostLikers);
        }

        window.__PKH_RUN_INVITE_LIKERS__ = runInvitePostLikers;

        // ==============================================================
        // 💬 ระบบตอบคอมเมนต์ลูกค้าในโพสต์กลุ่ม/โพสต์แชร์อัตโนมัติ (Guided Navigator 1-2-3)
        // ==============================================================
        const btnReplyComments = widget.querySelector("#pkh-btn-reply-comments");
        let isReplyingComments = false;

        function buildShortGuidedCommentReply(commentText, commenterName) {
            const cleanName = (commenterName || "").trim();
            const greet = cleanName ? `สวัสดีค่ะคุณ ${cleanName} 🙏🐟` : `สวัสดีค่ะคุณลูกค้า 🙏🐟`;
            const lower = (commentText || "").trim().toLowerCase();

            if (lower === "1" || lower.includes("ชุด 1") || lower.includes("ชุด1") || lower.includes("500") || lower.includes("ครึ่งโล")) {
                return `${greet} รับชุด 1️⃣ (500g / 2-3 ตัวใหญ่) โอน 390.- ส่งฟรี (งดรับ COD) จ้า\n👉 แจ้ง ชื่อ-ที่อยู่-เบอร์โทร ทางแชทเพจคลิก: https://m.me/1307380735783361 ได้เลยจ้า`;
            }
            if (lower === "2" || lower.includes("ชุด 2") || lower.includes("ชุด2") || lower.includes("1 โล") || lower.includes("1โล") || lower.includes("1 กก")) {
                return `${greet} รับชุด 2️⃣ ขายดี (1 กก. / 4-6 ตัวใหญ่) โอน 550.- ส่งฟรี ⭐ (งดรับ COD)\n👉 แจ้ง ชื่อ-ที่อยู่-เบอร์โทร ทางแชทเพจคลิก: https://m.me/1307380735783361 ได้เลยจ้า`;
            }
            if (lower === "3" || lower.includes("ชุด 3") || lower.includes("ชุด3") || lower.includes("2 โล") || lower.includes("2โล") || lower.includes("2 กก")) {
                return `${greet} รับชุด 3️⃣ สุดคุ้ม (2 กก. / 10-14 ตัว) โอน 1,090.- ส่งฟรีรถห้องเย็นจ้า ❄️\n🏦 ธ.กรุงไทย 038-0-25363-1 (นายจีรวัฒน์ พลอาจ)\n👉 ส่งสลิป + ชื่อ-ที่อยู่ ทางแชทเพจคลิก: https://m.me/1307380735783361 ได้เลยจ้า`;
            }
            if (lower.includes("เค็ม") || lower.includes("รสชาติ") || lower.includes("สาบ") || lower.includes("โคลน")) {
                return `${greet} ไม่เค็มจัดและไร้กลิ่นโคลนจ้า เนื้อปลา 97% + เกลือสมุทร 3% (ไร้สารกันบูด 0%)\n1️⃣ 500g (2-3 ตัวใหญ่): โอน 390.- ส่งฟรี (งดรับ COD)\n2️⃣ 1 กก. (4-6 ตัวใหญ่): โอน 550.- ส่งฟรี ⭐ขายดี (งดรับ COD)\n3️⃣ 2 กก. (10-14 ตัว): โอน 1,090.- ส่งฟรีรถห้องเย็น!\n👉 รับชุดไหน พิมพ์เลข 1, 2, 3 หรือทักแชท: https://m.me/1307380735783361 จ้า`;
            }

            return `${greet} ปลาสลิดสุพรรณแท้ ป้าเข็ม (ไซส์จัมโบ้ เนื้อล้วน เค็มน้อย 3%)\n1️⃣ 500g (2-3 ตัวใหญ่): โอน 390.- ส่งฟรี (งดรับ COD)\n2️⃣ 1 กก. (4-6 ตัวใหญ่): โอน 550.- ส่งฟรี ⭐ขายดี (งดรับ COD)\n3️⃣ 2 กก. (10-14 ตัว): โอน 1,090.- ส่งฟรีรถห้องเย็น!\n👉 รับชุดไหน พิมพ์เลข 1, 2, 3 หรือทักแชทเพจ: https://m.me/1307380735783361 จ้า`;
        }

        function getRepliedDomComments() {
            try {
                const raw = localStorage.getItem("pkh_replied_dom_comments_v85");
                return raw ? JSON.parse(raw) : {};
            } catch (e) {
                return {};
            }
        }

        function markDomCommentReplied(sig) {
            try {
                const map = getRepliedDomComments();
                map[sig] = Date.now();
                const keys = Object.keys(map);
                if (keys.length > 300) {
                    delete map[keys[0]];
                }
                localStorage.setItem("pkh_replied_dom_comments_v85", JSON.stringify(map));
            } catch (e) {}
        }

        async function submitCommentComposer(composer) {
            if (!composer) return false;
            composer.focus();
            await new Promise((r) => setTimeout(r, 150));

            // 1. กดปุ่มส่งความคิดเห็น (ไอคอนจรวดกระดาษด้านขวาของช่องคอมเมนต์) ถ้าเปิดใช้งานอยู่
            const rootContainer = composer.closest('div[role="dialog"], div[role="article"], form') || document;
            const submitSelectors = [
                '#focused-state-composer-submit div[role="button"]:not([aria-disabled="true"])',
                'div[aria-label="แสดงความคิดเห็น"][role="button"]:not([aria-disabled="true"])',
                'div[aria-label="ตอบกลับ"][role="button"]:not([aria-disabled="true"])',
                'div[aria-label="ส่ง"][role="button"]:not([aria-disabled="true"])',
                'div[aria-label="Comment"][role="button"]:not([aria-disabled="true"])',
                'div[aria-label="Reply"][role="button"]:not([aria-disabled="true"])'
            ];

            for (const sel of submitSelectors) {
                const btns = Array.from(rootContainer.querySelectorAll(sel)).filter((b) => isElementVisible(b) && !b.closest("#pakhem-group-helper"));
                // กรองปุ่ม "แสดงความคิดเห็น" ที่เป็นปุ่มใต้โพสต์ออก เอาเฉพาะปุ่มส่งที่อยู่ใกล้ช่องพิมพ์คอมเมนต์
                const compRect = composer.getBoundingClientRect();
                const nearBtn = btns.find((b) => {
                    const br = b.getBoundingClientRect();
                    return Math.abs(br.bottom - compRect.bottom) < 95 && br.left >= compRect.left - 20;
                });
                if (nearBtn) {
                    triggerReactClick(nearBtn);
                    await new Promise((r) => setTimeout(r, 350));
                    if ((composer.textContent || "").trim().length === 0) return true;
                }
            }

            // 2. Fallback: จำลองการกดปุ่ม Enter เพื่อส่งคอมเมนต์ใน Lexical Editor
            const enterOpts = {
                key: "Enter",
                code: "Enter",
                keyCode: 13,
                which: 13,
                bubbles: true,
                cancelable: true
            };
            composer.dispatchEvent(new KeyboardEvent("keydown", enterOpts));
            composer.dispatchEvent(new KeyboardEvent("keypress", enterOpts));
            composer.dispatchEvent(new KeyboardEvent("keyup", enterOpts));
            await new Promise((r) => setTimeout(r, 350));
            return (composer.textContent || "").trim().length === 0;
        }

        async function scanAndReplyDomComments(manualTrigger = false) {
            if (isReplyingComments || isInvitingLikers) return 0;
            const pth = window.location.pathname || "";
            if (pth.includes("/messages") || pth.includes("/inbox") || window.location.hostname.includes("messenger.com")) {
                if (manualTrigger) {
                    showToast("ℹ️ ปุ่มนี้ใช้สำหรับตอบคอมเมนต์ใต้โพสต์/กลุ่ม (ในแชทใช้ปุ่ม ⚡ ด้านบนได้เลยจ้า)", "#856404", "#fff3cd");
                }
                return 0;
            }

            // ไม่ทำงานแทรกจังหวะถ้าผู้ใช้กำลังพิมพ์ข้อความเองอยู่
            const activeEl = document.activeElement;
            if (!manualTrigger && activeEl && (activeEl.tagName === "INPUT" || activeEl.tagName === "TEXTAREA" || activeEl.getAttribute("contenteditable") === "true")) {
                return 0;
            }

            isReplyingComments = true;
            let repliedCount = 0;

            try {
                const repliedMap = getRepliedDomComments();
                // ค้นหาปุ่ม "ตอบกลับ" (Reply) ทั้งหมดในหน้าต่างโพสต์ที่เปิดอยู่
                const replyButtons = Array.from(document.querySelectorAll('div[role="button"], span[role="button"]')).filter((el) => {
                    if (el.closest("#pakhem-group-helper") || !isElementVisible(el)) return false;
                    const t = (el.textContent || "").trim();
                    return t === "ตอบกลับ" || t === "Reply";
                });

                for (const replyBtn of replyButtons) {
                    const commentArticle =
                        replyBtn.closest('div[role="article"]') ||
                        replyBtn.parentElement?.parentElement?.parentElement?.parentElement;
                    if (!commentArticle) continue;

                    const fullArticleText = (commentArticle.innerText || commentArticle.textContent || "").trim();
                    // ข้ามทันทีถ้าคอมเมนต์นี้เป็นของร้านเราเอง หรือมีคำตอบของร้านอยู่แล้ว
                    if (
                        fullArticleText.includes("1️⃣ 500g") ||
                        fullArticleText.includes("m.me/1307380735783361") ||
                        fullArticleText.includes("038-0-25363-1") ||
                        fullArticleText.includes("โปรโมชั่นล็อตใหม่") ||
                        fullArticleText.includes("ส่งฟรีรถห้องเย็น")
                    ) {
                        continue;
                    }

                    // ตรวจว่าคอมเมนต์ถัดไปด้านล่างมีคำตอบของป้าเข็มอยู่แล้วหรือไม่
                    const parentListItem = commentArticle.closest("li, div");
                    if (parentListItem && parentListItem.parentElement) {
                        const siblingText = (parentListItem.parentElement.innerText || "").trim();
                        if (siblingText.includes("1️⃣ 500g") && siblingText.includes("m.me/1307380735783361")) {
                            // ถ้าในชุดเธรดย่อยเดียวกันมีคำตอบแล้ว ให้ตรวจละเอียดเฉพาะบล็อกติดกัน
                            const nextEl = commentArticle.nextElementSibling;
                            if (nextEl && (nextEl.innerText || "").includes("1️⃣ 500g")) {
                                continue;
                            }
                        }
                    }

                    // สกัดชื่อผู้คอมเมนต์และข้อความคอมเมนต์
                    const authorEl = commentArticle.querySelector('a[role="link"] span[dir="auto"]');
                    const commenterName = authorEl ? (authorEl.textContent || "").trim() : "";
                    if (commenterName.includes("ป้าเข็ม") || commenterName.includes("ครัวแม่บ้าน")) {
                        continue;
                    }

                    const textCandidates = Array.from(commentArticle.querySelectorAll('div[dir="auto"], span[dir="auto"]'))
                        .map((el) => (el.textContent || "").trim())
                        .filter((t) => {
                            if (!t || t === commenterName) return false;
                            if (t === "ถูกใจ" || t === "ตอบกลับ" || t === "แชร์" || t === "Like" || t === "Reply") return false;
                            if (/^\d+\s*(นาที|ชม\.|ชั่วโมง|วัน|วิ|สัปดาห์)/.test(t)) return false;
                            return true;
                        });

                    const commentText = textCandidates.length > 0 ? textCandidates[textCandidates.length - 1] : "";
                    if (!commentText || commentText.length > 140) continue;

                    const customerKeywords = [
                        "สนใจ", "ราคา", "เท่าไร", "เท่าไหร่", "กี่ตัว", "เค็ม", "รับ", "เอา", "สั่ง",
                        "1", "2", "3", "ครึ่งโล", "โล", "กรัม", "500", "ปลายทาง", "มีไหม", "พร้อมส่ง", "ส่ง"
                    ];
                    const lowerComment = commentText.toLowerCase();
                    const isCustomerIntent = manualTrigger || customerKeywords.some((kw) => lowerComment.includes(kw));
                    if (!isCustomerIntent) continue;

                    const sig = `${commenterName}:${commentText}`.slice(0, 120);
                    if (!manualTrigger && repliedMap[sig]) continue;

                    showToast(`💬 พบคอมเมนต์ <b>"${commentText}"</b> (${commenterName || "ลูกค้า"}) กำลังตอบกลับ...`, "#004085", "#e8f4fd");

                    // 1. กดปุ่ม "ถูกใจ" คอมเมนต์ลูกค้า
                    const likeBtnsInComment = Array.from(commentArticle.querySelectorAll('div[role="button"], span[role="button"]')).filter(
                        (b) => (b.textContent || "").trim() === "ถูกใจ" || (b.textContent || "").trim() === "Like"
                    );
                    if (likeBtnsInComment.length > 0) {
                        triggerReactClick(likeBtnsInComment[0]);
                        await new Promise((r) => setTimeout(r, 250));
                    }

                    // 2. กดปุ่ม "ตอบกลับ" เพื่อเปิดช่องพิมพ์ตอบกลับใต้คอมเมนต์ลูกค้า
                    triggerReactClick(replyBtn);
                    await new Promise((r) => setTimeout(r, 500));

                    // 3. ค้นหากล่องพิมพ์ความคิดเห็นที่เพิ่งเปิดขึ้นมา (หรือกล่องแสดงความคิดเห็นด้านล่างของหน้าต่างโพสต์)
                    const scopeRoot = commentArticle.closest('div[role="dialog"]') || document;
                    const commentBoxes = Array.from(
                        scopeRoot.querySelectorAll('div[contenteditable="true"][role="textbox"], div[data-lexical-editor="true"][contenteditable="true"]')
                    ).filter((el) => !el.closest("#pakhem-group-helper") && isElementVisible(el));

                    // ให้ความสำคัญกับกล่องที่ระบุว่า "ตอบกลับ..." ก่อน ถ้าไม่มีให้ใช้กล่อง "แสดงความคิดเห็น..." ล่างสุด
                    let targetBox = commentBoxes.find((el) => {
                        const aria = ((el.getAttribute("aria-label") || "") + " " + (el.getAttribute("aria-placeholder") || "")).toLowerCase();
                        return aria.includes("ตอบกลับ") || aria.includes("reply");
                    });
                    if (!targetBox && commentBoxes.length > 0) {
                        targetBox = commentBoxes[commentBoxes.length - 1];
                    }

                    if (!targetBox) continue;

                    const replyMsg = buildShortGuidedCommentReply(commentText, commenterName);
                    const inserted = await insertTextIntoEditor(targetBox, replyMsg);
                    if (inserted) {
                        await new Promise((r) => setTimeout(r, 300));
                        await submitCommentComposer(targetBox);
                        markDomCommentReplied(sig);
                        repliedCount++;
                        showToast(`✅ ตอบคอมเมนต์ <b>คุณ${commenterName || "ลูกค้า"}</b> ด้วยตัวนำทาง 1-2-3 สำเร็จ!`, "#155724", "#d4edda");
                        await new Promise((r) => setTimeout(r, 900));
                    }
                }

                if (manualTrigger && repliedCount === 0) {
                    // หากผู้ใช้กดปุ่มเองและมีช่องคอมเมนต์เปิดอยู่ด้านล่าง ให้วางข้อความตัวนำทาง 1-2-3 ลงในช่องคอมเมนต์ทันทีแล้วกดส่ง!
                    const fallbackBox = findMessengerComposer();
                    if (fallbackBox) {
                        const fallbackMsg = buildShortGuidedCommentReply("สนใจ", "");
                        const ok = await insertTextIntoEditor(fallbackBox, fallbackMsg);
                        if (ok) {
                            await new Promise((r) => setTimeout(r, 250));
                            await submitCommentComposer(fallbackBox);
                            repliedCount++;
                            showToast(`✅ ส่งตัวนำทาง 1-2-3 ลงช่องความคิดเห็นเรียบร้อยจ้า!`, "#155724", "#d4edda");
                        }
                    } else {
                        showToast(`ℹ️ ยังไม่พบคอมเมนต์ใหม่ที่ยังไม่ได้ตอบในหน้าต่างนี้จ้า`, "#856404", "#fff3cd");
                    }
                }
            } catch (e) {}

            isReplyingComments = false;
            return repliedCount;
        }

        if (btnReplyComments) {
            btnReplyComments.addEventListener("click", () => scanAndReplyDomComments(true));
        }

        // [ปิดการตอบคอมเมนต์อัตโนมัติจากเบราว์เซอร์] เพื่อป้องกันการตอบซ้ำซ้อนกับบอทหลัก

        // สแกนเติมชื่อลูกค้าอัตโนมัติแบบนุ่มนวลเมื่อเปลี่ยนหน้าแชท (เฉพาะกรณีที่ช่องกรอกยังว่างอยู่ ไม่แย่งเมาส์ ไม่เปลี่ยนหน้าเว็บ!)
        let lastUrlPath = window.location.href;
        setInterval(() => {
            if (window.location.href !== lastUrlPath) {
                lastUrlPath = window.location.href;
                const isEditing =
                    document.activeElement === ordNameInput ||
                    document.activeElement === ordPhoneInput ||
                    document.activeElement === ordAddrInput;
                if (!isEditing && (!ordPhoneInput || !ordPhoneInput.value.trim())) {
                    populateFormFromChat(false);
                }
            }
        }, 1800);
    }

    // ==============================================================
    // 📡 รับคำสั่งจาก Popup (Message Passing)
    // ==============================================================
    if (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.onMessage) {
        chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
            if (!request || !request.action) return false;

            if (request.action === "EXTRACT_CHAT_ORDER") {
                const info = extractOrderFromChat();
                // อัปเดตลงช่องบนหน้าเว็บด้วยถ้ามี
                const ordNameInput = document.querySelector("#pkh-ord-name");
                const ordPhoneInput = document.querySelector("#pkh-ord-phone");
                const ordAddrInput = document.querySelector("#pkh-ord-addr");
                const ordPkgSelect = document.querySelector("#pkh-ord-pkg");
                if (ordNameInput && info.customerName) ordNameInput.value = info.customerName;
                if (ordPhoneInput && info.phone) ordPhoneInput.value = info.phone;
                if (ordAddrInput && info.address) ordAddrInput.value = info.address;
                if (ordPkgSelect && info.pkgValue) ordPkgSelect.value = info.pkgValue;
                sendResponse({ ok: true, data: info });
                return true;
            }

            if (request.action === "INSERT_CHAT_TEXT") {
                const text = request.text || "";
                const autoSend = !!request.autoSend;
                const composer = findMessengerComposer();
                if (!composer) {
                    sendResponse({ ok: false, reason: "no_composer" });
                    return true;
                }
                insertTextIntoEditor(composer, text).then(async (inserted) => {
                    if (inserted && autoSend) {
                        await new Promise((r) => setTimeout(r, 250));
                        try {
                            const sendBtn = document.querySelector(
                                'div[aria-label="กด Enter เพื่อส่ง"][role="button"], div[aria-label="Press enter to send"][role="button"], div[aria-label="ส่ง"][role="button"], div[aria-label="Send"][role="button"]'
                            );
                            if (sendBtn) sendBtn.click();
                        } catch (e) {}
                    }
                    sendResponse({ ok: inserted });
                });
                return true;
            }

            if (request.action === "INVITE_POST_LIKERS") {
                if (typeof window.__PKH_RUN_INVITE_LIKERS__ === "function") {
                    window.__PKH_RUN_INVITE_LIKERS__().then((res) => sendResponse(res));
                } else {
                    sendResponse({ ok: false, reason: "not_ready" });
                }
                return true;
            }

            return false;
        });
    }

    function init() {
        if (document.body) {
            createWidget();
            setTimeout(prefetchImageBlobs, 1200);
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }

    // ตรวจสอบเฉพาะกรณี Facebook ลบ DOM ตอนสลับหน้า SPA (ไม่สั่งคลิกหรือเปลี่ยนหน้าใดๆ)
    setInterval(() => {
        if (document.body && !document.getElementById("pakhem-group-helper")) {
            createWidget();
        }
    }, 3000);
})();

