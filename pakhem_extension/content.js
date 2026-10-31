(function() {
    'use strict';

    // แคปชั่นทองคำ 3 บรรทัด (สำหรับโพสต์หลัก)
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

    const TARGET_GROUPS = [
        { name: "--- 🛍️ เลือกกลุ่มเป้าหมาย / ค้นหากลุ่มทันที ---", url: "" },
        { name: "📋 ⭐ 1. เปิดดู 'กลุ่มที่คุณเป็นสมาชิกแล้วทั้งหมด'", url: "https://www.facebook.com/groups/joins/" },
        { name: "🛍️ 2. ตลาดขายส่ง-ปลีก อาหารแห้ง แดดเดียว", url: "https://www.facebook.com/groups/203180857683381" },
        { name: "🛍️ 3. ตลาดนัดคนสุขสำราญ (ซื้อขายอาหาร)", url: "https://www.facebook.com/groups/562879874340349" },
        { name: "🛍️ 4. ตลาดนัด อาหารอร่อย (ขายของกิน)", url: "https://www.facebook.com/groups/1585596445047346" },
        { name: "🔍 5. ค้นหากลุ่ม 'อาหารแห้ง แดดเดียว'", url: "https://www.facebook.com/search/groups/?q=%E0%B8%AD%E0%B8%B2%E0%B8%AB%E0%B8%B2%E0%B8%A3%E0%B9%81%E0%B8%AB%E0%B9%89%E0%B8%87+%E0%B9%81%E0%B8%94%E0%B8%94%E0%B9%80%E0%B8%94%E0%B8%B5%E0%B8%A2%E0%B8%A7" },
        { name: "🔍 6. ค้นหากลุ่ม 'ซื้อขายอาหารพร้อมส่ง'", url: "https://www.facebook.com/search/groups/?q=%E0%B8%8B%E0%B8%B7%E0%B9%89%E0%B8%AD%E0%B8%82%E0%B8%B2%E0%B8%A2%E0%B8%AD%E0%B8%B2%E0%B8%AB%E0%B8%B2%E0%B8%A3%E0%B8%9E%E0%B8%A3%E0%B9%89%E0%B8%AD%E0%B8%A1%E0%B8%AA%E0%B9%88%E0%B8%87" },
        { name: "🔍 7. ค้นหากลุ่ม 'ตลาดขายส่งอาหาร'", url: "https://www.facebook.com/search/groups/?q=%E0%B8%95%E0%B8%A5%E0%B8%B2%E0%B8%94%E0%B8%82%E0%B8%B2%E0%B8%A2%E0%B8%AA%E0%B9%88%E0%B8%87%E0%B8%AD%E0%B8%B2%E0%B8%AB%E0%B8%B2%E0%B8%A3" }
    ];

    let currentCaptionIndex = 0;
    let cachedPricePngBlob = null;
    let cachedPriceFile = null;
    let cachedFriedPngBlob = null;

    // โหลดรูปภาพเตรียมไว้ล่วงหน้าทันที
    async function prefetchImageBlobs() {
        try {
            const res = await fetch(IMAGES.price, { mode: 'cors' });
            const rawBlob = await res.blob();
            cachedPriceFile = new File([rawBlob], "pakhem_fish_price.jpg", { type: "image/jpeg" });
            cachedPricePngBlob = await convertBlobToPng(rawBlob);
        } catch(e) {}

        try {
            const res2 = await fetch(IMAGES.fried, { mode: 'cors' });
            const rawBlob2 = await res2.blob();
            cachedFriedPngBlob = await convertBlobToPng(rawBlob2);
        } catch(e) {}
    }

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

    async function copyPngBlobToClipboard(pngBlob) {
        if (!pngBlob) return false;
        try {
            if (navigator.clipboard && navigator.clipboard.write) {
                await navigator.clipboard.write([
                    new ClipboardItem({ "image/png": pngBlob })
                ]);
                return true;
            }
        } catch(e) {}
        return false;
    }

    // ==============================================================
    // 🔍 ระบบตรวจจับสถานะกลุ่ม (Group Status & Membership Detector)
    // ==============================================================
    function getActiveProfileName() {
        // ดึงชื่อโปรไฟล์/เพจที่กำลังใช้งานอยู่จริง
        const profileLink = document.querySelector('div[data-pagelet="GroupInlineComposer"] a[aria-label*="โปรไฟล์ของ"], div[data-pagelet="GroupInlineComposer"] a[aria-label*="profile"]');
        if (profileLink) {
            const label = profileLink.getAttribute('aria-label') || '';
            const name = label.replace(/^โปรไฟล์ของ\s*/, '').replace(/'s profile$/, '').trim();
            if (name) return name;
        }
        const topProfile = document.querySelector('div[aria-label="โปรไฟล์ของคุณ"], div[aria-label="Your profile"]');
        if (topProfile && topProfile.textContent.trim()) {
            return topProfile.textContent.trim();
        }
        return "ป้าเข็ม ปลาสลิดแดดเดียวสุพรรณแท้";
    }

        // ==============================================================
    // ⚡ ระบบค้นหา Element ด้วย Native XPath (High-Performance DOM Evaluator)
    // ==============================================================
    function getElementByXPath(xpath, context = document) {
        try {
            const result = document.evaluate(
                xpath,
                context,
                null,
                XPathResult.FIRST_ORDERED_NODE_TYPE,
                null
            );
            return result.singleNodeValue;
        } catch (e) {
            return null;
        }
    }

    function getAllElementsByXPath(xpath, context = document) {
        try {
            const result = document.evaluate(
                xpath,
                context,
                null,
                XPathResult.ORDERED_NODE_SNAPSHOT_TYPE,
                null
            );
            return Array.from({ length: result.snapshotLength }, (_, i) => result.snapshotItem(i));
        } catch (e) {
            return [];
        }
    }

function checkGroupMembership() {
        if (window.location.pathname.includes('/groups/joins')) {
            return {
                isGroup: false,
                name: "กลุ่มที่คุณเข้าร่วมแล้วทั้งหมด",
                status: "non_group",
                canPost: false,
                profileName: getActiveProfileName(),
                badgeText: "📋 เลือกคลิกกลุ่มที่ต้องการโพสต์",
                badgeBg: "#cce5ff",
                badgeColor: "#004085"
            };
        }

        const isGroupUrl = window.location.pathname.includes('/groups/');
        if (!isGroupUrl) {
            return {
                isGroup: false,
                name: "ไม่ใช่หน้ากลุ่ม Facebook",
                status: "non_group",
                canPost: false,
                profileName: getActiveProfileName(),
                badgeText: "⚠️ ไม่อยู่ในกลุ่ม",
                badgeBg: "#f8d7da",
                badgeColor: "#721c24"
            };
        }

        // 1. ดึงชื่อกลุ่มจาก document.title (แม่นยำที่สุดบน Facebook SPA)
        let groupName = "";
        try {
            let title = document.title || "";
            title = title.replace(/^\(\d+\+?\)\s*/, '');
            title = title.replace(/\s*[\|\-]\s*Facebook.*$/i, '').trim();
            if (title && title !== "Facebook") {
                groupName = title;
            }
        } catch(e) {}

        if (!groupName) {
            const h1 = document.querySelector('h1, div[data-pagelet="GroupActions"] h1');
            groupName = h1 ? h1.textContent.trim() : "กลุ่ม Facebook";
        }
        if (groupName.length > 26) groupName = groupName.substring(0, 26) + "...";

        // 2. ตรวจสอบความสามารถในการโพสต์ (GroupInlineComposer มีอยู่จริงหรือไม่)
        const inlineComposer = document.querySelector('div[data-pagelet="GroupInlineComposer"]');
        const hasComposer = !!inlineComposer;

        // 1. ดึง ID ของกลุ่มปัจจุบันเพื่อแยกแยะกลุ่มจริงออกจากกล่องแนะนำ
        const currentPath = window.location.pathname;
        const currentGroupMatch = currentPath.match(/\/groups\/([^\/?#]+)/);
        const currentGroupId = currentGroupMatch ? currentGroupMatch[1] : '';

        // ฟังก์ชันคัดกรองปุ่ม: ข้ามปุ่มที่อยู่ในโซนแนะนำ "ค้นพบกลุ่มเพิ่มเติม" หรือการ์ดกลุ่มอื่น
        function isInsideSuggestedGroups(element) {
            if (!element) return false;
            if (element.closest('div[data-pagelet*="Discover"], div[data-pagelet*="Recommendation"], div[aria-label*="ค้นพบกลุ่มเพิ่มเติม"], div[aria-label*="Discover groups"], div[aria-label*="กลุ่มที่คุณอาจสนใจ"]')) {
                return true;
            }
            let parent = element.parentElement;
            for (let i = 0; i < 8 && parent; i++) {
                if (parent.matches && parent.matches('div[role="feed"], div[data-pagelet="GroupInlineComposer"], div[data-pagelet="GroupActions"]')) {
                    break;
                }
                const text = parent.innerText || parent.textContent || '';
                if (text.includes('ค้นพบกลุ่มเพิ่มเติม') || text.includes('Discover groups') || text.includes('กลุ่มที่คุณอาจสนใจ')) {
                    return true;
                }
                const otherGroupLink = parent.querySelector('a[href*="/groups/"]');
                if (otherGroupLink) {
                    const href = otherGroupLink.getAttribute('href') || '';
                    if (currentGroupId && href.includes('/groups/') && !href.includes(currentGroupId)) {
                        return true;
                    }
                }
                parent = parent.parentElement;
            }
            return false;
        }

        // 2.5 ⚡ ค้นหาด้วย Native XPath ความเร็วสูง (XPath Fast Path)
        let joinBtn = null;
        let pendingBtn = null;
        let joinedBtn = null;
        let inviteBtn = null;

        const xpJoined = getElementByXPath('//div[@role="button" and (contains(., "เข้าร่วมแล้ว") or contains(., "เป็นสมาชิกแล้ว"))] | //a[@role="button" and contains(., "เข้าร่วมแล้ว")]');
        if (xpJoined && !isInsideSuggestedGroups(xpJoined)) joinedBtn = xpJoined;

        const xpPending = getElementByXPath('//div[@role="button" and (contains(., "ยกเลิกคำขอ") or contains(., "รอดำเนินการ"))]');
        if (xpPending && !isInsideSuggestedGroups(xpPending)) pendingBtn = xpPending;

        const xpJoin = getElementByXPath('//div[@role="button" and (contains(., "เข้าร่วมกลุ่ม") or contains(., "ขอเข้าร่วม"))]');
        if (xpJoin && !isInsideSuggestedGroups(xpJoin)) joinBtn = xpJoin;

        const xpInvite = getElementByXPath('//div[@role="button" and (contains(., "เชิญ") or contains(., "Invite"))]');
        if (xpInvite && !isInsideSuggestedGroups(xpInvite)) inviteBtn = xpInvite;

        // 3. สแกนปุ่มและข้อความทั้งหมดในโครงสร้างกลุ่ม (Deep Fallback Scan)
        const candidates = Array.from(document.querySelectorAll('div[role="button"], a[role="button"], span[dir="auto"], span, div[tabindex="0"]'));

        // ตัวแปรถูกประกาศใน XPath Fast Path แล้ว

        for (const el of candidates) {
            if (el.closest('[role="article"]') || el.closest('form')) continue;
            // ข้ามปุ่มที่อยู่ในกล่องแนะนำกลุ่มอื่นเด็ดขาด!
            if (isInsideSuggestedGroups(el)) continue;

            const aria = (el.getAttribute("aria-label") || "").trim();
            const text = (el.textContent || "").trim();
            const combined = (aria + " " + text).toLowerCase().replace(/[\s\-_]/g, '');

            // สมาชิกแล้ว
            if (combined.includes("เข้าร่วมแล้ว") || combined.includes("เป็นสมาชิกแล้ว") || combined === "joined") {
                joinedBtn = el.closest('div[role="button"]') || el;
            }

            // ปุ่มเชิญเพื่อน (มีเฉพาะสมาชิกกลุ่มเท่านั้น)
            if (combined.includes("เชิญ") || combined.includes("invite")) {
                inviteBtn = el.closest('div[role="button"]') || el;
            }

            // คำขอรอดำเนินการ
            if (combined.includes("ยกเลิกคำขอ") || combined.includes("cancelrequest") || combined.includes("รอดำเนินการ") || combined.includes("pending")) {
                pendingBtn = el.closest('div[role="button"]') || el;
            }

            // ขอเข้าร่วมกลุ่ม
            if (combined.includes("เข้าร่วมกลุ่ม") || combined.includes("joingroup") || combined.includes("ขอเข้าร่วม")) {
                joinBtn = el.closest('div[role="button"]') || el;
            }
        }

        const pageText = document.body ? (document.body.innerText || "") : "";
        const mustJoinNotice = pageText.includes("เข้าร่วมกลุ่มนี้เพื่อโพสต์และแสดงความคิดเห็น") ||
                               pageText.includes("คุณต้องเป็นสมาชิกของกลุ่มนี้จึงจะโพสต์ได้");

        const profileName = getActiveProfileName();

        // 1. ตรวจสอบปุ่ม "เข้าร่วมแล้ว" (Joined) เป็นอันดับแรก (Priority สูงสุด)
        // เพราะถ้า Facebook แสดงปุ่ม "เข้าร่วมแล้ว" แปลว่าผู้ใช้เป็นสมาชิกของกลุ่มนี้แน่นอน 100%!
        if (joinedBtn) {
            return {
                isGroup: true,
                name: groupName,
                status: "member",
                canPost: true,
                profileName: profileName,
                badgeText: "🟢 เป็นสมาชิกแล้ว (พร้อมโพสต์)",
                badgeBg: "#d4edda",
                badgeColor: "#155724"
            };
        }

        // 2. ตรวจสอบคำขอรอดำเนินการ (ส่งคำขอไปแล้ว รอแอดมินอนุมัติ)
        if (pendingBtn) {
            return {
                isGroup: true,
                name: groupName,
                status: "pending",
                canPost: false,
                profileName: profileName,
                badgeText: "⏳ ส่งคำขอแล้ว (รอแอดมินอนุมัติ)",
                badgeBg: "#fff3cd",
                badgeColor: "#856404"
            };
        }

        // 3. ตรวจสอบปุ่ม "เข้าร่วมกลุ่ม" ของกลุ่มปัจจุบัน
        // (กรณีไม่ใช่สมาชิก แม้เป็นกลุ่มสาธารณะที่มีกล่องโพสต์ แต่หากไม่มีปุ่ม 'เข้าร่วมแล้ว' และมีปุ่ม 'เข้าร่วมกลุ่ม')
        if (joinBtn || mustJoinNotice) {
            return {
                isGroup: true,
                name: groupName,
                status: "not_member",
                canPost: false,
                joinElement: joinBtn,
                profileName: profileName,
                badgeText: "🔴 ยังไม่เป็นสมาชิก (คลิกขอเข้ากลุ่ม)",
                badgeBg: "#f8d7da",
                badgeColor: "#721c24"
            };
        }

        // 4. เป็นสมาชิกผ่านกล่องโพสต์ หรือปุ่มเชิญ
        if (hasComposer || inviteBtn) {
            return {
                isGroup: true,
                name: groupName,
                status: "member",
                canPost: true,
                profileName: profileName,
                badgeText: "🟢 เป็นสมาชิกแล้ว (พร้อมโพสต์)",
                badgeBg: "#d4edda",
                badgeColor: "#155724"
            };
        }

        return {
            isGroup: true,
            name: groupName,
            status: "unknown",
            canPost: true,
            profileName: profileName,
            badgeText: "🔍 กำลังตรวจสถานะ (พร้อมโพสต์)",
            badgeBg: "#e8f4fd",
            badgeColor: "#0c5460"
        };
    }


    // ==============================================================
    // 📝 ระบบตอบคำถามขอเข้ากลุ่มอัตโนมัติ (Auto-Answer Group Questions)
    // ==============================================================
    function autoAnswerGroupQuestions() {
        const dialog = document.querySelector('div[role="dialog"]');
        if (!dialog) {
            return { success: false, msg: "ไม่พบหน้าต่างคำถามบนหน้าจอครับ (กดปุ่ม 'เข้าร่วมกลุ่ม' ก่อน)" };
        }

        let answeredCount = 0;

        // 1. ติ๊กเครื่องหมายถูกยอมรับกฎกลุ่มทั้งหมด
        const checkboxes = Array.from(dialog.querySelectorAll('input[type="checkbox"], div[role="checkbox"]'));
        for (const cb of checkboxes) {
            if (cb.tagName === 'INPUT' && !cb.checked) {
                cb.click();
                answeredCount++;
            } else if (cb.getAttribute('aria-checked') !== 'true') {
                cb.click();
                answeredCount++;
            }
        }

        // 2. เติมคำตอบลงในช่องเขียน (Textarea, Input)
        const inputs = Array.from(dialog.querySelectorAll('textarea, input[type="text"], div[contenteditable="true"]'));
        for (const input of inputs) {
            const parent = input.closest('div[role="listitem"], div') || input.parentElement;
            const qText = parent ? (parent.innerText || '').toLowerCase() : '';

            let answer = "ขออนุญาตเข้าร่วมกลุ่มเพื่อแลกเปลี่ยนและจำหน่ายสินค้าคุณภาพดีตามกฎระเบียบของกลุ่มครับ";
            if (qText.includes("ขาย") || qText.includes("สินค้า") || qText.includes("ธุรกิจ") || qText.includes("sell") || qText.includes("product")) {
                answer = "จำหน่ายปลาสลิดสุพรรณแดดเดียวแท้ ป้าเข็ม คัดพิเศษ (ไซส์จัมโบ้ สะอาด ไร้สาร เค็มน้อย 3%)";
            } else if (qText.includes("กฎ") || qText.includes("rule") || qText.includes("ยอมรับ") || qText.includes("accept")) {
                answer = "ยอมรับและพร้อมปฏิบัติตามกฎระเบียบของกลุ่มทุกประการครับ";
            } else if (qText.includes("จังหวัด") || qText.includes("ที่อยู่") || qText.includes("อยู่อำเภอ") || qText.includes("location") || qText.includes("where")) {
                answer = "อยุธยา / สุพรรณบุรี (บริการจัดส่งด่วนห้องเย็น 1-2 วันถึงบ้านทั่วไทย)";
            }

            if (input.tagName === "DIV" && input.getAttribute("contenteditable") === "true") {
                input.focus();
                document.execCommand("insertText", false, answer);
            } else {
                input.value = answer;
                input.dispatchEvent(new Event("input", { bubbles: true }));
                input.dispatchEvent(new Event("change", { bubbles: true }));
            }
            answeredCount++;
        }

        // 3. เลื่อนไปยังปุ่มส่ง (Submit)
        const submitBtn = Array.from(dialog.querySelectorAll('div[role="button"]')).find(b => {
            const t = (b.textContent || '').trim();
            return t === "ส่ง" || t === "Submit" || t.includes("ส่งคำขอ");
        });

        if (submitBtn) {
            submitBtn.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }

        return {
            success: answeredCount > 0,
            count: answeredCount,
            submitBtn: submitBtn
        };
    }

    // ==============================================================
    // 🔍 เรดาร์กวาดรายชื่อกลุ่มบนหน้าค้นหา (Group Harvester & CSV Export)
    // ==============================================================
    function scanAndExportGroupsToCsv() {
        const links = Array.from(document.querySelectorAll('a[href*="/groups/"]'));
        const groups = [];
        const seenUrls = new Set();

        for (const a of links) {
            let href = (a.href || '').split('?')[0].split('/posts')[0];
            if (!href.includes('/groups/') || href.endsWith('/groups/') || href.includes('/joins')) continue;
            if (seenUrls.has(href)) continue;

            const card = a.closest('div[role="feed"] > div, div[role="article"], div.x1n2onr6') || a.parentElement;
            const text = card ? (card.innerText || '') : '';
            const title = a.textContent ? a.textContent.trim() : '';

            if (title.length < 3 || title.includes('โพสต์') || title.includes('สมาชิก') || title === "Facebook") continue;

            seenUrls.add(href);

            const isMember = text.includes('เข้าร่วมแล้ว') || text.includes('Joined');
            const isPending = text.includes('ยกเลิกคำขอ') || text.includes('รอดำเนินการ') || text.includes('Pending');
            const status = isMember ? 'เป็นสมาชิกแล้ว' : (isPending ? 'รออนุมัติ' : 'ยังไม่เป็นสมาชิก');

            groups.push({
                title: title.replace(/"/g, '""'),
                url: href,
                status: status
            });
        }

        if (groups.length === 0) {
            return { count: 0 };
        }

        // สร้าง CSV พร้อม BOM (UTF-8) สำหรับเปิดใน Excel ภาษาไทยไม่เพี้ยน
        let csvContent = "\ufeff\"ชื่อกลุ่ม\",\"สถานะสมาชิก\",\"ลิงก์กลุ่ม Facebook\"\n";
        groups.forEach(g => {
            csvContent += `\"${g.title}\",\"${g.status}\",\"${g.url}\"\n`;
        });

        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.setAttribute("href", url);
        link.setAttribute("download", `facebook_groups_pakhem_${new Date().toISOString().slice(0,10)}.csv`);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);

        return { count: groups.length, groups: groups };
    }

    // ฟังก์ชันค้นหากล่อง "สร้างโพสต์"
    function findCreatePostTrigger() {
        const inlineComposer = document.querySelector('div[data-pagelet="GroupInlineComposer"] div[role="button"][tabindex="0"]') ||
                               document.querySelector('div[data-pagelet="GroupInlineComposer"] div[role="button"]') ||
                               document.querySelector('div[data-pagelet*="Composer"] div[role="button"]');
        if (inlineComposer) return inlineComposer;

        // ⚡ XPath Ultra-Fast Composer Detection
        const xpathComposer = getElementByXPath(
            '//div[@data-pagelet="GroupInlineComposer"]//div[@role="button"] | //div[contains(@data-pagelet, "Composer")]//div[@role="button"] | //div[@role="button" and (contains(., "เขียนอะไร") or contains(., "สร้างโพสต์") or contains(., "คุณกำลังคิดอะไรอยู่"))]'
        );
        if (xpathComposer && !xpathComposer.closest('[role="article"]')) return xpathComposer;

        const allCandidates = Array.from(document.querySelectorAll('span, div[role="button"], div[tabindex="0"]'));
        for (const el of allCandidates) {
            if (el.closest('[role="article"]') || el.closest('form')) continue;
            const rawText = el.textContent || '';
            const cleanText = rawText.replace(/[\.\s\u2026?？_—\-]/g, '').toLowerCase();

            if (cleanText.includes('เขียนอะไร') ||
                cleanText.includes('สร้างโพสต์') ||
                cleanText.includes('คุณกำลังคิดอะไรอยู่') ||
                cleanText.includes('writesomething') ||
                cleanText.includes('createapublicpost')) {
                return el.closest('div[role="button"]') || el.parentElement || el;
            }
        }
        return null;
    }

    function simulateFullClick(element) {
        if (!element) return;
        element.scrollIntoView({ behavior: 'smooth', block: 'center' });
        element.focus();
        element.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }));
        element.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true }));
        element.click();
    }

    async function insertTextIntoEditor(composer, text) {
        composer.focus();
        await new Promise(r => setTimeout(r, 100));

        try {
            const sel = window.getSelection();
            sel.removeAllRanges();
            const range = document.createRange();
            range.selectNodeContents(composer);
            range.collapse(false);
            sel.addRange(range);
            document.execCommand("insertText", false, text);
        } catch(e) {}

        await new Promise(r => setTimeout(r, 200));

        if (!composer.textContent || !composer.textContent.includes("ปลาสลิด")) {
            try {
                const inputEvt = new InputEvent('beforeinput', {
                    bubbles: true,
                    cancelable: true,
                    inputType: 'insertText',
                    data: text
                });
                composer.dispatchEvent(inputEvt);
            } catch(e) {}
        }
    }

    function isImagePreviewPresent(dialog) {
        if (!dialog) return false;
        const imgThumb = dialog.querySelector('img[src^="blob:"], div[aria-label*="เอาสื่อออก"], div[aria-label*="Remove"], div[aria-label*="แก้ไขรูปภาพ"], div[aria-label*="Edit photo"], img[src*="fbcdn.net"]');
        return !!imgThumb;
    }

    
    // ==============================================================
    // 💬 ระบบผู้ช่วยปิดการขายใน Facebook Messenger (Inbox Sales Assistant - v4.8)
    // ==============================================================
    const MESSENGER_REPLIES = {
        price: `ปลาสลิดสุพรรณแดดเดียวแท้ ป้าเข็ม คัดพิเศษ (ไซส์จัมโบ้ เนื้อแน่นหนาฟู มันแทรก เค็มน้อย 3% ไร้ชูรส) 🐟✨
📦 ราคามาตรฐานส่งฟรีถึงหน้าบ้าน:
• ชุด 500 กรัม (3-4 ตัว): โอน 390.- (เก็บปลายทาง 410.-)
• ชุด 1 กิโลกรัม (5-7 ตัว): โอน 550.- (เก็บปลายทาง 570.-) ⭐ ขายดีที่สุด!
• ชุด 2 กิโลกรัม (10-14 ตัว): โอน 1,090.- (ส่งฟรีรถห้องเย็นควบคุมอุณหภูมิ!)
🚚 แช่เยือกแข็ง -18°C บรรจุซองฟอยล์ ส่งถึงใน 1-2 วัน สินค้าเสียหายเคลมฟรี 100% ค่ะ 💕
👉 คุณลูกค้ารับชุดไหนดีคะ แจ้งชื่อ-ที่อยู่-เบอร์โทร ให้แอดมินเปิดบิลส่งได้เลยจ้า`,

        bank: `🏦 ยอดโอนชำระเงินส่งฟรี ร้านป้าเข็ม:
• ธนาคารกรุงไทย (Krungthai)
• เลขที่บัญชี: 038-0-25363-1
• ชื่อบัญชี: นายจีรวัฒน์ พลอาจ
โอนแล้วส่งสลิปพร้อมแจ้งชื่อ-ที่อยู่-เบอร์โทรผู้รับไว้ในแชทนี้ได้เลยนะคะ แอดมินรีบแพ็กจัดส่งสดใหม่ให้ทันทีจ้า 🙏✨`,

        shipping: `❄️ มาตรฐานการผลิตและการจัดส่ง ร้านป้าเข็ม:
1. ตากแดดธรรมชาติ 1 แดด เนื้อปลาหอมหนาฟู
2. ซีลสูญญากาศและแช่เยือกแข็ง ≤ -18°C อย่างน้อย 12 ชม.
3. บรรจุซองฟอยล์เก็บอุณหภูมิ จัดส่งถึงบ้านภายใน 1-2 วัน
🛡️ รับประกันความสด 100% หากสินค้ามีปัญหาถ่ายรูปแจ้งในแชท เคลมส่งใหม่ให้ฟรีทันทีค่ะ!`
    };

    function isElementVisible(el) {
        if (!el) return false;
        try {
            const rect = el.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0;
        } catch(e) {
            return false;
        }
    }

    function findMessengerComposer() {
        // 1. Meta Business Suite Lexical Editor
        let el = document.querySelector('div[data-lexical-editor="true"]');
        if (el && isElementVisible(el)) return el;

        // 2. Query by role="textbox" and contenteditable (excluding our helper widget)
        const textboxes = Array.from(document.querySelectorAll('div[role="textbox"][contenteditable="true"]'));
        const validTextboxes = textboxes.filter(tb => !tb.closest('#pakhem-group-helper') && isElementVisible(tb));
        if (validTextboxes.length > 0) return validTextboxes[validTextboxes.length - 1];

        // 3. XPath query for reply/message boxes
        const xp = getElementByXPath(
            '//div[contains(@aria-label, "ตอบกลับ") and @contenteditable="true"] | ' +
            '//div[contains(@aria-placeholder, "ตอบกลับ") and @contenteditable="true"] | ' +
            '//div[contains(@aria-label, "ข้อความ") and @contenteditable="true"] | ' +
            '//div[contains(@aria-label, "Message") and @contenteditable="true"]'
        );
        if (xp && !xp.closest('#pakhem-group-helper') && isElementVisible(xp)) return xp;

        // 4. Any contenteditable in main area (last one)
        const editables = Array.from(document.querySelectorAll('div[contenteditable="true"]')).filter(ed => !ed.closest('#pakhem-group-helper') && isElementVisible(ed));
        if (editables.length > 0) {
            return editables[editables.length - 1];
        }
        return null;
    }

    function extractAddressFromMessenger() {
        const selectors = [
            'div[data-scope="messages_table"] div[dir="auto"]',
            'div[role="main"] div[dir="auto"]',
            'div[role="row"] div[dir="auto"]',
            'div[data-lexical-text="true"]',
            'span[dir="auto"]'
        ];
        let allElements = [];
        for (const sel of selectors) {
            const els = Array.from(document.querySelectorAll(sel));
            if (els.length > allElements.length) {
                allElements = els;
            }
        }
        const widget = document.getElementById("pakhem-group-helper");
        const chatElements = allElements.filter(el => !widget || !widget.contains(el));
        const fullChatText = chatElements.map(m => (m.textContent || "").trim()).filter(Boolean).join("\n");

        const phoneMatch = fullChatText.match(/(?:0[689]\d[\s\-]?\d{3}[\s\-]?\d{4}|0[23457]\d[\s\-]?\d{3}[\s\-]?\d{3})/);
        const phone = phoneMatch ? phoneMatch[0].replace(/[\s\-]/g, '') : "";

        const zipMatch = fullChatText.match(/\b(1\d{4}|2\d{4}|3\d{4}|4\d{4}|5\d{4}|6\d{4}|7\d{4}|8\d{4}|9\d{4})\b/);
        const zip = zipMatch ? zipMatch[0] : "";

        const lines = fullChatText.split("\n").map(l => l.trim()).filter(l => l.length > 4);
        let addressLines = [];
        for (const l of lines) {
            if (l.includes("ต.") || l.includes("ตำบล") || l.includes("อ.") || l.includes("อำเภอ") ||
                l.includes("จ.") || l.includes("จังหวัด") || l.includes("แขวง") || l.includes("เขต") ||
                l.includes("ม.") || l.includes("หมู่") || l.includes("ซอย") || l.includes("ถนน") ||
                l.includes("บ้านเลขที่") || l.includes("เลขที่")) {
                if (!l.includes("กดปุ่มเลือก") && !l.includes("สูตรทองคำ") && !l.includes("ปลาสลิด") && !l.includes("ราคามาตรฐาน")) {
                    addressLines.push(l);
                }
            }
        }

        return {
            phone: phone,
            zip: zip,
            address: addressLines.join(" "),
            raw: fullChatText
        };
    }

    function createWidget() {
        if (document.getElementById("pakhem-group-helper")) return;

        const widget = document.createElement("div");
        widget.id = "pakhem-group-helper";
        widget.style.cssText = `
            position: fixed;
            bottom: 24px;
            right: 24px;
            z-index: 999999;
            background: #ffffff;
            border-radius: 14px;
            box-shadow: 0 10px 35px rgba(0,0,0,0.35);
            width: 300px;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            border: 2px solid #28a745;
            overflow: hidden;
            box-sizing: border-box;
            transition: border-color 0.3s;
        `;

        const savedPos = localStorage.getItem("pkh_widget_pos");
        if (savedPos) {
            try {
                const pos = JSON.parse(savedPos);
                widget.style.top = `${pos.top}px`;
                widget.style.left = `${pos.left}px`;
                widget.style.bottom = "auto";
                widget.style.right = "auto";
            } catch(e) {}
        }

        widget.innerHTML = `
            <div id="pkh-header" style="background: linear-gradient(135deg, #1b5e20, #28a745); color: #fff; padding: 10px 14px; font-weight: bold; font-size: 13px; display: flex; justify-content: space-between; align-items: center; cursor: move; user-select: none; border-radius: 10px 10px 0 0;">
                <span id="pkh-header-text">🐟 ป้าเข็ม: ผู้ช่วยแชร์ลงกลุ่ม</span>
                <span id="pkh-toggle" style="cursor: pointer; font-size: 16px; padding: 0 4px;" title="ย่อ/ขยายหน้าต่าง">—</span>
            </div>
            <div id="pkh-body" style="padding: 12px; font-size: 12px; color: #333; background: #ffffff; border-radius: 0 0 10px 10px;">
                
                <!-- แถบแสดงสถานะสมาชิกกลุ่ม -->
                <div id="pkh-group-badge" style="padding: 8px 10px; margin-bottom: 10px; border-radius: 8px; font-size: 11px; font-weight: bold; background: #e8f5e9; color: #1b5e20; border: 1px solid #c8e6c9; display: flex; flex-direction: column; gap: 4px;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span id="pkh-group-title" style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 200px;">กำลังตรวจกลุ่ม...</span>
                        <button id="pkh-btn-refresh-status" style="background: transparent; border: none; font-size: 12px; cursor: pointer; padding: 0;" title="คลิกเพื่อตรวจสถานะกลุ่มใหม่">🔄</button>
                    </div>
                    <div style="display: flex; justify-content: space-between; align-items: center; font-size: 11px;">
                        <span id="pkh-group-status">ตรวจสถานะ...</span>
                        <span id="pkh-profile-name" style="font-weight: normal; color: #555; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 130px;"></span>
                    </div>
                </div>

                <!-- 🚀 ปุ่มหลักยักษ์: 1-คลิก ใส่แคปชั่น + แชร์ลงกลุ่มทันที -->
                <div style="margin-bottom: 10px;">
                    <button type="button" id="pkh-btn-auto-share-live" style="width: 100%; background: linear-gradient(135deg, #e0245e, #ff416c); color: white; border: none; border-radius: 8px; padding: 13px 4px; font-weight: bold; font-size: 13px; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 6px; box-shadow: 0 4px 12px rgba(224,36,94,0.35);">
                        🚀 1-คลิก: ใส่แคปชั่น + แชร์ลงกลุ่มทันที!
                    </button>
                </div>

                <!-- ปุ่มสำรอง 1 แถว -->
                <div style="display: flex; gap: 6px; margin-bottom: 10px;">
                    <button id="pkh-btn-copy-text" style="flex: 1; background: #f0f2f5; color: #333; border: 1px solid #ced4da; border-radius: 6px; padding: 7px 4px; font-size: 11px; font-weight: bold; cursor: pointer;">
                        📋 ก๊อปปี้แคปชั่น
                    </button>
                    <button id="pkh-btn-rand" style="flex: 1; background: #f0f2f5; color: #333; border: 1px solid #ced4da; border-radius: 6px; padding: 7px 4px; font-size: 11px; cursor: pointer;">
                        🎲 สลับแคปชั่น
                    </button>
                </div>

                <!-- ข้อความยืนยันความสบายใจ -->
                <div style="background: #f8f9fa; border: 1px solid #e9ecef; border-radius: 8px; padding: 8px 10px; font-size: 10.5px; color: #495057; line-height: 1.45; text-align: center; margin-bottom: 8px;">
                    ✅ วิ่งเข้ากลุ่มโดยตรง <b>ไม่ต้องตามลบออก</b><br>
                    🤖 <b>บอทจะคอยตอบแชท & สรุปออเดอร์แทน 100%</b>
                </div>

                <div id="pkh-toast" style="font-size: 11px; color: #666; text-align: center; min-height: 24px; line-height: 1.4; padding: 4px; background: #fdfdfe; border-radius: 6px;">
                    🔒 พร้อมช่วยแชร์ลงกลุ่มทันทีครับ
                </div>
            </div>
        `;

        document.body.appendChild(widget);

        // 📝 ตรวจสอบโน้ตลูกค้า (CRM Note Alert บนวิดเจ็ต)
        const crmBadge = document.createElement("div");
        crmBadge.id = "pkh-crm-badge";
        crmBadge.style.cssText = "display: none; padding: 6px 8px; margin-bottom: 8px; border-radius: 6px; font-size: 11px; background: #e8f4fd; color: #004085; border: 1px solid #b8daff; line-height: 1.4;";
        const groupBadgeEl = widget.querySelector("#pkh-group-badge");
        if (groupBadgeEl && groupBadgeEl.parentNode) {
            groupBadgeEl.parentNode.insertBefore(crmBadge, groupBadgeEl.nextSibling);
        }

        async function checkCustomerNoteAlert() {
            try {
                const currentKey = window.location.origin + window.location.pathname;
                let note = "";
                if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
                    const data = await chrome.storage.local.get(["pakhem_customer_notes"]);
                    const notes = data.pakhem_customer_notes || {};
                    if (notes[currentKey]) note = notes[currentKey].note || "";
                } else {
                    const raw = localStorage.getItem("pakhem_customer_notes");
                    if (raw) {
                        const notes = JSON.parse(raw);
                        if (notes[currentKey]) note = notes[currentKey].note || "";
                    }
                }

                if (note && crmBadge) {
                    crmBadge.style.display = "block";
                    crmBadge.innerHTML = `💡 <b>โน้ตลูกค้ารายนี้:</b><br>${note}`;
                } else if (crmBadge) {
                    crmBadge.style.display = "none";
                }
            } catch(e) {}
        }
        checkCustomerNoteAlert();

        // Elements
        const header = widget.querySelector("#pkh-header");
        const headerText = widget.querySelector("#pkh-header-text");
        const toggleBtn = widget.querySelector("#pkh-toggle");
        const bodyDiv = widget.querySelector("#pkh-body");
        const groupBadge = widget.querySelector("#pkh-group-badge");
        const groupTitle = widget.querySelector("#pkh-group-title");
        const groupStatus = widget.querySelector("#pkh-group-status");
        const refreshStatusBtn = widget.querySelector("#pkh-btn-refresh-status");
        const capTitle = widget.querySelector("#pkh-cap-title");
        const capArea = widget.querySelector("#pkh-caption-area");
        const randBtn = widget.querySelector("#pkh-btn-rand");
        const insertBtn = widget.querySelector("#pkh-btn-insert");
        const copyImgBtn = widget.querySelector("#pkh-btn-copy-img");
        const copyFriedBtn = widget.querySelector("#pkh-btn-copy-fried");
        const copyTextBtn = widget.querySelector("#pkh-btn-copy-text");
        const selectGroup = widget.querySelector("#pkh-select-group");
        const toast = widget.querySelector("#pkh-toast");

        // 💬 จัดการแถบผู้ช่วยปิดการขาย Messenger / Meta Business Suite Inbox
        const messengerBox = widget.querySelector("#pkh-messenger-box");
        const btnSendPrice = widget.querySelector("#pkh-btn-send-price");
        const btnSendBank = widget.querySelector("#pkh-btn-send-bank");
        const btnSendShipping = widget.querySelector("#pkh-btn-send-shipping");
        const btnExtractAddr = widget.querySelector("#pkh-btn-extract-addr");

        let isGroupToolsManuallyOpened = false;
        let isChatBoxManuallyOpened = false;
        const btnToggleChatBox = widget.querySelector("#pkh-btn-toggle-chat-box");

        if (btnToggleChatBox) {
            btnToggleChatBox.addEventListener("click", () => {
                if (!messengerBox) return;
                if (messengerBox.style.display === "none") {
                    messengerBox.style.display = "block";
                    isChatBoxManuallyOpened = true;
                    btnToggleChatBox.textContent = "💬 ซ่อนผู้ช่วยตอบแชท & รับออเดอร์ ▲";
                } else {
                    messengerBox.style.display = "none";
                    isChatBoxManuallyOpened = false;
                    btnToggleChatBox.textContent = "💬 เปิดผู้ช่วยตอบแชท & รับออเดอร์ช่วยบอท ▼";
                }
            });
        }

        function checkMessengerPageMode() {
            const pth = window.location.pathname || "";
            const isMsg = pth.includes('/messages') || pth.includes('/inbox') || window.location.hostname.includes('messenger.com');
            const isVideoOrLive = pth.includes('/videos/') || pth.includes('/live');

            // ตรวจหาหน้าต่างสร้างโพสต์ / แชร์ไปยังกลุ่ม
            const shareDialog = document.querySelector('div[role="dialog"]');
            const isShareDialogOpen = !!shareDialog && (
                (shareDialog.textContent || '').includes('สร้างโพสต์') || 
                (shareDialog.textContent || '').includes('แชร์') || 
                (shareDialog.textContent || '').includes('กลุ่ม') ||
                (shareDialog.textContent || '').includes('Share')
            );

            const groupToolsEl = widget.querySelector("#pkh-group-tools");
            const groupToolsToggleEl = widget.querySelector("#pkh-group-tools-toggle");
            const groupBadgeEl = widget.querySelector("#pkh-group-badge");
            const liveShareBox = widget.querySelector("#pkh-live-share-box");

            // แสดงแถบช่วยแชร์ไลฟ์สดลงกลุ่มทันทีเมื่อเปิดหน้าต่างแชร์ หรืออยู่ในหน้าไลฟ์สด
            if (liveShareBox) {
                if (isShareDialogOpen || isVideoOrLive) {
                    liveShareBox.style.display = "block";
                } else {
                    liveShareBox.style.display = "none";
                }
            }

            if (isShareDialogOpen) {
                if (headerText && !headerText.textContent.includes("⏳")) {
                    headerText.textContent = "📢 ป้าเข็ม: แชร์ไลฟ์ลงกลุ่ม (v5.0)";
                    header.style.background = "#e0245e";
                    widget.style.borderColor = "#e0245e";
                }
                if (groupBadgeEl) groupBadgeEl.style.display = "flex";
                if (groupToolsToggleEl) groupToolsToggleEl.style.display = "none";
                if (groupToolsEl) groupToolsEl.style.display = "block";
            } else if (isMsg) {
                if (messengerBox) messengerBox.style.display = "block";
                if (btnToggleChatBox) btnToggleChatBox.textContent = "💬 ซ่อนผู้ช่วยตอบแชท & รับออเดอร์ ▲";
                if (groupBadgeEl && !pth.includes('/groups/')) groupBadgeEl.style.display = "none";
                if (groupToolsToggleEl) groupToolsToggleEl.style.display = "block";
                if (groupToolsEl && !isGroupToolsManuallyOpened) {
                    groupToolsEl.style.display = "none";
                }
                if (headerText && !headerText.textContent.includes("⏳")) {
                    headerText.textContent = "💬 ป้าเข็ม: ตอบแชท & รับออเดอร์เชื่อมบอท (v5.0)";
                    header.style.background = "#007bff";
                    widget.style.borderColor = "#007bff";
                }
            } else {
                if (messengerBox && !isChatBoxManuallyOpened) messengerBox.style.display = "none";
                if (groupBadgeEl) groupBadgeEl.style.display = "flex";
                if (groupToolsToggleEl) groupToolsToggleEl.style.display = "none";
                if (groupToolsEl) groupToolsEl.style.display = "block";
                if (headerText && !headerText.textContent.includes("⏳")) {
                    headerText.textContent = "🐟 ป้าเข็ม: ตรวจกลุ่ม + โพสต์ (v5.0)";
                    header.style.background = "#28a745";
                    widget.style.borderColor = "#28a745";
                }
            }
        }
        setInterval(checkMessengerPageMode, 1500);
        checkMessengerPageMode();

        const btnToggleGroupTools = widget.querySelector("#pkh-btn-toggle-group-tools");
        if (btnToggleGroupTools) {
            btnToggleGroupTools.addEventListener("click", () => {
                const groupToolsEl = widget.querySelector("#pkh-group-tools");
                if (groupToolsEl) {
                    if (groupToolsEl.style.display === "none") {
                        groupToolsEl.style.display = "block";
                        isGroupToolsManuallyOpened = true;
                        btnToggleGroupTools.textContent = "📢 ซ่อนเครื่องมือโพสต์กลุ่ม Facebook ▲";
                    } else {
                        groupToolsEl.style.display = "none";
                        isGroupToolsManuallyOpened = false;
                        btnToggleGroupTools.textContent = "📢 แสดงเครื่องมือโพสต์กลุ่ม Facebook ▼";
                    }
                }
            });
        }

        async function insertReplyToMessenger(replyText, label, autoPressSend = false) {
            const composer = findMessengerComposer();
            let inserted = false;
            if (composer) {
                inserted = await insertTextIntoEditor(composer, replyText);
                if (autoPressSend && inserted) {
                    await new Promise(r => setTimeout(r, 350));
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
                        const sendBtn = document.querySelector('div[aria-label="กด Enter เพื่อส่ง"][role="button"], div[aria-label="Press enter to send"][role="button"], div[aria-label="ส่ง"][role="button"], div[aria-label="Send"][role="button"]');
                        if (sendBtn) sendBtn.click();
                    } catch(e) {}
                }
            }

            // Always copy to clipboard as seamless failsafe
            try {
                await navigator.clipboard.writeText(replyText);
            } catch(e) {}

            if (inserted) {
                showToast(`✅ พิมพ์ ${label} ลงในช่องแชทแล้วครับ (กดส่งได้เลย)`, "#28a745");
            } else if (composer) {
                showToast(`✅ วางข้อความแล้ว (หรือกด Ctrl+V ในช่องแชทได้ทันที)`, "#007bff");
            } else {
                showToast(`📋 ก๊อปปี้ ${label} เข้าคลิปบอร์ดแล้วครับ กด Ctrl+V วางได้เลย!`, "#007bff");
            }
        }

        if (btnSendPrice) {
            btnSendPrice.addEventListener("click", () => insertReplyToMessenger(MESSENGER_REPLIES.price, "ราคา 3 แพ็กเกจ"));
        }
        if (btnSendBank) {
            btnSendBank.addEventListener("click", () => insertReplyToMessenger(MESSENGER_REPLIES.bank, "บัญชีกรุงไทย"));
        }
        if (btnSendShipping) {
            btnSendShipping.addEventListener("click", () => insertReplyToMessenger(MESSENGER_REPLIES.shipping, "เงื่อนไขจัดส่ง"));
        }
        const ordNameInput = widget.querySelector("#pkh-ord-name");
        const ordPhoneInput = widget.querySelector("#pkh-ord-phone");
        const ordAddrInput = widget.querySelector("#pkh-ord-addr");
        const ordPkgSelect = widget.querySelector("#pkh-ord-pkg");
        const btnSubmitOrder = widget.querySelector("#pkh-btn-submit-order");

        if (btnExtractAddr) {
            btnExtractAddr.addEventListener("click", async () => {
                showToast("⏳ กำลังสแกนแชทเพื่อสกัดชื่อ-เบอร์โทร-ที่อยู่...", "#007bff");
                const res = extractAddressFromMessenger();
                const chatName = getChatCustomerName();
                if (ordNameInput && chatName && !ordNameInput.value.trim()) {
                    ordNameInput.value = chatName;
                }
                if (ordPhoneInput && res.phone) {
                    ordPhoneInput.value = res.phone;
                }
                if (ordAddrInput && (res.address || res.zip)) {
                    ordAddrInput.value = (res.address + (res.zip && !res.address.includes(res.zip) ? " " + res.zip : "")).trim();
                }
                // Auto-detect package & payment from chat text
                if (ordPkgSelect && res.raw) {
                    const rawTxt = res.raw;
                    const isCod = rawTxt.includes("ปลายทาง") || rawTxt.toUpperCase().includes("COD");
                    if (rawTxt.includes("2 โล") || rawTxt.includes("2 กก") || rawTxt.includes("2กิโล") || rawTxt.includes("1,090") || rawTxt.includes("1090")) {
                        ordPkgSelect.value = "SKU-SLID-MD-2KG|TRANSFER|1090|ปลาสลิดแดดเดียว ชุดตุนสุดคุ้ม 2 กิโลกรัม (ส่งฟรีรถห้องเย็น)";
                    } else if (rawTxt.includes("ครึ่งโล") || rawTxt.includes("500") || rawTxt.includes("390") || rawTxt.includes("410")) {
                        ordPkgSelect.value = isCod
                            ? "SKU-SLID-MD-500G|COD|410|ปลาสลิดแดดเดียว ชุดพอดีมื้อ 500 กรัม (เก็บปลายทาง COD)"
                            : "SKU-SLID-MD-500G|TRANSFER|390|ปลาสลิดแดดเดียว ชุดพอดีมื้อ 500 กรัม (โอนส่งฟรี)";
                    } else {
                        ordPkgSelect.value = isCod
                            ? "SKU-SLID-MD-1KG|COD|570|ปลาสลิดแดดเดียว ชุดยอดฮิต 1 กิโลกรัม (เก็บปลายทาง COD)"
                            : "SKU-SLID-MD-1KG|TRANSFER|550|ปลาสลิดแดดเดียว ชุดยอดฮิต 1 กิโลกรัม (โอนส่งฟรี)";
                    }
                }
                let summary = "";
                if (res.phone) summary += `เบอร์: ${res.phone} `;
                if (res.zip) summary += `ปณ: ${res.zip} `;
                if (res.address) summary += `ที่อยู่: ${res.address}`;

                if (summary) {
                    try {
                        await navigator.clipboard.writeText(summary);
                    } catch(e) {}
                    showToast(`🎉 ดึงข้อมูลใส่ฟอร์มเปิดบิลแล้ว! ตรวจสอบแล้วกด '🚀 บันทึกออเดอร์' ได้เลย`, "#28a745");
                } else {
                    showToast("ℹ️ ยังไม่พบเบอร์โทร/ที่อยู่ในแชท (พิมพ์กรอกในช่องด้านล่างได้เลยครับ)", "#e67e22");
                }
            });
        }

        if (btnSubmitOrder) {
            btnSubmitOrder.addEventListener("click", async () => {
                const nameVal = (ordNameInput ? ordNameInput.value.trim() : "") || getChatCustomerName() || "ลูกค้า Facebook";
                const phoneVal = (ordPhoneInput ? ordPhoneInput.value.trim() : "").replace(/[\s\-]/g, "");
                const addrVal = ordAddrInput ? ordAddrInput.value.trim() : "";
                const pkgRaw = ordPkgSelect ? ordPkgSelect.value : "SKU-SLID-MD-1KG|TRANSFER|550|ปลาสลิดแดดเดียว ชุดยอดฮิต 1 กิโลกรัม (โอนส่งฟรี)";
                const [sku, payMethod, priceStr, pkgLabel] = pkgRaw.split("|");
                const priceNum = parseFloat(priceStr) || 550;

                if (!/^0\d{8,9}$/.test(phoneVal)) {
                    showToast("⚠️ กรุณาระบุเบอร์โทรศัพท์ผู้รับ 10 หลักให้ถูกต้องก่อนครับ", "#d9534f");
                    if (ordPhoneInput) ordPhoneInput.focus();
                    return;
                }
                if (addrVal.length < 10) {
                    showToast("⚠️ กรุณาระบุที่อยู่จัดส่ง (บ้านเลขที่ ตำบล อำเภอ จังหวัด) ให้ครบก่อนครับ", "#d9534f");
                    if (ordAddrInput) ordAddrInput.focus();
                    return;
                }

                btnSubmitOrder.disabled = true;
                btnSubmitOrder.textContent = "⏳ กำลังบันทึกออเดอร์เข้าฐานข้อมูลบอท...";
                showToast("⏳ กำลังส่งออเดอร์เข้า Supabase + Google Sheets + Telegram...", "#007bff");

                const now = new Date();
                const pad = n => String(n).padStart(2, "0");
                const orderId = `PKF-${pad(now.getMonth()+1)}${pad(now.getDate())}${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;

                const supaUrl = "https://usqhvujqmnxqrdoovvnp.supabase.co/rest/v1/direct_orders";
                const supaKey = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVzcWh2dWpxbW54cXJkb292dm5wIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTQyOTc4NjAsImV4cCI6MjA2OTg3Mzg2MH0.3kCGGAe1OoSJ_SCN_NDSdnKep1hXIMgMxR1lBd_i2eI";
                const gasUrl = "https://script.google.com/macros/s/AKfycbxHAfBm0V67wkiXb1dlAFNbG3NQudcN35zuQ3xjFo0FRHY2ja8TB3-Xj0l_xOWxeF404Q/exec";

                const orderRow = {
                    order_code: orderId,
                    product_name: "ปลาสลิดแดดเดียวสุพรรณแท้ ป้าเข็ม คัดพิเศษ",
                    package_code: sku,
                    package_name: pkgLabel,
                    price: priceNum,
                    customer_name: nameVal,
                    phone: phoneVal,
                    address: addrVal,
                    payment_method: payMethod,
                    status: "PENDING",
                    note: `[ChromeExt v4.9] ${window.location.href}`,
                    created_at: now.toISOString()
                };

                let saved = false;
                try {
                    const rSupa = await fetch(supaUrl, {
                        method: "POST",
                        headers: {
                            "apikey": supaKey,
                            "Authorization": "Bearer " + supaKey,
                            "Content-Type": "application/json",
                            "Prefer": "return=minimal"
                        },
                        body: JSON.stringify(orderRow)
                    });
                    if (rSupa.ok || rSupa.status === 409) saved = true;
                } catch(e) {}

                try {
                    await fetch(gasUrl, {
                        method: "POST",
                        mode: "no-cors",
                        headers: { "Content-Type": "text/plain;charset=utf-8" },
                        body: JSON.stringify({
                            action: "order_fish",
                            order_id: orderId,
                            skip_db: saved,
                            name: nameVal,
                            phone: phoneVal,
                            address: addrVal,
                            package: sku,
                            package_name: pkgLabel,
                            price: priceNum,
                            payment_method: payMethod,
                            note: `[ChromeExt v4.9] ${window.location.href}`
                        })
                    });
                    saved = true;
                } catch(e) {}

                const payText = payMethod === "COD"
                    ? `🚚 เก็บเงินปลายทาง (COD) ยอดรวม ${priceNum.toLocaleString()} บาท`
                    : `💳 โอนเงินส่งฟรี ยอดรวม ${priceNum.toLocaleString()} บาท (กรุงไทย 038-0-25363-1 นายจีรวัฒน์ พลอาจ)`;

                const confirmMsg = `✅ ป้าเข็มบันทึกออเดอร์ให้เรียบร้อยแล้วจ้า! 🙏💕
🔖 รหัสสั่งซื้อ: ${orderId}
📦 สินค้า: ${pkgLabel}
💰 การชำระเงิน: ${payText}
👤 ผู้รับ: คุณ${nameVal} (${phoneVal})
📍 ที่อยู่จัดส่ง: ${addrVal}
🚚 จัดส่งแพ็กซองฟอยล์เก็บความเย็นถึงหน้าบ้านภายใน 1-2 วันค่ะ ขอบพระคุณมากนะคะ 🐟✨`;

                await insertReplyToMessenger(confirmMsg, `บิลยืนยันออเดอร์ ${orderId}`, true);
                try {
                    const savedMap = JSON.parse(localStorage.getItem("pkh_auto_saved_orders") || "{}");
                    savedMap[phoneVal] = { orderId, ts: Date.now(), addr: addrVal };
                    localStorage.setItem("pkh_auto_saved_orders", JSON.stringify(savedMap));
                } catch(e) {}
                showToast(`🎉 บันทึกออเดอร์ ${orderId} เข้าบอท + ส่งบิลในแชทสำเร็จ!`, "#28a745");
                btnSubmitOrder.disabled = false;
                btnSubmitOrder.textContent = "🚀 บันทึกออเดอร์เข้าบอท + พิมพ์บิลยืนยันในแชท";
            });
        }

        // 🤖 ระบบ Auto-Pilot เฝ้าแชท & รับออเดอร์อัตโนมัติ 100% (v5.0)
        const btnAutopilotToggle = widget.querySelector("#pkh-btn-autopilot-toggle");
        let isAutoPilotEnabled = localStorage.getItem("pkh_autopilot_on") !== "0";
        let isAutoPilotBusy = false;

        function updateAutoPilotBtnUI() {
            if (!btnAutopilotToggle) return;
            if (isAutoPilotEnabled) {
                btnAutopilotToggle.textContent = "🤖 อัตโนมัติ: ON";
                btnAutopilotToggle.style.background = "#28a745";
            } else {
                btnAutopilotToggle.textContent = "⚪ อัตโนมัติ: OFF";
                btnAutopilotToggle.style.background = "#6c757d";
            }
        }
        updateAutoPilotBtnUI();

        if (btnAutopilotToggle) {
            btnAutopilotToggle.addEventListener("click", () => {
                isAutoPilotEnabled = !isAutoPilotEnabled;
                localStorage.setItem("pkh_autopilot_on", isAutoPilotEnabled ? "1" : "0");
                updateAutoPilotBtnUI();
                showToast(
                    isAutoPilotEnabled
                        ? "🤖 เปิดโหมดเฝ้าแชท & รับออเดอร์อัตโนมัติ 100% แล้ว!"
                        : "⚪ ปิดโหมดอัตโนมัติ (ใช้โหมดกดปุ่ม 1-คลิก)",
                    isAutoPilotEnabled ? "#28a745" : "#6c757d"
                );
            });
        }

        async function runMessengerAutoPilot() {
            if (!isAutoPilotEnabled || isAutoPilotBusy) return;
            const pth = window.location.pathname || "";
            const isChatScreen = pth.includes("/messages") || pth.includes("/inbox") || window.location.hostname.includes("messenger.com");
            if (!isChatScreen) return;

            try {
                const res = extractAddressFromMessenger();
                const rawTxt = res.raw || "";
                if (!rawTxt || rawTxt.length < 2) return;

                const chatName = getChatCustomerName();
                if (ordNameInput && chatName && document.activeElement !== ordNameInput) {
                    ordNameInput.value = chatName;
                }
                if (ordPhoneInput && res.phone && document.activeElement !== ordPhoneInput) {
                    ordPhoneInput.value = res.phone;
                }
                if (ordAddrInput && (res.address || res.zip) && document.activeElement !== ordAddrInput) {
                    ordAddrInput.value = (res.address + (res.zip && !res.address.includes(res.zip) ? " " + res.zip : "")).trim();
                }

                // ตรวจบริบทว่าแชทนี้คุยเรื่องปลาสลิดหรือไม่ (ป้องกันแชทเพื่อน/ส่วนตัว)
                const fishKeywords = ["ปลาสลิด", "ป้าเข็ม", "ครึ่งโล", "500", "1 โล", "1โล", "1 กิโล", "2 โล", "2โล", "390", "410", "550", "570", "1,090", "1090", "สนใจ", "ปลายทาง", "โอนเงิน", "แพ็กเกจ"];
                const hasFishContext = pth.includes("/inbox") || fishKeywords.some(k => rawTxt.includes(k));
                if (!hasFishContext) return;

                // เลือกแพ็กเกจอัตโนมัติจากข้อความแชท
                if (ordPkgSelect && document.activeElement !== ordPkgSelect) {
                    const isCod = rawTxt.includes("ปลายทาง") || rawTxt.toUpperCase().includes("COD");
                    if (rawTxt.includes("2 โล") || rawTxt.includes("2โล") || rawTxt.includes("2 กก") || rawTxt.includes("1,090") || rawTxt.includes("1090")) {
                        ordPkgSelect.value = "SKU-SLID-MD-2KG|TRANSFER|1090|ปลาสลิดแดดเดียว ชุดตุนสุดคุ้ม 2 กิโลกรัม (ส่งฟรีรถห้องเย็น)";
                    } else if (rawTxt.includes("ครึ่งโล") || rawTxt.includes("500") || rawTxt.includes("390") || rawTxt.includes("410")) {
                        ordPkgSelect.value = isCod
                            ? "SKU-SLID-MD-500G|COD|410|ปลาสลิดแดดเดียว ชุดพอดีมื้อ 500 กรัม (เก็บปลายทาง COD)"
                            : "SKU-SLID-MD-500G|TRANSFER|390|ปลาสลิดแดดเดียว ชุดพอดีมื้อ 500 กรัม (โอนส่งฟรี)";
                    } else {
                        ordPkgSelect.value = isCod
                            ? "SKU-SLID-MD-1KG|COD|570|ปลาสลิดแดดเดียว ชุดยอดฮิต 1 กิโลกรัม (เก็บปลายทาง COD)"
                            : "SKU-SLID-MD-1KG|TRANSFER|550|ปลาสลิดแดดเดียว ชุดยอดฮิต 1 กิโลกรัม (โอนส่งฟรี)";
                    }
                }

                // 1) กรณีพบเบอร์โทร 10 หลัก + ที่อยู่ครบถ้วน -> บันทึกออเดอร์เข้าบอทอัตโนมัติทันที (Zero-Click)
                const cleanPhone = (res.phone || "").replace(/[\s\-]/g, "");
                const fullAddr = ((res.address || "") + (res.zip && !(res.address || "").includes(res.zip) ? " " + res.zip : "")).trim();
                if (/^0\d{8,9}$/.test(cleanPhone) && fullAddr.length >= 12 && !rawTxt.includes("รหัสสั่งซื้อ: PKF-")) {
                    const savedMap = JSON.parse(localStorage.getItem("pkh_auto_saved_orders") || "{}");
                    if (!savedMap[cleanPhone] && btnSubmitOrder && !btnSubmitOrder.disabled) {
                        isAutoPilotBusy = true;
                        showToast(`🤖 [Auto-Pilot] พบที่อยู่+เบอร์ ${cleanPhone} กำลังบันทึกออเดอร์อัตโนมัติ...`, "#28a745");
                        btnSubmitOrder.click();
                        setTimeout(() => { isAutoPilotBusy = false; }, 6000);
                        return;
                    }
                }

                // 2) กรณีลูกค้าทักถาม 'สนใจ / ราคาเท่าไหร่' และในแชทยังไม่เคยส่งตารางราคา -> ส่งตารางราคาอัตโนมัติ
                const chatKey = window.location.origin + window.location.pathname;
                const repliedMap = JSON.parse(localStorage.getItem("pkh_auto_replied_chats") || "{}");
                const askPriceKeywords = ["สนใจ", "ราคาเท่าไหร่", "เท่าไร", "เท่าไหร่", "โลละเท่าไหร่", "กี่บาท", "สั่งปลาสลิด"];
                if (!repliedMap[chatKey] && !rawTxt.includes("390.-") && askPriceKeywords.some(k => rawTxt.includes(k))) {
                    isAutoPilotBusy = true;
                    repliedMap[chatKey] = Date.now();
                    localStorage.setItem("pkh_auto_replied_chats", JSON.stringify(repliedMap));
                    showToast("🤖 [Auto-Pilot] ลูกค้าถามราคา กำลังส่งตารางราคา 3 ชุดอัตโนมัติ...", "#007bff");
                    await insertReplyToMessenger(MESSENGER_REPLIES.price, "ราคา 3 แพ็กเกจ (Auto)", true);
                    setTimeout(() => { isAutoPilotBusy = false; }, 5000);
                }
            } catch(e) {
                isAutoPilotBusy = false;
            }
        }
        setInterval(runMessengerAutoPilot, 3200);

        // 📝 CRM โน้ตลูกค้าสดในแชท + Export CSV
        const inboxNoteInput = widget.querySelector("#pkh-inbox-note-input");
        const btnSaveInboxNote = widget.querySelector("#pkh-btn-save-inbox-note");
        const btnExportNotesCsv = widget.querySelector("#pkh-btn-export-notes-csv");
        const inboxTagChips = widget.querySelectorAll(".pkh-inbox-tag");

        function getChatCustomerName() {
            const nameEl = document.querySelector('div[role="main"] h2') ||
                           document.querySelector('div[data-scope="messages_table"]') ||
                           Array.from(document.querySelectorAll('span[dir="auto"], div[dir="auto"]')).find(el => {
                               const txt = (el.textContent || "").trim();
                               return txt.length > 2 && txt.length < 35 && !txt.includes("ป้าเข็ม") && !txt.includes("กล่องข้อความ") && !txt.includes("Messenger") && !txt.includes("มอบหมาย");
                           });
            return nameEl ? (nameEl.textContent || "").trim() : "";
        }

        async function loadCurrentCustomerNote() {
            if (!inboxNoteInput) return;
            try {
                const currentKey = window.location.origin + window.location.pathname;
                let note = "";
                if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
                    const data = await chrome.storage.local.get(["pakhem_customer_notes"]);
                    const notes = data.pakhem_customer_notes || {};
                    if (notes[currentKey]) note = notes[currentKey].note || "";
                } else {
                    const raw = localStorage.getItem("pakhem_customer_notes");
                    if (raw) {
                        const notes = JSON.parse(raw);
                        if (notes[currentKey]) note = notes[currentKey].note || "";
                    }
                }
                if (note && inboxNoteInput.value !== note) {
                    inboxNoteInput.value = note;
                }
            } catch(e) {}
        }
        setInterval(loadCurrentCustomerNote, 3000);
        loadCurrentCustomerNote();

        if (inboxTagChips) {
            inboxTagChips.forEach(chip => {
                chip.addEventListener("click", () => {
                    const tag = chip.getAttribute("data-tag") || "";
                    if (inboxNoteInput && tag) {
                        const cur = inboxNoteInput.value.trim();
                        inboxNoteInput.value = cur ? cur + " | " + tag : tag;
                    }
                });
            });
        }

        if (btnSaveInboxNote) {
            btnSaveInboxNote.addEventListener("click", async () => {
                const noteText = inboxNoteInput ? inboxNoteInput.value.trim() : "";
                const currentKey = window.location.origin + window.location.pathname;
                const custName = getChatCustomerName();

                let notes = {};
                try {
                    if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
                        const data = await chrome.storage.local.get(["pakhem_customer_notes"]);
                        notes = data.pakhem_customer_notes || {};
                        notes[currentKey] = {
                            key: currentKey,
                            url: window.location.href,
                            title: custName || document.title || "ลูกค้าแชท",
                            note: noteText,
                            updated_at: new Date().toLocaleString("th-TH")
                        };
                        await chrome.storage.local.set({ pakhem_customer_notes: notes });
                    }
                } catch(e) {}

                try {
                    const raw = localStorage.getItem("pakhem_customer_notes");
                    if (raw) notes = JSON.parse(raw);
                    notes[currentKey] = {
                        key: currentKey,
                        url: window.location.href,
                        title: custName || document.title || "ลูกค้าแชท",
                        note: noteText,
                        updated_at: new Date().toLocaleString("th-TH")
                    };
                    localStorage.setItem("pakhem_customer_notes", JSON.stringify(notes));
                } catch(e) {}

                checkCustomerNoteAlert();
                showToast("💾 บันทึกโน้ตลูกค้าเรียบร้อยแล้ว!", "#28a745");
            });
        }

        if (btnExportNotesCsv) {
            btnExportNotesCsv.addEventListener("click", async () => {
                let notes = {};
                try {
                    if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
                        const data = await chrome.storage.local.get(["pakhem_customer_notes"]);
                        notes = data.pakhem_customer_notes || {};
                    }
                } catch(e) {}
                if (Object.keys(notes).length === 0) {
                    try {
                        const raw = localStorage.getItem("pakhem_customer_notes");
                        if (raw) notes = JSON.parse(raw);
                    } catch(e) {}
                }

                const items = Object.values(notes);
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

        function showToast(msg, color="#28a745") {
            toast.innerHTML = msg;
            toast.style.color = color;
            toast.style.fontWeight = "bold";
        }

        // 🚀 ระบบแชร์ไลฟ์สดลงกลุ่มอัตโนมัติ 1-คลิก (Live Share Autopilot)
        async function executeAutoLiveShare() {
            let dialog = document.querySelector('div[role="dialog"]');

            // ถ้ายังไม่เปิดหน้าต่างแชร์ ให้ลองเปิดช่องโพสต์ของกลุ่ม
            if (!dialog) {
                const trigger = findCreatePostTrigger();
                if (trigger) {
                    showToast("⏳ กำลังเปิดหน้าต่างโพสต์ของกลุ่ม...", "#007bff");
                    simulateFullClick(trigger);
                    await new Promise(r => setTimeout(r, 1000));
                    dialog = document.querySelector('div[role="dialog"]');
                }
            }

            if (!dialog) {
                const captionText = CAPTIONS[currentCaptionIndex].text;
                try {
                    await navigator.clipboard.writeText(captionText);
                    showToast("📋 ก๊อปปี้แคปชั่นสำเร็จแล้ว! (กดปุ่มแชร์ใต้วิดีโอแล้ววางได้เลย)", "#28a745");
                } catch(e) {
                    showToast("⚠️ กรุณากดปุ่ม 'แชร์' ใต้วิดีโอไลฟ์สดก่อนจ้า", "#e67e22");
                }
                return;
            }

            const composer = dialog.querySelector('div[contenteditable="true"], div[role="textbox"]');
            if (!composer) {
                showToast("⚠️ ไม่พบช่องพิมพ์ข้อความในหน้าต่างแชร์", "#dc3545");
                return;
            }

            const captionText = CAPTIONS[currentCaptionIndex].text;

            showToast("⏳ กำลังใส่แคปชั่นปลาสลิดพร้อมราคา...", "#007bff");
            await insertTextIntoEditor(composer, captionText);

            try {
                await navigator.clipboard.writeText(captionText);
            } catch(e) {}

            await new Promise(r => setTimeout(r, 600));

            // ค้นหาปุ่มสีน้ำเงิน 'โพสต์' หรือ 'Post'
            const buttons = Array.from(dialog.querySelectorAll('div[role="button"], button'));
            const postBtn = buttons.find(b => {
                const txt = (b.textContent || '').trim();
                const aria = (b.getAttribute('aria-label') || '').trim();
                return (txt === 'โพสต์' || txt === 'Post' || aria === 'โพสต์' || aria === 'Post');
            });

            if (postBtn && !postBtn.getAttribute('aria-disabled')) {
                showToast("🚀 กำลังกดปุ่มแชร์ลงกลุ่มอัตโนมัติ...", "#28a745");
                simulateFullClick(postBtn);
                await new Promise(r => setTimeout(r, 1000));
                showToast("✅ แชร์ลงกลุ่มเรียบร้อยแล้วจ้า! (ไม่ต้องตามลบออก บอทจะคอยตอบแชทแทน 100%)", "#28a745");
            } else {
                showToast("✅ ใส่แคปชั่นเรียบร้อยแล้วจ้า! กดปุ่ม 'โพสต์' สีน้ำเงินได้เลย", "#28a745");
            }
        }

        const btnAutoShareLive = widget.querySelector("#pkh-btn-auto-share-live");
        if (btnAutoShareLive) {
            btnAutoShareLive.addEventListener("click", executeAutoLiveShare);
        }

        // อัปเดตสถานะสมาชิกกลุ่มแบบ Realtime (Safe Guard 100%)
        function updateGroupBadgeUI() {
            const pth = window.location.pathname || "";
            const isMsg = pth.includes('/messages') || pth.includes('/inbox');
            if (isMsg) return;

            try {
                const info = checkGroupMembership();
                if (groupTitle) groupTitle.textContent = info.name || "กลุ่ม Facebook";
                if (groupStatus) groupStatus.textContent = info.badgeText || "ตรวจสถานะ...";
                if (groupBadge) {
                    groupBadge.style.background = info.badgeBg || "#e8f5e9";
                    groupBadge.style.color = info.badgeColor || "#1b5e20";
                }

                const profileSpan = widget ? widget.querySelector("#pkh-profile-name") : null;
                if (profileSpan) {
                    profileSpan.textContent = "👤 " + (info.profileName || "ป้าเข็ม");
                }

                const btnAutoShareLive = widget ? widget.querySelector("#pkh-btn-auto-share-live") : null;
                if (info.status === "not_member") {
                    if (header) header.style.background = "#d9534f";
                    if (widget) widget.style.borderColor = "#d9534f";
                    if (headerText) headerText.textContent = "❌ ยังไม่ได้เข้าร่วมกลุ่ม";
                    if (groupBadge) {
                        groupBadge.style.cursor = "pointer";
                        groupBadge.title = "คลิกที่นี่เพื่อกดขอเข้าร่วมกลุ่ม";
                        groupBadge.onclick = () => {
                            if (info.joinElement) simulateFullClick(info.joinElement);
                        };
                    }
                    if (btnAutoShareLive) {
                        btnAutoShareLive.innerHTML = "👉 ยังไม่ได้เข้ากลุ่ม (คลิกเพื่อขอเข้าร่วมกลุ่ม)";
                        btnAutoShareLive.style.background = "#d9534f";
                        btnAutoShareLive.onclick = () => {
                            if (info.joinElement) simulateFullClick(info.joinElement);
                        };
                    }
                } else if (info.status === "pending") {
                    if (header) header.style.background = "#e67e22";
                    if (widget) widget.style.borderColor = "#e67e22";
                    if (headerText) headerText.textContent = "⏳ รอแอดมินอนุมัติ";
                    if (groupBadge) {
                        groupBadge.style.cursor = "default";
                        groupBadge.onclick = null;
                    }
                    if (btnAutoShareLive) {
                        btnAutoShareLive.innerHTML = "⏳ รอแอดมินกลุ่มอนุมัติ (ยังแชร์ไม่ได้)";
                        btnAutoShareLive.style.background = "#e67e22";
                        btnAutoShareLive.onclick = null;
                    }
                } else {
                    if (header) header.style.background = "linear-gradient(135deg, #1b5e20, #28a745)";
                    if (widget) widget.style.borderColor = "#28a745";
                    if (headerText) headerText.textContent = "🐟 ป้าเข็ม: ผู้ช่วยแชร์ลงกลุ่ม";
                    if (groupBadge) {
                        groupBadge.style.cursor = "default";
                        groupBadge.onclick = null;
                    }
                    if (btnAutoShareLive) {
                        btnAutoShareLive.innerHTML = "🚀 1-คลิก: ใส่แคปชั่น + แชร์ลงกลุ่มทันที!";
                        btnAutoShareLive.style.background = "linear-gradient(135deg, #e0245e, #ff416c)";
                        btnAutoShareLive.onclick = executeAutoLiveShare;
                    }
                }
            } catch(err) {
                // Silently fallback without logging to console.error
                if (groupTitle) groupTitle.textContent = (document.title || "").replace(/\s*[\|\-]\s*Facebook.*$/i, '').trim() || "กลุ่ม Facebook";
                if (groupStatus) groupStatus.textContent = "🟢 พร้อมแชร์ (สแตนด์บาย)";
                if (groupBadge) {
                    groupBadge.style.background = "#d4edda";
                    groupBadge.style.color = "#155724";
                }
            }
        }

        if (refreshStatusBtn) {
            refreshStatusBtn.addEventListener("click", (e) => {
                e.stopPropagation();
                updateGroupBadgeUI();
                showToast("🔄 ตรวจสอบสถานะกลุ่มใหม่แล้ว!", "#007bff");
            });
        }

        const customSearchInput = widget.querySelector("#pkh-custom-search");
        const goSearchBtn = widget.querySelector("#pkh-btn-go-search");

        function executeGroupSearch() {
            const kw = customSearchInput ? customSearchInput.value.trim() : "";
            if (kw) {
                const searchUrl = `https://www.facebook.com/search/groups/?q=${encodeURIComponent(kw)}`;
                window.open(searchUrl, "_blank");
                showToast(`🔍 กำลังค้นหากลุ่ม '${kw}' ในแท็บใหม่...`, "#007bff");
            } else {
                showToast("⚠️ กรุณาพิมพ์คำค้นหาก่อนครับ เช่น 'อาหารแห้ง'", "#e67e22");
            }
        }

        if (goSearchBtn) {
            goSearchBtn.addEventListener("click", executeGroupSearch);
        }
        if (customSearchInput) {
            customSearchInput.addEventListener("keydown", (e) => {
                if (e.key === "Enter") {
                    e.preventDefault();
                    executeGroupSearch();
                }
            });
        }


        const btnAutoAnswer = widget.querySelector("#pkh-btn-auto-answer");
        const btnHarvestCsv = widget.querySelector("#pkh-btn-harvest-csv");

        if (btnAutoAnswer) {
            btnAutoAnswer.addEventListener("click", () => {
                showToast("⏳ กำลังสแกนและตอบคำถามเข้ากลุ่ม...", "#007bff");
                const res = autoAnswerGroupQuestions();
                if (res.success) {
                    showToast(`✅ เติมคำตอบปลาสลิด + ติ๊กยอมรับกฎให้แล้ว (${res.count} ข้อ)! พร้อมส่งได้เลย`, "#28a745");
                } else {
                    showToast(res.msg || "💡 หากมีหน้าต่างคำถามเด้งขึ้นมา กดปุ่มนี้เพื่อตอบทันทีครับ", "#e67e22");
                }
            });
        }

        if (btnHarvestCsv) {
            btnHarvestCsv.addEventListener("click", () => {
                showToast("⏳ กำลังสแกนดูดรายชื่อกลุ่ม...", "#007bff");
                const res = scanAndExportGroupsToCsv();
                if (res.count > 0) {
                    showToast(`🎉 กวาดรายชื่อกลุ่มได้ ${res.count} กลุ่ม ดาวน์โหลดเป็น CSV สำเร็จ!`, "#28a745");
                } else {
                    showToast("ℹ️ ไม่พบกลุ่มในหน้านี้ (ให้พิมพ์ค้นหากลุ่มก่อนครับ)", "#e67e22");
                }
            });
        }

        // ตรวจสอบสถานะกลุ่มทุก 2 วินาที
        setInterval(updateGroupBadgeUI, 2000);
        updateGroupBadgeUI();

        if (selectGroup) {
            selectGroup.addEventListener("change", () => {
                const url = selectGroup.value;
                if (url) {
                    window.open(url, "_blank");
                    showToast("เปิดหน้ากลุ่มตลาดนัดในแท็บใหม่แล้วครับ!", "#28a745");
                    selectGroup.selectedIndex = 0;
                }
            });
        }

        // ลากย้ายตำแหน่ง
        let isDragging = false;
        let startX = 0, startY = 0;
        let startLeft = 0, startTop = 0;

        function onDragStart(clientX, clientY) {
            isDragging = true;
            const rect = widget.getBoundingClientRect();
            startLeft = rect.left;
            startTop = rect.top;
            startX = clientX;
            startY = clientY;

            widget.style.bottom = "auto";
            widget.style.right = "auto";
            widget.style.left = `${startLeft}px`;
            widget.style.top = `${startTop}px`;
        }

        function onDragMove(clientX, clientY) {
            if (!isDragging) return;
            const deltaX = clientX - startX;
            const deltaY = clientY - startY;

            let newLeft = startLeft + deltaX;
            let newTop = startTop + deltaY;

            newLeft = Math.max(10, Math.min(window.innerWidth - widget.offsetWidth - 10, newLeft));
            newTop = Math.max(10, Math.min(window.innerHeight - widget.offsetHeight - 10, newTop));

            widget.style.left = `${newLeft}px`;
            widget.style.top = `${newTop}px`;
        }

        function onDragEnd() {
            if (!isDragging) return;
            isDragging = false;
            const rect = widget.getBoundingClientRect();
            localStorage.setItem("pkh_widget_pos", JSON.stringify({
                left: Math.round(rect.left),
                top: Math.round(rect.top)
            }));
        }

        header.addEventListener("mousedown", (e) => {
            if (e.target.id === "pkh-toggle") return;
            onDragStart(e.clientX, e.clientY);
            const onMouseMove = (ev) => onDragMove(ev.clientX, ev.clientY);
            const onMouseUp = () => {
                onDragEnd();
                document.removeEventListener("mousemove", onMouseMove);
                document.removeEventListener("mouseup", onMouseUp);
            };
            document.addEventListener("mousemove", onMouseMove);
            document.addEventListener("mouseup", onMouseUp);
        });

        let isMinimized = false;
        toggleBtn.addEventListener("click", () => {
            isMinimized = !isMinimized;
            bodyDiv.style.display = isMinimized ? "none" : "block";
            toggleBtn.textContent = isMinimized ? "➕" : "➖";
        });

        if (randBtn) {
            randBtn.addEventListener("click", () => {
                currentCaptionIndex = (currentCaptionIndex + 1) % CAPTIONS.length;
                if (capTitle) capTitle.textContent = CAPTIONS[currentCaptionIndex].title;
                if (capArea) capArea.value = CAPTIONS[currentCaptionIndex].text;
                showToast(`🎲 สลับใช้: ${CAPTIONS[currentCaptionIndex].title}`, "#007bff");
            });
        }

        // ==============================================================
        // 🚀 ระบบโพสต์อัตโนมัติ (ตรวจสอบสถานะกลุ่มก่อนโพสต์ทุกครั้ง)
        // ==============================================================
        if (insertBtn) insertBtn.addEventListener("click", async () => {
            const textToInsert = capArea.value.trim();

            // ⚡ สเต็ป 0: ตรวจสอบก่อนว่าอยู่ในกลุ่มไหม และเป็นสมาชิกหรือยัง
            const membership = checkGroupMembership();
            if (membership.status === "not_member") {
                header.style.background = "#d9534f";
                headerText.textContent = "❌ ยังไม่ได้เข้าร่วมกลุ่ม";
                showToast("⚠️ <b>บัญชีนี้ยังไม่ได้เข้าร่วมกลุ่มนี้ครับ!</b><br>👉 กำลังคลิกปุ่ม <b>'เข้าร่วมกลุ่ม'</b> ให้ทันที...", "#d9534f");
                if (membership.joinElement) {
                    simulateFullClick(membership.joinElement);
                } else {
                    window.scrollTo({ top: 0, behavior: 'smooth' });
                }
                return;
            }

            if (membership.status === "pending") {
                header.style.background = "#e67e22";
                headerText.textContent = "⏳ รอแอดมินอนุมัติ";
                showToast("⚠️ กลุ่มนี้ส่งคำขอเข้าร่วมแล้ว แต่<b>กำลังรอแอดมินอนุมัติ</b> จึงยังไม่สามารถโพสต์ได้ครับ", "#e67e22");
                return;
            }

            // สเต็ปแรก: ก๊อปปี้รูปป้ายราคาเข้า Windows Clipboard ทันที
            if (cachedPricePngBlob) {
                copyPngBlobToClipboard(cachedPricePngBlob);
            }

            insertBtn.disabled = true;
            insertBtn.style.opacity = "0.7";
            header.style.background = "#007bff";
            headerText.textContent = "⏳ กำลังดำเนินการ...";

            // สเต็ปแท็บการสนทนา
            const discussionTab = document.querySelector('a#posts[role="tab"]') ||
                                  Array.from(document.querySelectorAll('a[role="tab"], div[role="tab"]')).find(t => {
                                      const txt = t.textContent ? t.textContent.trim() : "";
                                      return txt.includes("การสนทนา") || txt.includes("Discussion");
                                  });

            if (discussionTab && discussionTab.getAttribute("aria-selected") !== "true") {
                showToast("⏳ 1/6 สลับไปแท็บ 'การสนทนา'...", "#007bff");
                discussionTab.click();
                await new Promise(r => setTimeout(r, 1200));
            }

            showToast("⏳ 2/6 ค้นหากล่องสร้างโพสต์...", "#007bff");

            // ตรวจสอบว่าไดอะล็อกเปิดอยู่แล้วหรือไม่
            let dialog = document.querySelector('div[role="dialog"]');
            let composer = dialog ? dialog.querySelector('div[contenteditable="true"]') : null;

            // ถ้าไดอะล็อกยังไม่เปิด ให้ค้นหาปุ่ม "เขียนอะไรสักหน่อย...." แล้วคลิกเปิด
            if (!dialog || !composer) {
                const trigger = findCreatePostTrigger();
                if (trigger) {
                    showToast("⏳ 3/6 คลิกเปิดกล่อง 'เขียนอะไรสักหน่อย'...", "#007bff");
                    simulateFullClick(trigger);

                    for (let w = 0; w < 20; w++) {
                        await new Promise(r => setTimeout(r, 250));
                        dialog = document.querySelector('div[role="dialog"]');
                        if (dialog) {
                            composer = dialog.querySelector('div[contenteditable="true"]');
                            if (composer) break;
                        }
                    }
                }
            }

            if (!dialog || !composer) {
                header.style.background = "#e67e22";
                headerText.textContent = "💡 คลิกกล่องโพสต์ 1 ที";
                showToast("👉 กรุณาคลิกที่กล่อง <b>'เขียนอะไรสักหน่อย....'</b> บนหน้าจอ 1 ครั้ง<br>แล้วกดปุ่มสีเขียวนี้ใหม่อีกครั้งครับ!", "#e67e22");
                insertBtn.disabled = false;
                insertBtn.style.opacity = "1";
                return;
            }

            // สเต็ปพิมพ์ข้อความแคปชั่น
            showToast("⏳ 4/6 กำลังพิมพ์ข้อความราคา 3 บรรทัด...", "#007bff");
            await insertTextIntoEditor(composer, textToInsert);
            await new Promise(r => setTimeout(r, 400));

            // ตรวจสอบไฟล์รูปภาพ
            if (!cachedPriceFile) {
                try {
                    const res = await fetch(IMAGES.price, { mode: 'cors' });
                    const blob = await res.blob();
                    cachedPriceFile = new File([blob], "pakhem_fish_price.jpg", { type: "image/jpeg" });
                } catch(e) {}
            }

            // คลิกเปิดพื้นที่ "รูปภาพ/วิดีโอ" ในไดอะล็อก
            showToast("⏳ 5/6 กำลังเปิดพื้นที่แนบรูปภาพ...", "#007bff");
            const photoButton = Array.from(dialog.querySelectorAll('div[role="button"], span, div')).find(el => {
                const label = el.getAttribute('aria-label') || '';
                const txt = el.textContent || '';
                return (label.includes('รูปภาพ') || label.includes('Photo') || txt.includes('รูปภาพ/วิดีโอ')) &&
                       !label.includes('แก้ไข') && !label.includes('เอาสื่อออก');
            });

            if (photoButton) {
                photoButton.click();
                await new Promise(r => setTimeout(r, 700));
            }

            // แนบไฟล์รูปภาพเข้าสู่ <input type="file"> ภายในไดอะล็อก
            showToast("⏳ 6/6 กำลังแนบรูปป้ายราคา...", "#007bff");
            if (cachedPriceFile) {
                const dt = new DataTransfer();
                dt.items.add(cachedPriceFile);

                const dialogFileInputs = Array.from(dialog.querySelectorAll('input[type="file"]') || []);
                dialogFileInputs.forEach(input => {
                    try {
                        const proto = HTMLInputElement.prototype;
                        const nativeFilesSetter = Object.getOwnPropertyDescriptor(proto, 'files')?.set;
                        if (nativeFilesSetter) {
                            nativeFilesSetter.call(input, dt.files);
                        } else {
                            input.files = dt.files;
                        }
                        if (input._valueTracker) input._valueTracker.setValue('');
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                    } catch(e) {}
                });

                try {
                    ['dragenter', 'dragover', 'drop'].forEach(evtType => {
                        const dragEvt = new DragEvent(evtType, {
                            bubbles: true,
                            cancelable: true,
                            dataTransfer: dt
                        });
                        composer.dispatchEvent(dragEvt);
                        dialog.dispatchEvent(dragEvt);
                    });
                } catch(e) {}
            }

            // ตรวจสอบสถานะว่ารูปภาพขึ้นหรือยัง
            let hasImage = false;
            for (let c = 0; c < 12; c++) {
                await new Promise(r => setTimeout(r, 300));
                if (isImagePreviewPresent(dialog)) {
                    hasImage = true;
                    break;
                }
            }

            // Failsafe: หากเบราว์เซอร์บล็อกการยัดรูปอัตโนมัติ ให้ผู้ใช้กด Ctrl+V เพียง 1 ที
            if (!hasImage) {
                header.style.background = "#e67e22";
                widget.style.borderColor = "#e67e22";
                headerText.textContent = "⚡ ข้อความพิมพ์แล้ว! (กด Ctrl+V เพื่อวางรูป)";
                showToast("✍️ <b>ข้อความพิมพ์แล้ว!</b> 👉 <b>กดปุ่ม [ Ctrl + V ] 1 ทีครับ!</b><br>(รูปป้ายราคาอยู่ในคลิปบอร์ดแล้ว วางปุ๊บ บอทจะกดโพสต์ให้เองทันที)", "#e67e22");
                composer.focus();

                for (let wait = 0; wait < 60; wait++) {
                    await new Promise(r => setTimeout(r, 350));
                    if (isImagePreviewPresent(dialog)) {
                        hasImage = true;
                        break;
                    }
                }
            }

            // กดยืนยันโพสต์เมื่อรูปภาพปรากฏเท่านั้น
            if (hasImage) {
                header.style.background = "#28a745";
                widget.style.borderColor = "#28a745";
                headerText.textContent = "🚀 รูปและข้อความพร้อมแล้ว! กำลังโพสต์...";
                showToast("🎉 ครบทั้งข้อความและรูปภาพแล้ว! กำลังกดปุ่ม 'โพสต์'...", "#28a745");
                await new Promise(r => setTimeout(r, 800));

                const postBtn = dialog.querySelector('div[aria-label="โพสต์"][role="button"]') ||
                                Array.from(dialog.querySelectorAll('div[role="button"]')).find(b => {
                                    const t = b.textContent ? b.textContent.trim() : "";
                                    return t === "โพสต์" || t === "Post";
                                });

                if (postBtn && postBtn.getAttribute("aria-disabled") !== "true") {
                    postBtn.click();
                    showToast("✅ โพสต์พร้อมรูปภาพป้ายราคาขึ้นกลุ่มสำเร็จ 100% แล้วครับ!", "#28a745");
                    headerText.textContent = "✅ โพสต์สำเร็จเรียบร้อย!";
                } else {
                    showToast("💡 ครบทั้งข้อความและรูปภาพแล้ว! กดปุ่มโพสต์สีน้ำเงินได้เลยครับ", "#007bff");
                }
            }

            insertBtn.disabled = false;
            insertBtn.style.opacity = "1";
        });

        if (copyImgBtn) {
            copyImgBtn.addEventListener("click", async () => {
                showToast("⏳ กำลังดึงรูปป้ายราคาลงคลิปบอร์ด...", "#007bff");
                if (!cachedPricePngBlob) {
                    await prefetchImageBlobs();
                }
                const ok = await copyPngBlobToClipboard(cachedPricePngBlob);
                if (ok) {
                    showToast("🖼️ ก๊อปรูปป้ายราคาลงคลิปบอร์ดแล้ว! (กด Ctrl+V วางได้ทันที)", "#28a745");
                } else {
                    showToast("❌ เบราว์เซอร์ปฏิเสธคลิปบอร์ด ลองคลิกปุ่มอีกครั้งครับ", "#d9534f");
                }
            });
        }

        if (copyFriedBtn) {
            copyFriedBtn.addEventListener("click", async () => {
                showToast("⏳ กำลังดึงรูปปลาทอดลงคลิปบอร์ด...", "#6f42c1");
                if (!cachedFriedPngBlob) {
                    await prefetchImageBlobs();
                }
                const ok = await copyPngBlobToClipboard(cachedFriedPngBlob);
                if (ok) {
                    showToast("🍳 ก๊อปรูปปลาทอดลงคลิปบอร์ดแล้ว! (กด Ctrl+V วางในเม้นต์ได้)", "#6f42c1");
                } else {
                    showToast("❌ เบราว์เซอร์ปฏิเสธคลิปบอร์ด ลองคลิกปุ่มอีกครั้งครับ", "#d9534f");
                }
            });
        }

        if (copyTextBtn) {
            copyTextBtn.addEventListener("click", async () => {
                const text = (CAPTIONS && CAPTIONS[currentCaptionIndex]) ? CAPTIONS[currentCaptionIndex].text : "";
                try {
                    await navigator.clipboard.writeText(text);
                    showToast("📋 ก๊อปปี้ข้อความแคปชั่นเรียบร้อยแล้วครับ!", "#28a745");
                } catch(e) {
                    showToast("❌ ก๊อปปี้ไม่สำเร็จ", "#d9534f");
                }
            });
        }
    }

    prefetchImageBlobs();

    window.addEventListener("load", () => {
        setTimeout(createWidget, 2000);
    });
    setInterval(createWidget, 3500);

// ==============================================================
    // 📡 Chrome Message Passing (รับคำสั่งจาก popup.js)
    // ==============================================================
    if (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.onMessage) {
        chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
            if (request.action === 'GET_GROUP_STATUS') {
                const info = checkGroupMembership();
                sendResponse(info);
                return true;
            }

            if (request.action === 'START_POST') {
                const widget = document.getElementById('pakhem-group-helper');
                const insertBtn = widget ? widget.querySelector('#pkh-btn-insert') : null;
                if (insertBtn) {
                    insertBtn.click();
                    sendResponse({ status: 'started' });
                } else {
                    sendResponse({ status: 'error', msg: 'ไม่พบวิดเจ็ตโพสต์' });
                }
                return true;
            }

            if (request.action === 'ANSWER_QUESTIONS') {
                const res = autoAnswerGroupQuestions();
                sendResponse(res);
                return true;
            }

            if (request.action === 'HARVEST_CSV') {
                const res = scanAndExportGroupsToCsv();
                sendResponse(res);
                return true;
            }
        });
    }

})();
