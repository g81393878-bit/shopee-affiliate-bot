"""ตั้งค่า LINE Rich Menu (แถบเมนูติดหน้าจอด้านล่าง — ไม่หายเหมือน quick reply)

- ดีไซน์ระดับโลก: ออกแบบในสไตล์ Web App Dashboard / Modern Forum (ถอดคำว่า Affiliate ออก)
- ดาวน์โหลดฟอนต์ Prompt (Medium, Regular) จาก Google Fonts อัตโนมัติ
- วาดปุ่มแบบอสมมาตร (Asymmetric Layout) มี Hero Card และการ์ดแนวนอน/แนวตั้ง
- วาดไอคอนแบบ Flat/Vector ด้วยมือทีละตัว (แว่นขยาย, หมวดหมู่, ดาว, กราฟอันดับ, หัวใจ, กล่องแชท)
- สร้าง rich menu → อัปโหลดรูป → ตั้งเป็น default ให้ทุกคน
- พิกัดปุ่มสัมผัสตรงกับตำแหน่งการ์ดจริง 100%

รัน: cd backend && PYTHONIOENCODING=utf-8 ./.venv/Scripts/python tools/setup_rich_menu.py --force
รูปตัวอย่างถูกเขียนที่ D:/rich_menu.png (ดูได้ ไม่ได้ commit ขึ้น git)
"""
import os
import sys
import math
import urllib.request

# ให้ import app.* ได้ (db.py/models.py อยู่ app/)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

try:
    from dotenv import load_dotenv
    load_dotenv()  # fallback: อ่าน backend/.env (ไม่ทับ env ที่ตั้งไว้แล้ว)
except Exception:
    pass

from PIL import Image, ImageDraw, ImageFont

from linebot import LineBotApi
from linebot.models import (RichMenu, RichMenuSize, RichMenuArea, RichMenuBounds,
                             MessageAction)

MENU_NAME = "ป้าเข็มเมนู"
CHAT_BAR_TEXT = "🛍️ เมนูป้าเข็ม"

W, H = 2500, 1686          # ขนาด rich menu มาตรฐาน

# โครงสร้างเมนูพร้อมดีไซน์แบบ Dashboard (พิกัดปุ่มตรงกับการ์ดจริงในรูปภาพ)
CARDS_CONFIG = [
    # 0. ค้นสินค้า (Hero Card) -> แอคชันส่งคำว่า "ค้นสินค้า"
    {
        "id": "search", "x": 24, "y": 204, "w": 1618, "h": 680, 
        "bg": "#EE4D2D", "fg": "#FFFFFF", "title": "ค้นหาของดี", "send": "ค้นสินค้า", 
        "desc": "พิมพ์สิ่งที่อยากได้ หรือบอกงบที่ต้องการให้ป้าเข็มช่วยหาเลยจ้า"
    },
    # 1. หมวดสินค้า -> แอคชันส่งคำว่า "หมวดสินค้า"
    {
        "id": "category", "x": 1666, "y": 204, "w": 810, "h": 680, 
        "bg": "#1E293B", "fg": "#FFFFFF", "title": "หมวดสินค้า", "send": "หมวดสินค้า", 
        "desc": "แยกตามประเภท ค้นหาของถูกใจง่ายและไว"
    },
    # 2. ขายดีวันนี้ -> แอคชันส่งคำว่า "วันนี้ขายอะไรดี"
    {
        "id": "star", "x": 24, "y": 908, "w": 810, "h": 754, 
        "bg": "#1E293B", "fg": "#FFFFFF", "title": "ดีลเด่นวันนี้", "send": "วันนี้ขายอะไรดี", 
        "desc": "ป้าเข็มคัดสรรสินค้าแนะนำคุณภาพสูง คุ้มค่าที่สุด"
    },
    # 3. อันดับขายดี -> แอคชันส่งคำว่า "อันดับขายดี"
    {
        "id": "ranking", "x": 858, "y": 908, "w": 810, "h": 754, 
        "bg": "#1E293B", "fg": "#FFFFFF", "title": "อันดับยอดฮิต", "send": "อันดับขายดี", 
        "desc": "3 อันดับสินค้าที่ผู้คนนิยมซื้อจริงในสัปดาห์นี้"
    },
    # 4. ทำไมต้องป้าเข็ม (Split Top) -> แอคชันส่งคำว่า "ทำไมต้องซื้อกับป้าเข็ม"
    {
        "id": "heart", "x": 1692, "y": 908, "w": 784, "h": 365, 
        "bg": "#1E293B", "fg": "#FFFFFF", "title": "บริการป้าเข็ม", "send": "ทำไมต้องซื้อกับป้าเข็ม", 
        "desc": "แนะนำด้วยใจ ของแท้ปลอดภัย 100%"
    },
    # 5. คุยกับป้าเข็ม (Split Bottom) -> แอคชันส่งคำว่า "คุยกับป้าเข็ม"
    {
        "id": "chat", "x": 1692, "y": 1297, "w": 784, "h": 365, 
        "bg": "#1E293B", "fg": "#FFFFFF", "title": "พูดคุยแชท", "send": "คุยกับป้าเข็ม", 
        "desc": "แชทคุยเล่น สอบถามบริการกับป้าเข็ม"
    },
]

