# -*- coding: utf-8 -*-
"""Generate the Shopee Affiliate rich menu image and register it with LINE."""
import json
import os
import sys
import urllib.request

from PIL import Image, ImageDraw, ImageFont

TOKEN = os.environ.get("LINE_TOKEN", "")
IMG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_richmenu.png")
W, H = 2500, 843

def api(method, url, data=None, ctype=None):
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    if ctype:
        req.add_header("Content-Type", ctype)
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8") if not isinstance(data, bytes) else data
    try:
        with urllib.request.urlopen(req, body) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")

# ---------- 1. draw image ----------
img = Image.new("RGB", (W, H), "#EE4D2D")
d = ImageDraw.Draw(img)
f_main = ImageFont.truetype(r"C:\Windows\Fonts\tahomabd.ttf", 120)
f_sub = ImageFont.truetype(r"C:\Windows\Fonts\tahoma.ttf", 58)

main = "วันนี้ขายอะไรดี"
sub = "แตะเพื่อดูสินค้าแนะนำ 3 อันดับ + ลิงก์ Affiliate"

w1 = d.textlength(main, font=f_main)
w2 = d.textlength(sub, font=f_sub)
d.text(((W - w1) / 2, H / 2 - 150), main, font=f_main, fill="#FFFFFF")
d.text(((W - w2) / 2, H / 2 + 30), sub, font=f_sub, fill="#FFE3D9")
img.save(IMG_PATH, "PNG")
print("image saved:", IMG_PATH, os.path.getsize(IMG_PATH), "bytes")

# ---------- 2. create rich menu ----------
menu = {
    "size": {"width": W, "height": H},
    "selected": False,
    "name": "Shopee Affiliate เมนูหลัก",
    "chatBarText": "เมนู Affiliate",
    "areas": [
        {
            "bounds": {"x": 0, "y": 0, "width": W, "height": H},
            "action": {"type": "message", "label": "วันนี้ขายอะไรดี", "text": "วันนี้ขายอะไรดี"},
        }
    ],
}
st, out = api("POST", "https://api.line.me/v2/bot/richmenu", menu, "application/json")
print("create richmenu:", st, out[:300])
if st != 200:
    sys.exit(1)
rm_id = json.loads(out)["richMenuId"]
print("richMenuId:", rm_id)

# ---------- 3. upload image ----------
with open(IMG_PATH, "rb") as f:
    img_bytes = f.read()
st, out = api("POST", f"https://api-data.line.me/v2/bot/richmenu/{rm_id}/content", img_bytes, "image/png")
print("upload image:", st, out[:200])

# ---------- 4. set as default ----------
st, out = api("POST", f"https://api.line.me/v2/bot/user/all/richmenu/{rm_id}")
print("set default:", st, out[:200])

print("DONE", rm_id)
