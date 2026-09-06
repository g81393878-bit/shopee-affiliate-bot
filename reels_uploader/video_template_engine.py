# -*- coding: utf-8 -*-
"""video_template_engine.py — เทมเพลตมาตรฐานสำหรับผลิตวิดีโอ 9:16 Cinematic & Mute-First 100%
รองรับทั้ง 5 เสาหลักคอนเทนต์เพียว (ข่าว, คนดัง, เลขมงคล, ทริคแม่บ้าน, ทริคทำงาน) และสินค้า Shopee

หลักการออกแบบระดับสตูดิโอ (Golden Standard):
1. 🎨 Ambient Cinematic Backdrop: ใช้ภาพจริงเบลอ Gaussian Blur (radius=32) ผสม Overlay เข้ม เพื่อเติมเต็มจอ 1080x1920 ไร้ขอบดำว่างเปล่า 100%
2. 📸 Crystal-Clear Hero Media Frame: วางภาพถ่ายจริง 100% ในกรอบโค้งมน 960x660px พร้อมขอบสีสว่างและเงา มั่นใจไม่ตัดหัวคน และไม่ผิดสัดส่วน
3. 🪝 3-Second Viral Hook: ป้ายประเภทคอนเทนต์ + ข้อความ Hook 3 วิ ตัวโตสีเหลือง/ขาว ตัดขอบดำ 4 ทิศทาง หยุดนิ้วคนดู 100%
4. 💡 Dynamic 3-Step Progressive Insight Card (สำหรับคนปิดเสียงดู): แสดงการ์ดสรุปสาระสำคัญ 3 ข้อ และวิ่งสลับไฟไฮไลท์สว่างสดใสตามจังหวะ (Phase 1 -> Phase 2 -> Phase 3)
5. 🛡️ Safe Zone Action Bar: แถบ CTA ด้านล่างสุด (y=1680-1780) ปลอดภัยจากการถูกปุ่ม TikTok / Shorts บดบัง 100%
"""
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent
REELS_DIR = Path(__file__).resolve().parent

import auto_product_reels
FONT_BOLD, FONT_REG = auto_product_reels._resolve_fonts()

import master_template_config as mtc

THEME_PALETTES = mtc.THEME_PALETTES
CANVAS_W = mtc.CANVAS_W
CANVAS_H = mtc.CANVAS_H


def get_font(font_path: Path, size: int) -> ImageFont.FreeTypeFont:
    return auto_product_reels.get_font(font_path, size)