def get_font(size: int, weight: str = "Medium") -> ImageFont.FreeTypeFont:
    font_filename = f"Prompt-{weight}.ttf"
    font_dir = os.path.dirname(os.path.abspath(__file__))
    font_path = os.path.join(font_dir, font_filename)
    
    if not os.path.exists(font_path):
        url = f"https://raw.githubusercontent.com/google/fonts/main/ofl/prompt/Prompt-{weight}.ttf"
        try:
            print(f"📥 กำลังดาวน์โหลดฟอนต์ {font_filename} จาก Google Fonts...")
            urllib.request.urlretrieve(url, font_path)
        except Exception as e:
            print(f"⚠️ ดาวน์โหลดฟอนต์ไม่สำเร็จ: {e}")
            
    if os.path.exists(font_path):
        try:
            return ImageFont.truetype(font_path, size)
        except Exception:
            pass
            
    # Fallbacks สำหรับเครื่องระบบ Windows
    candidates = [
        r"C:\Windows\Fonts\leelawadeeui.ttf",
        r"C:\Windows\Fonts\tahoma.ttf",
        r"C:\Windows\Fonts\arial.ttf"
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


# --- ฟังก์ชันวาดไอคอนเรขาคณิต (Flat/Vector) ด้วย Pillow ---

def draw_search_icon(d, cx, cy, color):
    r = 30
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=8)
    d.line([cx + r - 10, cy + r - 10, cx + r + 20, cy + r + 20], fill=color, width=10)

