# -*- coding: utf-8 -*-
"""reels_uploader/master_template_config.py — สเปกแม่แบบมาตรฐานระดับสตูดิโอ (Golden Master Template)
ล็อกขนาด พิกัด ระยะห่าง ขีดจำกัดตัวอักษร ธีมสี และความเร็วเสียงพากย์ TTS ไว้อย่างตายตัว
เพื่อให้การสร้างวิดีโอ 9:16 (1080x1920) เป็นเรื่องง่าย แม่นยำ และไม่ผิดเพี้ยน 100%
"""
from typing import Dict, Tuple, List, Optional
import re

# ----------------------------------------------------------------------
# 1. ความละเอียดและมิติของหน้าจอ (Canvas Dimensions: 9:16 Full HD)
# ----------------------------------------------------------------------
CANVAS_W = 1080
CANVAS_H = 1920

# ----------------------------------------------------------------------
# 2. ข้อกำหนดพิกัดและระยะห่างของแต่ละโซน (Master Zone Specifications)
# ----------------------------------------------------------------------
# โซนที่ 1: ป้ายหมวดหมู่บนสุด (Top Category Badge Pill)
BADGE_CONFIG = {
    "w": 440,
    "h": 46,
    "y": 90,             # พิกัดแนวตั้ง Y=90 ถึง Y=136 (เว้นระยะปลอดภัย ไม่ทับหัวข้อข่าว 100%)
    "radius": 23,        # ขอบมนสมบูรณ์แบบ (Capsule)
    "border_w": 2,       # เส้นขอบสีขาวหนา 2px
    "font_size": 23,     # ขนาดฟอนต์ Leelawadee Bold
    "max_chars": 26,     # ขีดจำกัดตัวอักษรบนป้าย
}

# โซนที่ 2: พาดหัว Hook 3 วินาทีหยุดนิ้ว (Viral Hook Headline)
HOOK_CONFIG = {
    "y_min": 160,
    "y_max": 315,
    "max_chars": 45,             # ล็อกความยาวไม่เกิน 45 ตัวอักษร
    "max_chars_per_line": 22,    # ตัดบรรทัดไม่เกิน 22 ตัวอักษร
    "font_size_1_2_lines": 48,   # กรณีมี 1-2 บรรทัด ฟอนต์ใหญ่ 48px
    "line_spacing_1_2": 56,      # ระยะห่างบรรทัดกรณี 1-2 บรรทัด
    "font_size_3_lines": 38,     # กรณีมี 3 บรรทัด ย่อฟอนต์เป็น 38px
    "line_spacing_3": 46,        # ระยะห่างบรรทัดกรณี 3 บรรทัด
    "color_phase1": (255, 235, 59),  # สีเหลืองสดดึงดูดสายตาในเฟส 1
    "color_phase2_3": (255, 255, 255),# สีขาวคมชัดในเฟส 2 และ 3
    "shadow_offsets": [(-3, -3), (3, -3), (-3, 3), (3, 3), (0, 4), (0, -4)], # เงาดำ 4 ทิศ
}

# โซนที่ 3: กรอบภาพถ่ายจริง 100% (Hero Media Frame — ปรับขนาด 960x500 ยืดหยุ่น ไร้การบีบอัด ไม่ชนพาดหัว)
HERO_FRAME_CONFIG = {
    "w": 960,
    "h": 500,                    # ขนาด 960x500 สัดส่วนภาพกว้างมาตรฐาน ไร้การเบียดบดบัง
    "x": (CANVAS_W - 960) // 2,  # x = 60
    "y": 350,                    # y = 350 ถึง y = 850
    "radius": 24,                # ขอบมน 24px
    "border_w": 3,               # เส้นขอบคมชัดหนา 3px
    "border_color": (255, 255, 255, 220), # สีขาวโปร่งแสงพรีเมียม
}

# โซนที่ 4: กล่องการ์ดสาระสำคัญ 3 ข้อ (Frosted Glass Infographic Container)
CARD_CONTAINER_CONFIG = {
    "w": 960,
    "h": 600,
    "x": (CANVAS_W - 960) // 2,  # x = 60
    "y": 880,                    # y = 880 ถึง y = 1480
    "radius": 26,                # ขอบมน 26px
    "border_w": 3,
    "header_x_offset": 36,       # ระยะจากขอบซ้ายการ์ด (x = 96)
    "header_y_offset": 32,       # ระยะจากขอบบนการ์ด
    "header_font_size": 26,      # ขนาดฟอนต์หัวข้อ
    "header_color": (226, 232, 240), # สีเทาสว่าง Slate
}