# ----------------------------------------------------------------------
# 2. Text Utilities (PyThaiNLP Tokenization & No Syllable Butchering)
# ----------------------------------------------------------------------
def clean_render_text(text: str) -> str:
    """ลบอิโมจิ, HTML tags, และอักขระพิเศษที่ทำให้ Pillow แสดงผลเป็นกล่องสี่เหลี่ยม □"""
    if not text:
        return ""
    cleaned = re.sub(r'<[^>]+>', ' ', text)
    cleaned = re.sub(r'https?://\S+', '', cleaned)
    cleaned = re.sub(r"[\U00010000-\U0010ffff]", "", cleaned)
    cleaned = re.sub(r"[\u2600-\u27ff]", "", cleaned)
    cleaned = re.sub(r"[\u2300-\u23ff]", "", cleaned)
    cleaned = re.sub(r"[\u2b50-\u2b55]", "", cleaned)
    cleaned = re.sub(r"[\ufe0e\ufe0f]", "", cleaned)
    for c in ["🚨", "🔴", "💬", "👇", "💡", "🌟", "🔮", "💼", "🏠", "✨", "🦛", "📌", "👉", "🔥", "⚠️"]:
        cleaned = cleaned.replace(c, "")
    cleaned = re.sub(r'#+\s*', '', cleaned)
    cleaned = re.sub(r'[*_~`]+', '', cleaned)
    cleaned = re.sub(r'ข่าว[อฮด]ื่น\s*ๆ.*', '', cleaned)
    cleaned = re.sub(r'\b(?:judging|contest|singing|season|show|am star)\b', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def wrap_thai_lines(text: str, max_chars_per_line: int = 24, max_lines: int = 4) -> List[str]:
    """ตัดข้อความภาษาไทยเป็นบรรทัดตามขอบเขตคำ PyThaiNLP ป้องกันตัดกลางคำเด็ดขาด"""
    text = clean_render_text(text)
    if not text:
        return []

    # ตัดตรงเครื่องหมายวรรคตอนสำคัญก่อน
    for punct in ["!", "?", "•", " :", ":"]:
        if punct in text:
            parts = text.split(punct, 1)
            p1 = parts[0].strip() + (punct if punct not in ("•", " :", ":") else "")
            p2 = parts[1].strip()
            if 3 <= len(p1) <= max_chars_per_line and len(p2) >= 3:
                wrapped_p2 = wrap_thai_lines(p2, max_chars_per_line=max_chars_per_line, max_lines=max_lines - 1)
                return [p1] + wrapped_p2

    try:
        from pythainlp.tokenize import word_tokenize
        tokens = word_tokenize(text, engine="newmm")
    except Exception:
        tokens = text.split(" ")

    lines, cur = [], ""
    for t in tokens:
        if len(cur) + len(t) <= max_chars_per_line:
            cur += t
        else:
            if cur:
                lines.append(cur)
            cur = t
    if cur:
        lines.append(cur)
    if max_lines and len(lines) > max_lines:
        return lines[:max_lines]
    return lines


def clean_thai_sentence_end(text: str, max_chars: int = 50) -> str:
    """ตัดคำที่ค้างคาที่ปลายประโยคภาษาไทย เช่น เพื่อ, ที่, และ, หรือ, กับ, ว่า, คือ, จะ, ใน, ของ, จาก, สำหรับ, เมื่อ, ให้"""
    text = clean_render_text(text)
    if len(text) <= max_chars:
        return re.sub(r'[\s=\-–—:_\"\'\(\[“]+$', '', text).strip()

    try:
        from pythainlp.tokenize import word_tokenize
        tokens = word_tokenize(text, engine="newmm")
        res = ""
        for t in tokens:
            if len(res) + len(t) <= max_chars:
                res += t
            else:
                break
        text = res if res else text[:max_chars]
    except Exception:
        text = text[:max_chars].rsplit(" ", 1)[0]

    # ลบคำเชื่อมและเครื่องหมายคำพูดค้างคาที่ปลายประโยค เฉพาะกรณีที่มีการตัดทอน
    res = re.sub(r'[\s=\-–—:_\"\'\(\[“]+$', '', text).strip()
    res = re.sub(r'(?:เพื่อ|ที่|และ|หรือ|กับ|ว่า|คือ|จะ|ใน|ของ|จาก|สำหรับ|เมื่อ|ให้|โดย|ถึง)$', '', res).strip()
    res = re.sub(r'[\s=\-–—:_\"\'\(\[“]+$', '', res).strip()
    return res


# ----------------------------------------------------------------------
# 3. Ambient Background & Hero Frame Helpers
# ----------------------------------------------------------------------
def create_ambient_background(base_img: Optional[Image.Image], w: int = 1080, h: int = 1920, theme_palette: Optional[dict] = None) -> Image.Image:
    """สร้างพื้นหลัง Ambient Cinematic Blur เต็มจอ 1080x1920 เพื่อความลึก มีชีวิตชีวา และกลมกลืนกับภาพจริง ไร้ขอบดำมืด"""
    if base_img is not None:
        # 1. ขยายภาพให้คลุมพื้นที่ 1080x1920
        ratio = max(w / base_img.width, h / base_img.height)
        sw, sh = int(base_img.width * ratio), int(base_img.height * ratio)
        scaled = base_img.resize((sw, sh), Image.Resampling.LANCZOS)
        cx = max(0, (sw - w) // 2)
        cy = max(0, (sh - h) // 2)
        cropped = scaled.crop((cx, cy, cx + w, cy + h))

        # 2. Gaussian Blur สตูดิโอ
        blurred = cropped.filter(ImageFilter.GaussianBlur(radius=32))

        # 3. Dark Vignette Tint เพื่อให้ภาพ Hero และตัวหนังสือเด่นชัด 100%
        tint = Image.new("RGBA", (w, h), (10, 15, 26, 175))
        bg = Image.alpha_composite(blurred.convert("RGBA"), tint)
        return bg
    else:
        # Fallback: Gradient สีเข้มหรูหราประจำหมวดหมู่ ตาม Rule 26
        brand_col = theme_palette.get("brand_col", (34, 197, 94)) if theme_palette else (34, 197, 94)
        base = Image.new("RGBA", (w, h), (10, 15, 26, 255))
        draw = ImageDraw.Draw(base)
        for y in range(h):
            factor = y / float(h)
            r = int(10 * (1.0 - factor * 0.5) + brand_col[0] * 0.12 * factor)
            g = int(15 * (1.0 - factor * 0.5) + brand_col[1] * 0.12 * factor)
            b = int(26 * (1.0 - factor * 0.5) + brand_col[2] * 0.12 * factor)
            draw.line([(0, y), (w, y)], fill=(r, g, b, 255))
        return base


def create_rounded_hero_frame(img: Image.Image, target_w: int = 960, target_h: int = 660, radius: int = 24, border_color: tuple = (255, 255, 255, 220), border_width: int = 3) -> Image.Image:
    """จัดวางภาพจริง 100% ลงในกรอบโค้งมน พร้อมขอบสีคมชัด ป้องกันสัดส่วนบิดเบี้ยวและไม่ตัดหัวคน"""
    # 1. Center Crop ให้พอดีกรอบ target_w x target_h
    ratio = max(target_w / img.width, target_h / img.height)
    sw, sh = int(img.width * ratio), int(img.height * ratio)
    scaled = img.resize((sw, sh), Image.Resampling.LANCZOS)
    cx = max(0, (sw - target_w) // 2)
    cy = max(0, (sh - target_h) // 2)
    cropped = scaled.crop((cx, cy, cx + target_w, cy + target_h)).convert("RGBA")

    # 2. Alpha Mask สำหรับมุมโค้งมน
    mask = Image.new("L", (target_w, target_h), 0)
    d_mask = ImageDraw.Draw(mask)
    d_mask.rounded_rectangle([0, 0, target_w, target_h], radius=radius, fill=255)

    # 3. วางภาพลงบนกรอบใส
    result = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    result.paste(cropped, (0, 0), mask)

    # 4. วาดขอบมนรอบนอก (Border)
    d_border = ImageDraw.Draw(result)
    d_border.rounded_rectangle([1, 1, target_w - 2, target_h - 2], radius=radius, outline=border_color, width=border_width)

    return result


def create_typography_hero_card(
    w: int,
    h: int,
    thm: dict,
    title: str,
    phase_idx: int = 0,
    mode: str = "TRENDING_NEWS"
) -> Image.Image:
    """สร้าง Hero Typography Card สไตล์ Graphic Studio ด้วย Pillow 100% ตามคู่มือ Rule 26
    แก้ปัญหาช่องสี่เหลี่ยมดำว่างเปล่าเมื่อไม่มีภาพถ่ายจริง สวย คมชัด ระดับพรีเมียม ไร้เต้าหู้
    """
    card = Image.new("RGBA", (w, h), (0, 0, 0, 0))

    brand_col = thm.get("brand_col", (34, 197, 94))
    badge_bg = thm.get("badge_bg", (16, 185, 129))
    base_dark = (15, 23, 42)  # Slate 900

    # 1. วาดพื้นหลัง Gradient ภายในกรอบโค้งมน
    bg_img = Image.new("RGBA", (w, h), base_dark + (255,))
    d_bg = ImageDraw.Draw(bg_img)
    for y in range(h):
        factor = y / float(h)
        r = int(base_dark[0] * (1.0 - factor * 0.4) + brand_col[0] * 0.28 * factor)
        g = int(base_dark[1] * (1.0 - factor * 0.4) + brand_col[1] * 0.28 * factor)
        b = int(base_dark[2] * (1.0 - factor * 0.4) + brand_col[2] * 0.28 * factor)
        d_bg.line([(0, y), (w, y)], fill=(r, g, b, 255))

    mask = Image.new("L", (w, h), 0)
    d_mask = ImageDraw.Draw(mask)
    d_mask.rounded_rectangle([0, 0, w, h], radius=28, fill=255)
    card.paste(bg_img, (0, 0), mask)
    draw = ImageDraw.Draw(card)

    # 2. กรอบ 2 ชั้น ขอบสว่างคมชัด
    draw.rounded_rectangle([1, 1, w - 2, h - 2], radius=28, outline=thm.get("active_border", (52, 211, 153)), width=3)
    draw.rounded_rectangle([8, 8, w - 9, h - 9], radius=22, outline=(255, 255, 255, 60), width=2)

    # 3. แถบ Badge หัวข้อภายในการ์ด (Top Tag inside Card)
    tag_w, tag_h = 360, 44
    tx1 = (w - tag_w) // 2
    ty1 = 38
    draw.rounded_rectangle([tx1, ty1, tx1 + tag_w, ty1 + tag_h], radius=22, fill=badge_bg, outline=(255, 255, 255, 180), width=1)
    f_badge = get_font(FONT_BOLD, 22)
    draw.text((w // 2, ty1 + 22), f"• {thm.get('badge_txt', 'สาระน่ารู้')} •", font=f_badge, fill=(255, 255, 255), anchor="mm")

    # 4. ข้อความพาดหัวตัวโต ชัดเจน สวยงาม (Main Headline Typography)
    lines = wrap_thai_lines(title, max_chars_per_line=20, max_lines=4)
    if len(lines) <= 2:
        f_title = get_font(FONT_BOLD, 46)
        start_y = (h // 2) - 30 if len(lines) == 1 else (h // 2) - 55
        step_y = 66
    else:
        f_title = get_font(FONT_BOLD, 38)
        start_y = 150
        step_y = 54

    for line in lines:
        for dx, dy in [(-2, -2), (2, -2), (-2, 2), (2, 2), (0, 3)]:
            draw.text((w // 2 + dx, start_y + dy), line, font=f_title, fill=(0, 0, 0, 230), anchor="mm")
        draw.text((w // 2, start_y), line, font=f_title, fill=(255, 255, 255), anchor="mm")
        start_y += step_y

    # 5. แถบจุดเด่นด้านล่างการ์ด (Sub-feature Action Bar)
    sub_w = w - 80
    sub_h = 56
    sx1 = (w - sub_w) // 2
    sy1 = h - 85
    draw.rounded_rectangle([sx1, sy1, sx1 + sub_w, sy1 + sub_h], radius=16, fill=(255, 255, 255, 28), outline=(255, 255, 255, 70), width=1)
    f_sub = get_font(FONT_BOLD, 24)
    if phase_idx == 0:
        sub_txt = "• ประเด็นสำคัญที่ต้องรู้ • สรุปให้ใน 1 นาที •"
    elif phase_idx == 1:
        sub_txt = "• เจาะลึกวิธีแก้ปัญหา • ทำตามได้ทันที •"
    else:
        sub_txt = "• กดติดตามช่อง Anda • ไม่พลาดเรื่องเด็ดทุกวัน •"
    draw.text((w // 2, sy1 + sub_h // 2), sub_txt, font=f_sub, fill=thm.get("hook_col", (255, 215, 0)), anchor="mm")

    return card



# ----------------------------------------------------------------------
# 4. Master Template Poster Generator (3 Phases)
# ----------------------------------------------------------------------
def render_cinematic_template_posters(
    mode: str,
    topic_data: dict,
    hero_images: List[Optional[Image.Image]],
    takeaways: List[str],
    channel_name: str = "Anda",
    line_id: str = "@137gsref"
) -> List[Image.Image]:
    """สร้างโปสเตอร์ 3 จังหวะ 1080x1920 (9:16) ตามเทมเพลตมาตรฐานสตูดิโอ (100% Mute-First)
    
    จังหวะการแสดงผล:
      • Phase 1 (0-3s): แสดงภาพจริง 1 + พาดหัว Hook สีเหลืองหยุดนิ้ว + ไฮไลท์ข้อที่ 1 สว่างสดใส
      • Phase 2 (3-6s): แสดงภาพจริง 2 (หรือภาพหลัก) + เจาะลึกเนื้อหา + ไฮไลท์ข้อที่ 2 สว่างสดใส
      • Phase 3 (6-9s): แสดงภาพจริง 3 + สรุปชวนติดตาม + ไฮไลท์ข้อที่ 3 สว่างสดใส
    """
    W, H = 1080, 1920
    thm = THEME_PALETTES.get(mode, THEME_PALETTES["TRENDING_NEWS"])

    # ตรวจสอบและทำความสะอาดข้อความสาระสำคัญ 3 ข้อ ป้องกันประโยคกุดค้างคา และกรองข้อความขยะ/Filler 100%
    FORBIDDEN_STEP_FILLERS = [
        "ติดตามช่อง", "รอเนื้อหาใหม่", "กดติดตาม", "อย่าลืมกด", "ติดตามดู",
        "คำมั่นสัญญาต่อไป", "ไม่พลาดอัปเดต", "ไม่พลาดเรื่องสำคัญ"
    ]
    clean_takeaways = []
    for idx, t in enumerate(takeaways[:3]):
        if any(fb in t for fb in FORBIDDEN_STEP_FILLERS):
            t = f"สาระสำคัญและข้อคิดประเด็นที่ {idx + 1}"
        cleaned = mtc.format_master_step(t, max_chars=mtc.STEP_ROW_CONFIG["max_chars"])
        if not cleaned:
            cleaned = f"สาระสำคัญประเด็นที่ {idx + 1}"
        clean_takeaways.append(cleaned)
    while len(clean_takeaways) < 3:
        clean_takeaways.append(f"ประเด็นสำคัญที่ต้องรู้ข้อที่ {len(clean_takeaways) + 1}")

    # กำหนดข้อความ Hook และหัวเรื่องบนสุด (Zone 2: Viral Hook Headline y=140..310)
    # กฎเหล็ก: หัวเรื่องด้านบนต้องเป็นหัวข้อหลัก/Hook ของคอนเทนต์เดียวกันตลอดทั้ง 3 เฟส
    # ห้ามเปลี่ยนหัวเรื่องด้านบนเป็นข้อความเชิญชวน 'กดติดตาม' หรือคำซ้ำซ้อนเด็ดขาด 100%
    title = (topic_data.get("title") or "").strip()
    hook = (topic_data.get("hook") or "").strip()
    top_headline = hook or title or "สรุปประเด็นสำคัญที่ต้องรู้"

    top_headline = clean_render_text(top_headline)
    top_headline = mtc.format_master_hook(top_headline, max_chars=mtc.HOOK_CONFIG["max_chars"])

    phases = [
        {"top_text": top_headline, "active_step": 0, "hero_idx": 0},
        {"top_text": top_headline, "active_step": 1, "hero_idx": 1 if len(hero_images) > 1 and hero_images[1] else 0},
        {"top_text": top_headline, "active_step": 2, "hero_idx": 2 if len(hero_images) > 2 and hero_images[2] else 0}
    ]

    posters = []
    base_hero = hero_images[0] if hero_images and hero_images[0] else None

    for p_idx, ph in enumerate(phases):
        # 1. Ambient Background Layer
        active_hero = hero_images[ph["hero_idx"]] if ph["hero_idx"] < len(hero_images) and hero_images[ph["hero_idx"]] else base_hero
        canvas = create_ambient_background(active_hero or base_hero, W, H, thm)
        draw = ImageDraw.Draw(canvas)

        # 2. Top Header Zone (Safe Zone: y=105..315)
        # 2.1 Category Badge Pill (y=105..151)
        tag_w, tag_h = mtc.BADGE_CONFIG["w"], mtc.BADGE_CONFIG["h"]
        tx1 = (W - tag_w) // 2
        ty1 = mtc.BADGE_CONFIG["y"]
        draw.rounded_rectangle([tx1, ty1, tx1 + tag_w, ty1 + tag_h], radius=mtc.BADGE_CONFIG["radius"], fill=thm["badge_bg"], outline=(255, 255, 255), width=2)
        f_tag = get_font(FONT_BOLD, mtc.BADGE_CONFIG["font_size"])
        draw.text((W // 2, ty1 + tag_h // 2), f"[ {thm['badge_txt']} ]", font=f_tag, fill=(255, 255, 255), anchor="mm")

        # 2.2 3-Second Viral Hook Headline (y=160..315) — จัดวางกึ่งกลางอย่างประณีต ไร้การทับซ้อนกับป้ายหมวดหมู่ 100%
        hook_lines = wrap_thai_lines(ph["top_text"], max_chars_per_line=mtc.HOOK_CONFIG["max_chars_per_line"], max_lines=3)
        if len(hook_lines) <= 2:
            f_hook = get_font(FONT_BOLD, mtc.HOOK_CONFIG["font_size_1_2_lines"])
            hy = 235 if len(hook_lines) == 1 else 210
            step_hy = mtc.HOOK_CONFIG["line_spacing_1_2"]
        else:
            f_hook = get_font(FONT_BOLD, mtc.HOOK_CONFIG["font_size_3_lines"])
            hy = 185
            step_hy = mtc.HOOK_CONFIG["line_spacing_3"]

        h_color = thm["hook_col"] if p_idx == 0 else (255, 255, 255)
        for line in hook_lines:
            # 4-way deep black shadow for perfect contrast
            for dx, dy in mtc.HOOK_CONFIG["shadow_offsets"]:
                draw.text((W // 2 + dx, hy + dy), line, font=f_hook, fill=(0, 0, 0, 255), anchor="mm")
            draw.text((W // 2, hy), line, font=f_hook, fill=h_color, anchor="mm")
            hy += step_hy

        # 3. Hero Visual Zone (y=320..850) — 960x530 Flexible 16:9 Frame (ลดขนาดลงตามคำสั่งผู้ใช้ ไร้การบีบอัด)
        hero_w = mtc.HERO_FRAME_CONFIG["w"]
        hero_h = mtc.HERO_FRAME_CONFIG["h"]
        hero_x = (W - hero_w) // 2
        hero_y = mtc.HERO_FRAME_CONFIG["y"]
        if active_hero is not None:
            hero_frame = create_rounded_hero_frame(
                active_hero,
                target_w=hero_w,
                target_h=hero_h,
                radius=mtc.HERO_FRAME_CONFIG["radius"],
                border_color=mtc.HERO_FRAME_CONFIG["border_color"],
                border_width=mtc.HERO_FRAME_CONFIG["border_w"]
            )
            canvas.paste(hero_frame, (hero_x, hero_y), hero_frame)
        else:
            # Hero Typography Card
            hero_card = create_typography_hero_card(
                w=hero_w,
                h=hero_h,
                thm=thm,
                title=title,
                phase_idx=p_idx,
                mode=mode
            )
            canvas.paste(hero_card, (hero_x, hero_y), hero_card)

        # 4. Infographic Insight Zone (y=875..1480) — Dynamic 3-Step Progressive Highlight
        card_w = mtc.CARD_CONTAINER_CONFIG["w"]
        card_h = mtc.CARD_CONTAINER_CONFIG["h"]
        card_x = (W - card_w) // 2
        card_y = mtc.CARD_CONTAINER_CONFIG["y"]

        # 4.1 Frosted Glass Container
        glass_overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d_glass = ImageDraw.Draw(glass_overlay)
        d_glass.rounded_rectangle([card_x, card_y, card_x + card_w, card_y + card_h], radius=mtc.CARD_CONTAINER_CONFIG["radius"], fill=thm["card_bg"], outline=thm["card_border"], width=mtc.CARD_CONTAINER_CONFIG["border_w"])
        canvas = Image.alpha_composite(canvas, glass_overlay)
        draw = ImageDraw.Draw(canvas)

        # 4.2 Card Header
        f_card_head = get_font(FONT_BOLD, mtc.CARD_CONTAINER_CONFIG["header_font_size"])
        hdr = clean_render_text(thm["header_txt"])
        if not hdr.startswith("•"):
            hdr = f"• {hdr}"
        draw.text((card_x + mtc.CARD_CONTAINER_CONFIG["header_x_offset"], card_y + mtc.CARD_CONTAINER_CONFIG["header_y_offset"]), hdr, font=f_card_head, fill=mtc.CARD_CONTAINER_CONFIG["header_color"], anchor="lm")

        # 4.3 3 Progressive Rows
        row_w = mtc.STEP_ROW_CONFIG["w"]
        row_h = mtc.STEP_ROW_CONFIG["h"]
        rx = (W - row_w) // 2
        ry_start = mtc.STEP_ROW_CONFIG["start_y"]

        for s_idx in range(3):
            ry = ry_start + s_idx * (row_h + mtc.STEP_ROW_CONFIG["gap"])
            is_active = (s_idx == ph["active_step"])

            if is_active:
                # Active Highlight Row: สว่างสดใส มีขอบสว่างและตัวเลขเด่น
                draw.rounded_rectangle([rx, ry, rx + row_w, ry + row_h], radius=mtc.STEP_ROW_CONFIG["radius"], fill=thm["active_row_bg"], outline=thm["active_border"], width=3)
                # Number Pill
                np_w, np_h = mtc.STEP_ROW_CONFIG["num_box_w"], mtc.STEP_ROW_CONFIG["num_box_h"]
                nx = rx + 22
                ny = ry + (row_h - np_h) // 2
                draw.rounded_rectangle([nx, ny, nx + np_w, ny + np_h], radius=mtc.STEP_ROW_CONFIG["num_box_radius"], fill=thm["active_num_bg"])
                f_num = get_font(FONT_BOLD, mtc.STEP_ROW_CONFIG["num_font_size"])
                draw.text((nx + np_w // 2, ny + np_h // 2), str(s_idx + 1), font=f_num, fill=thm["active_num_txt"], anchor="mm")

                # Text with Drop Shadow (Auto font scaling 1-3 lines)
                row_lines = wrap_thai_lines(clean_takeaways[s_idx], max_chars_per_line=mtc.STEP_ROW_CONFIG["max_chars_per_line"], max_lines=3)
                if len(row_lines) == 1:
                    f_text = get_font(FONT_BOLD, mtc.STEP_ROW_CONFIG["font_size_1line"])
                    ty = ry + (row_h // 2)
                    step_y = 0
                elif len(row_lines) == 2:
                    f_text = get_font(FONT_BOLD, mtc.STEP_ROW_CONFIG["font_size_2lines"])
                    ty = ry + 36
                    step_y = mtc.STEP_ROW_CONFIG["line_spacing_2lines"]
                else:
                    f_text = get_font(FONT_BOLD, mtc.STEP_ROW_CONFIG["font_size_3lines"])
                    ty = ry + 24
                    step_y = mtc.STEP_ROW_CONFIG["line_spacing_3lines"]

                for rl in row_lines:
                    draw.text((rx + mtc.STEP_ROW_CONFIG["text_x_offset"] + 2, ty + 2), rl, font=f_text, fill=(0, 0, 0, 200), anchor="lm")
                    draw.text((rx + mtc.STEP_ROW_CONFIG["text_x_offset"], ty), rl, font=f_text, fill=(255, 255, 255), anchor="lm")
                    ty += step_y
            else:
                # Inactive Row: หรี่แสง สีเรียบหรู ไม่งง
                draw.rounded_rectangle([rx, ry, rx + row_w, ry + row_h], radius=mtc.STEP_ROW_CONFIG["radius"], fill=(30, 41, 59, 140), outline=(51, 65, 85, 120), width=1)
                # Number Pill
                np_w, np_h = mtc.STEP_ROW_CONFIG["num_box_w"], mtc.STEP_ROW_CONFIG["num_box_h"]
                nx = rx + 22
                ny = ry + (row_h - np_h) // 2
                draw.rounded_rectangle([nx, ny, nx + np_w, ny + np_h], radius=mtc.STEP_ROW_CONFIG["num_box_radius"], fill=(51, 65, 85))
                f_num = get_font(FONT_BOLD, 30)
                draw.text((nx + np_w // 2, ny + np_h // 2), str(s_idx + 1), font=f_num, fill=(148, 163, 184), anchor="mm")

                # Muted Text (Auto font scaling 1-3 lines)
                row_lines = wrap_thai_lines(clean_takeaways[s_idx], max_chars_per_line=26, max_lines=3)
                if len(row_lines) == 1:
                    f_text = get_font(FONT_REG, 33)
                    ty = ry + (row_h // 2)
                    step_y = 0
                elif len(row_lines) == 2:
                    f_text = get_font(FONT_REG, 33)
                    ty = ry + 38
                    step_y = 44
                else:
                    f_text = get_font(FONT_REG, 26)
                    ty = ry + 26
                    step_y = 34

                for rl in row_lines:
                    draw.text((rx + mtc.STEP_ROW_CONFIG["text_x_offset"], ty), rl, font=f_text, fill=(148, 163, 184), anchor="lm")
                    ty += step_y

        # 5. Safe Action Bar Footer (y=1515..1605 เว้นพื้นที่ปลอดภัยล่าง 315px ปลอดภัยจากปุ่ม TikTok/Shorts 100%)
        draw.rounded_rectangle([mtc.FOOTER_CONFIG["x1"], mtc.FOOTER_CONFIG["y1"], mtc.FOOTER_CONFIG["x2"], mtc.FOOTER_CONFIG["y2"]], radius=mtc.FOOTER_CONFIG["radius"], fill=mtc.FOOTER_CONFIG["bg_color"], outline=mtc.FOOTER_CONFIG["border_color"], width=mtc.FOOTER_CONFIG["border_w"])
        f_foot = get_font(FONT_BOLD, mtc.FOOTER_CONFIG["font_size"])
        draw.text((W // 2, (mtc.FOOTER_CONFIG["y1"] + mtc.FOOTER_CONFIG["y2"]) // 2), f"• กดติดตามช่อง {channel_name} • ทัก LINE: {line_id} •", font=f_foot, fill=mtc.FOOTER_CONFIG["text_color"], anchor="mm")

        posters.append(canvas.convert("RGB"))

    return posters