def draw_category_icon(d, cx, cy, color):
    size = 22
    gap = 12
    d.rectangle([cx - size - gap//2, cy - size - gap//2, cx - gap//2, cy - gap//2], fill=color)
    d.rectangle([cx + gap//2, cy - size - gap//2, cx + size + gap//2, cy - gap//2], fill=color)
    d.rectangle([cx - size - gap//2, cy + gap//2, cx - gap//2, cy + size + gap//2], fill=color)
    d.rectangle([cx + gap//2, cy + gap//2, cx + size + gap//2, cy + size + gap//2], fill=color)

def draw_star_icon(d, cx, cy, color):
    points = []
    r_outer = 38
    r_inner = 16
    for i in range(10):
        r = r_outer if i % 2 == 0 else r_inner
        angle = math.pi * i / 5 - math.pi / 2
        x = cx + r * math.cos(angle)
        y = cy + r * math.sin(angle)
        points.append((x, y))
    d.polygon(points, fill=color)

def draw_ranking_icon(d, cx, cy, color):
    d.rounded_rectangle([cx - 38, cy - 10, cx - 18, cy + 30], radius=4, fill=color)
    d.rounded_rectangle([cx - 10, cy - 30, cx + 10, cy + 30], radius=4, fill=color)
    d.rounded_rectangle([cx + 18, cy + 10, cx + 38, cy + 30], radius=4, fill=color)

def draw_heart_icon(d, cx, cy, color):
    points = [
        (cx, cy + 32),
        (cx - 32, cy - 5),
        (cx - 32, cy - 23),
        (cx - 16, cy - 32),
        (cx, cy - 16),
        (cx + 16, cy - 32),
        (cx + 32, cy - 23),
        (cx + 32, cy - 5),
    ]
    d.polygon(points, fill=color)

def draw_chat_icon(d, cx, cy, color, dot_color):
    d.rounded_rectangle([cx - 35, cy - 22, cx + 35, cy + 18], radius=8, fill=color)
    d.polygon([(cx - 20, cy + 18), (cx - 28, cy + 30), (cx - 10, cy + 18)], fill=color)
    dot_r = 4
    d.ellipse([cx - 18 - dot_r, cy - dot_r, cx - 18 + dot_r, cy + dot_r], fill=dot_color)
    d.ellipse([cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r], fill=dot_color)
    d.ellipse([cx + 18 - dot_r, cy - dot_r, cx + 18 + dot_r, cy + dot_r], fill=dot_color)


def draw_rich_menu_image(path: str):
    """วาดรูปเมนูอสมมาตรสไตล์ Dashboard ด้วย Prompt Font และ Flat Icons"""
    img = Image.new("RGB", (W, H), "#0F172A") # Slate 900
    d = ImageDraw.Draw(img)
    
    font_title = get_font(90, "Medium")
    font_desc = get_font(42, "Regular")
    font_header_title = get_font(60, "Medium")
    font_header_sub = get_font(40, "Regular")
    
    # 1. วาด Header บาร์ (สไตล์ Native App)
    d.rectangle([0, 0, W, 180], fill="#1E293B")
    d.line([0, 180, W, 180], fill="#334155", width=4)
    
    # โลโก้แอปจำลอง (วงกลมส้ม Shopee Accent)
    d.ellipse([48, 40, 148, 140], fill="#EE4D2D")
    font_logo = get_font(70, "Medium")
    d.text((75, 45), "ป", font=font_logo, fill="#FFFFFF")
    
    # ชื่อและสถานะระบบ (ถอดคำว่า Affiliate ออก)
    d.text((180, 48), "ป้าเข็ม ผู้ช่วยช้อปส่วนตัว", font=font_header_title, fill="#FFFFFF")
    # ไฟสถานะสีเขียว (🟢 Active)
    d.ellipse([180, 120, 196, 136], fill="#10B981")
    d.text((215, 108), "ค้นหาของดี เปรียบเทียบราคา 24 ชม.", font=font_header_sub, fill="#94A3B8")
    
    # 2. วาดการ์ดเมนูแต่ละใบตามพิกัด CARDS_CONFIG
    for cfg in CARDS_CONFIG:
        x0, y0, w, h = cfg["x"], cfg["y"], cfg["w"], cfg["h"]
        x1, y1 = x0 + w, y0 + h
        bg, fg = cfg["bg"], cfg["fg"]
        title, desc = cfg["title"], cfg["desc"]
        
        # วาดการ์ดแบบมีระยะขอบมนๆ
        d.rounded_rectangle([x0, y0, x1, y1], radius=40, fill=bg)
        
        # วาดขอบการ์ดบางๆ ยกเว้นปุ่มค้นหาหลัก
        if cfg["id"] != "search":
            d.rounded_rectangle([x0, y0, x1, y1], radius=40, outline="#334155", width=4)
            
        cx = x0 + w / 2
        
        if h > 500:
            # การ์ดขนาดใหญ่แนวตั้ง / คอนเทนต์หลัก
            cy_icon = y0 + h * 0.32
            y_title = y0 + h * 0.58
            y_desc = y0 + h * 0.76
            
            # วาดไอคอนเวกเตอร์
            if cfg["id"] == "search":
                draw_search_icon(d, cx, cy_icon, fg)
            elif cfg["id"] == "category":
                draw_category_icon(d, cx, cy_icon, fg)
            elif cfg["id"] == "star":
                draw_star_icon(d, cx, cy_icon, fg)
            elif cfg["id"] == "ranking":
                draw_ranking_icon(d, cx, cy_icon, fg)
                
            # วาดหัวข้อหลัก
            tw = d.textlength(title, font=font_title)
            d.text((cx - tw / 2, y_title), title, font=font_title, fill=fg)
            
            # วาดคำอธิบาย
            desc_color = "#FFCCBC" if cfg["id"] == "search" else "#94A3B8"
            td = d.textlength(desc, font=font_desc)
            d.text((cx - td / 2, y_desc), desc, font=font_desc, fill=desc_color)
            
        else:
            # การ์ดแนวนอน (Split Cards ด้านขวาล่าง)
            cy_mid = y0 + h / 2
            icon_x = x0 + 100
            
            # วาดไอคอน
            if cfg["id"] == "heart":
                draw_heart_icon(d, icon_x, cy_mid, fg)
            elif cfg["id"] == "chat":
                draw_chat_icon(d, icon_x, cy_mid, fg, bg)
                
            # วาดข้อความเยื้องขวา
            text_x = x0 + 200
            font_split_title = get_font(75, "Medium")
            font_split_desc = get_font(38, "Regular")
            
            d.text((text_x, cy_mid - 65), title, font=font_split_title, fill=fg)
            d.text((text_x, cy_mid + 20), desc, font=font_split_desc, fill="#94A3B8")
            
    img.save(path, "PNG")
    return path


def main():
    force = "--force" in sys.argv
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
    if not token or "mock" in token.lower():
        print("❌ ไม่มี LINE_CHANNEL_ACCESS_TOKEN จริง (หรือเป็น mock) — ข้าม")
        return 1
    api = LineBotApi(token)

    existing = api.get_rich_menu_list()
    mine = [m for m in existing if m.name == MENU_NAME]
    default_id = _default_rich_menu_id(api)
    if not force and mine and default_id and any(m.rich_menu_id == default_id for m in mine):
        print(f"✅ Rich menu '{MENU_NAME}' ตั้งเป็น default แล้ว ({default_id}) — ไม่ต้องทำซ้ำ")
        return 0

    # 1) วาดรูป
    out_png = "D:/rich_menu.png"
    draw_rich_menu_image(out_png)
    with open(out_png, "rb") as f:
        img_bytes = f.read()
    print(f"🎨 วาดรูปเมนูอสมมาตรสไตล์ Dashboard แล้ว: {out_png} ({len(img_bytes):,} bytes)")

    # 2) สร้างโครงสร้างริชเมนู (อสมมาตรตาม CARDS_CONFIG)
    areas = []
    for cfg in CARDS_CONFIG:
        areas.append(RichMenuArea(
            bounds=RichMenuBounds(x=cfg["x"], y=cfg["y"],
                                  width=cfg["w"], height=cfg["h"]),
            action=MessageAction(label=cfg["title"], text=cfg["send"])))
            
    rich = RichMenu(size=RichMenuSize(width=W, height=H), selected=True,
                    name=MENU_NAME, chat_bar_text=CHAT_BAR_TEXT, areas=areas)
    rich_id = api.create_rich_menu(rich)
    print(f"📋 สร้างโครงสร้าง Rich Menu ในระบบแล้ว ID: {rich_id}")

    # 3) อัปโหลดรูปภาพใหม่
    api.set_rich_menu_image(rich_id, "image/png", img_bytes)
    print("🖼️ อัปโหลดรูปภาพใหม่เรียบร้อย")

    # 4) ตั้งเป็นค่าเริ่มต้นให้ลูกค้าทุกคน
    api.set_default_rich_menu(rich_id)
    print("👥 ตั้งเป็นเมนูเริ่มต้น (Default) ให้ผู้ใช้ทุกคนแล้ว")

    # 5) เคลียร์ลบตัวเก่าที่ชื่อซ้ำกันออก
    for m in existing:
        if m.name == MENU_NAME and m.rich_menu_id != rich_id:
            try:
                api.delete_rich_menu(m.rich_menu_id)
                print(f"🗑️ ลบ Rich Menu ตัวเก่า: {m.rich_menu_id}")
            except Exception as e:
                print(f"⚠️ ลบตัวเก่าไม่ได้: {e}")

    print(f"\n✅ อัปเกรดริชเมนูสำเร็จ! — Default Rich Menu ID = {_default_rich_menu_id(api)}")
    return 0


def _default_rich_menu_id(api):
    """SDK ตัวนี้ get_default_rich_menu คืน ID ตรงๆ (str) — รองรับทั้ง str/object"""
    try:
        d = api.get_default_rich_menu()
        return d if isinstance(d, str) else getattr(d, "rich_menu_id", None)
    except Exception:
        return None


if __name__ == "__main__":
    sys.exit(main())