# รายละเอียดย่อย: แถวสาระสำคัญ 3 แถว (3 Step Rows)
STEP_ROW_CONFIG = {
    "w": 888,
    "h": 130,                    # ความสูงแถวละ 130px
    "gap": 16,                   # ระยะเว้นระหว่างแถว 16px
    "radius": 18,                # ขอบมนแถว 18px
    "start_y": 945,              # แถว 1: 945-1075, แถว 2: 1091-1221, แถว 3: 1237-1367
    "num_box_w": 56,
    "num_box_h": 56,
    "num_box_radius": 14,
    "num_font_size": 32,
    "text_x_offset": 96,         # จุดเริ่มตัวหนังสือ (rx + 96)
    "max_text_w": 760,           # พื้นที่ความกว้างของข้อความ
    "max_chars": 45,             # ล็อกความยาวตัวอักษร 20-45 ตัวอักษร
    "max_chars_per_line": 24,    # ตัดบรรทัดละ 24 ตัวอักษร
    # ขนาดฟอนต์และระยะบรรทัดตามจำนวนบรรทัด
    "font_size_1line": 35,
    "font_size_2lines": 34,
    "line_spacing_2lines": 44,
    "font_size_3lines": 28,
    "line_spacing_3lines": 35,
}

# โซนที่ 5: แถบกระตุ้นการดำเนินการท้ายคลิป (Safe Action Bar Footer)
FOOTER_CONFIG = {
    "x1": 60,
    "y1": 1515,
    "x2": CANVAS_W - 60,         # x2 = 1020
    "y2": 1605,                  # สูง 90px (y=1515..1605 เว้นพื้นที่ปลอดภัยด้านล่าง 315px ปลอดภัยจากปุ่ม TikTok/Shorts 100%)
    "radius": 24,
    "border_w": 2,
    "border_color": (34, 197, 94),   # เขียวมรกตสดใส
    "bg_color": (15, 23, 42),        # สีกรมท่าเข้มหรูหรา
    "font_size": 28,
    "text_color": (74, 222, 128),
}

# ----------------------------------------------------------------------
# 3. ข้อกำหนดเสียงพากย์ AI TTS (Voiceover Pacing Specification)
# ----------------------------------------------------------------------
TTS_CONFIG = {
    "voice": "th-TH-PremwadeeNeural",  # เสียงป้าเข็มหลัก คมชัด เป็นธรรมชาติ
    "voice_alt": "th-TH-NiwatNeural",  # เสียงสำรองกรณีผู้ชาย
    "rate": "+0%",                     # ความเร็วมาตรฐาน 100% พูดธรรมชาติระดับสตูดิโอ (ห้ามเร่งเสียง)
    "volume": 1.0,
    "min_video_duration": 5.5,         # ความยาวขั้นต่ำ 5.5 วินาที
    "audio_tail_buffer": 0.4,          # ปล่อยหางเสียง +0.4 วินาที ไม่ตัดคำจบ
}

# ----------------------------------------------------------------------
# 4. จานสีมาตรฐาน 6 หมวดคอนเทนต์ (Master Color Themes)
# ----------------------------------------------------------------------
THEME_PALETTES = {
    "TRENDING_NEWS": {
        "name": "ข่าวด่วนกระแสสังคม",
        "badge_bg": (220, 38, 38),       # Crimson Red
        "badge_txt": "สรุปข่าวด่วนวันนี้",
        "card_bg": (15, 23, 42, 240),
        "card_border": (239, 68, 68, 200),
        "active_row_bg": (185, 28, 28),
        "active_border": (254, 202, 202),
        "active_num_bg": (255, 255, 255),
        "active_num_txt": (185, 28, 28),
        "glow_col": (255, 240, 0),
        "hook_col": (255, 235, 59),
        "header_txt": "• สาระสำคัญของข่าวที่ต้องรู้",
    },
    "CELEBRITY_TREND": {
        "name": "กระแสไวรัลคนดัง",
        "badge_bg": (220, 38, 38),       # Crimson Red (ตามแม่แบบมาตรฐาน)
        "badge_txt": "สรุปประเด็นดารา",
        "card_bg": (15, 23, 42, 240),
        "card_border": (239, 68, 68, 200),
        "active_row_bg": (185, 28, 28),
        "active_border": (254, 202, 202),
        "active_num_bg": (255, 255, 255),
        "active_num_txt": (185, 28, 28),
        "glow_col": (255, 240, 0),
        "hook_col": (255, 235, 59),
        "header_txt": "• สาระสำคัญของข่าวที่ต้องรู้",
    },
    "LUCKY_FORTUNE": {
        "name": "เลขเด็ด & ดวงมงคล",
        "badge_bg": (202, 138, 4),       # Imperial Gold
        "badge_txt": "เลขเด็ด & ดวงมงคล",
        "card_bg": (35, 20, 10, 240),
        "card_border": (250, 204, 21, 200),
        "active_row_bg": (180, 83, 9),
        "active_border": (254, 240, 138),
        "active_num_bg": (255, 255, 255),
        "active_num_txt": (180, 83, 9),
        "glow_col": (255, 255, 255),
        "hook_col": (255, 235, 59),
        "header_txt": "• แนวทางตัวเลขและเคล็ดลับเสริมดวง",
    },
    "LIFE_HACK_TIP": {
        "name": "ทริคแม่บ้านแก้ปัญหา",
        "badge_bg": (16, 185, 129),      # Emerald Green
        "badge_txt": "ทริคแม่บ้านแก้ปัญหา",
        "card_bg": (6, 35, 25, 240),
        "card_border": (52, 211, 153, 200),
        "active_row_bg": (5, 150, 105),
        "active_border": (209, 250, 229),
        "active_num_bg": (255, 255, 255),
        "active_num_txt": (5, 150, 105),
        "glow_col": (255, 240, 0),
        "hook_col": (255, 235, 59),
        "header_txt": "• ขั้นตอนง่ายๆ แก้ปัญหาได้ใน 1 นาที",
    },
    "WORK_PRODUCTIVITY": {
        "name": "ทริคคนทำงานออฟฟิศ",
        "badge_bg": (6, 182, 212),       # Ocean Cyan
        "badge_txt": "ทริคคนทำงานออฟฟิศ",
        "card_bg": (10, 30, 45, 240),
        "card_border": (34, 211, 238, 200),
        "active_row_bg": (14, 116, 144),
        "active_border": (207, 250, 254),
        "active_num_bg": (255, 255, 255),
        "active_num_txt": (14, 116, 144),
        "glow_col": (255, 235, 59),
        "hook_col": (255, 235, 59),
        "header_txt": "• เทคนิคทำงานไว เลิกงานตรงเวลา",
    },
    "PRODUCT_PROMO": {
        "name": "สินค้าของแท้ 100% (Shopee)",
        "badge_bg": (238, 77, 45),       # Shopee Orange
        "badge_txt": "ของดีบอกต่อ แท้ 100%",
        "card_bg": (35, 20, 15, 240),
        "card_border": (251, 146, 60, 200),
        "active_row_bg": (217, 72, 39),
        "active_border": (254, 215, 170),
        "active_num_bg": (255, 255, 255),
        "active_num_txt": (217, 72, 39),
        "glow_col": (255, 235, 59),
        "hook_col": (255, 235, 59),
        "header_txt": "• จุดเด่นที่ต้องมีติดบ้านไว้",
    }
}

# ----------------------------------------------------------------------
# 5. ฟังก์ชันทำความสะอาดและตรวจสอบข้อความตามแม่แบบ (Master Text Utilities)
# ----------------------------------------------------------------------
def clean_master_text(text: str) -> str:
    """ลบอักขระพิเศษ อิโมจิสี และช่องว่างส่วนเกินที่ทำให้เกิดกล่องสี่เหลี่ยม □ หรือสระลอย"""
    if not text:
        return ""
    cleaned = re.sub(r'<[^>]+>', ' ', text)
    cleaned = re.sub(r'https?://\S+', '', cleaned)
    cleaned = re.sub(r"[\U00010000-\U0010ffff]", "", cleaned)
    cleaned = re.sub(r"[\u2600-\u27ff]", "", cleaned)
    cleaned = re.sub(r"[\u2300-\u23ff]", "", cleaned)
    cleaned = re.sub(r"[\u2b50-\u2b55]", "", cleaned)
    cleaned = re.sub(r"[\ufe0e\ufe0f]", "", cleaned)
    for c in ["🚨", "🔴", "💬", "👇", "💡", "🌟", "🔮", "💼", "🏠", "✨", "🦛", "📌", "👉", "🔥", "⚠️", "“", "”", '"', "'"]:
        cleaned = cleaned.replace(c, "")
    cleaned = re.sub(r'#+\s*', '', cleaned)
    cleaned = re.sub(r'[*_~`]+', '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def format_master_hook(text: str, max_chars: int = HOOK_CONFIG["max_chars"]) -> str:
    """จัดรูปแบบข้อความ Hook ให้อยู่ในโควต้าไม่เกิน 45 ตัวอักษร สมบูรณ์ในตัวเอง ไม่ค้างคาคำเชื่อม"""
    cleaned = clean_master_text(text)
    if not cleaned:
        return ""

    if len(cleaned) <= max_chars + 4:
        return re.sub(r'[\s=\-–—:_\"\'\(\[“]+$', '', cleaned).strip()

    try:
        from pythainlp.tokenize import word_tokenize
        tokens = word_tokenize(cleaned, engine="newmm")
        res = ""
        for t in tokens:
            if len(res) + len(t) <= max_chars + 3:
                res += t
            else:
                break
        res = res if res else cleaned[:max_chars]
    except Exception:
        res = cleaned[:max_chars].rsplit(" ", 1)[0]

    res = re.sub(r'[\s=\-–—:_\"\'\(\[“]+$', '', res).strip()
    res = re.sub(r'(?:เพื่อ|ที่|และ|หรือ|กับ|ว่า|คือ|จะ|ใน|ของ|จาก|สำหรับ|เมื่อ|ให้|โดย|ถึง|ที่จังหวัด|จังหวัด|อำเภอ|ตำบล)$', '', res).strip()
    res = re.sub(r'[\s=\-–—:_\"\'\(\[“]+$', '', res).strip()
    return res


def format_master_step(text: str, max_chars: int = STEP_ROW_CONFIG["max_chars"]) -> str:
    """จัดรูปแบบข้อความสาระสำคัญให้อยู่ในโควต้า 20-45 ตัวอักษร สมบูรณ์ในตัวเอง ไม่ค้างคาคำเชื่อม"""
    cleaned = clean_master_text(text)
    if not cleaned:
        return ""

    if len(cleaned) <= max_chars + 4:
        res = cleaned
    else:
        # หากยาวเกินโควต้า ให้ตัดด้วย PyThaiNLP ตามขอบเขตคำ
        try:
            from pythainlp.tokenize import word_tokenize
            tokens = word_tokenize(cleaned, engine="newmm")
            res = ""
            for t in tokens:
                if len(res) + len(t) <= max_chars + 3:
                    res += t
                else:
                    break
            res = res if res else cleaned[:max_chars]
        except Exception:
            res = cleaned[:max_chars].rsplit(" ", 1)[0]

    # ลบคำเชื่อมและคำค้างคาที่ปลายข้อความเสมอ (ทั้งสั้นและยาว)
    res = re.sub(r'[\s=\-–—:_\"\'\(\[“]+$', '', res).strip()
    res = re.sub(r'(?:เพื่อ|ที่|และ|หรือ|กับ|ว่า|คือ|จะ|ใน|ของ|จาก|สำหรับ|เมื่อ|ให้|โดย|ถึง|อย่าง|จน|เป็น|อายุ|ซึ่ง|แก่|แด่|ต่อ|ที่จังหวัด|จังหวัด|อำเภอ|ตำบล)$', '', res).strip()
    res = re.sub(r'[\s=\-–—:_\"\'\(\[“]+$', '', res).strip()
    return res


def validate_master_inputs(
    hook: str,
    steps: List[str],
    mode: str = "LIFE_HACK_TIP"
) -> Tuple[bool, List[str]]:
    """ตรวจสอบว่าข้อมูลที่จะนำไปสร้างวิดีโอตรงตามแม่แบบมาตรฐานหรือไม่"""
    errors = []
    if not hook or len(clean_master_text(hook)) < 5:
        errors.append("ข้อความ Hook ต้องมีความยาวอย่างน้อย 5 ตัวอักษร")
    elif len(clean_master_text(hook)) > HOOK_CONFIG["max_chars"]:
        errors.append(f"ข้อความ Hook ยาวเกินแม่แบบ ({len(clean_master_text(hook))} > {HOOK_CONFIG['max_chars']} ตัวอักษร)")

    if len(steps) < 3:
        errors.append("ต้องมีสาระสำคัญครบ 3 ข้อ")
    else:
        for idx, s in enumerate(steps[:3]):
            s_clean = clean_master_text(s)
            if not s_clean or len(s_clean) < 5:
                errors.append(f"ข้อที่ {idx + 1} สั้นเกินไป (ต้องอย่างน้อย 5 ตัวอักษร)")
            elif len(s_clean) > STEP_ROW_CONFIG["max_chars"]:
                errors.append(f"ข้อที่ {idx + 1} ยาวเกินสเปกแม่แบบ ({len(s_clean)} > {STEP_ROW_CONFIG['max_chars']} ตัวอักษร)")

    if mode not in THEME_PALETTES:
        errors.append(f"หมวดหมู่ {mode} ไม่อยู่ในระบบ (หมวดที่รองรับ: {list(THEME_PALETTES.keys())})")

    return (len(errors) == 0, errors)
