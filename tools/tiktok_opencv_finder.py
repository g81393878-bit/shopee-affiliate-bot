#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/tiktok_opencv_finder.py — ระบบตรวจจับและค้นหาพิกัดปุ่มบน TikTok ผ่าน OpenCV (Template Matching)

คุณสมบัติ:
1. เลี่ยงการโดนแบนจาก Appium / CDP / Dynamic Resource IDs 100%
2. ดึงภาพหน้าจอมือถือสดผ่าน ADB ➔ Match ภาพต้นแบบปุ่ม (Template) ➔ ส่งพิกัด (X, Y) กลับไปกดสัมผัส
3. รองรับมือถือทุกความละเอียดและทุกรุ่นหน้าจอ
"""

import os
import sys
import time
import subprocess
import pathlib
import cv2
import numpy as np
from typing import Optional, Tuple

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATES_DIR = PROJECT_ROOT / "tools" / "templates"
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)


def capture_adb_screen(device_id: Optional[str] = None) -> Optional[np.ndarray]:
    """ดึงภาพถ่ายหน้าจอมือถือสดผ่าน ADB เข้าสู่ OpenCV Image Array"""
    cmd = ["adb"]
    if device_id:
        cmd.extend(["-s", device_id])
    cmd.extend(["exec-out", "screencap", "-p"])

    try:
        res = subprocess.run(cmd, capture_output=True, timeout=10)
        if res.returncode == 0 and res.stdout:
            img_array = np.frombuffer(res.stdout, dtype=np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            return img
    except Exception as e:
        print(f"⚠️ Screencap Error: {e}")
    return None


import random

def find_template_on_screen(
    screen_img: np.ndarray,
    template_path: pathlib.Path,
    threshold: float = 0.82,
    randomize_offset: bool = True
) -> Optional[Tuple[int, int]]:
    """ค้นหาตำแหน่งพิกัดกึ่งกลาง (Center X, Center Y) ของปุ่มภาพต้นแบบด้วย OpenCV Grayscale + Coordinate Randomization"""
    if not template_path.exists():
        return None

    img_gray = cv2.cvtColor(screen_img, cv2.COLOR_BGR2GRAY)
    template_gray = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
    if template_gray is None or img_gray is None:
        return None

    th, tw = template_gray.shape[:2]

    # ทำ Grayscale Template Matching
    res = cv2.matchTemplate(img_gray, template_gray, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

    if max_val >= threshold:
        center_x = max_loc[0] + (tw // 2)
        center_y = max_loc[1] + (th // 2)

        # สุ่มพิกัดเบี่ยงเบนจากจุดศูนย์กลางเล็กน้อย (-8 ถึง +8 พิกเซล) เพื่อจำลองลายนิ้วมือมนุษย์จริง
        if randomize_offset:
            center_x += random.randint(-8, 8)
            center_y += random.randint(-8, 8)

        print(f"🎯 [OpenCV Match] พบปุ่ม {template_path.name} ที่พิกัด ({center_x}, {center_y}) | Match Score: {max_val:.4f}")
        return center_x, center_y

    return None


def find_color_button_center(
    screen_img: np.ndarray,
    lower_bgr: Tuple[int, int, int],
    upper_bgr: Tuple[int, int, int],
    min_area: int = 500,
    randomize_offset: bool = True
) -> Optional[Tuple[int, int]]:
    """ค้นหาพิกัดปุ่มจากช่วงสีเฉพาะ (เช่น ปุ่มโพสต์สีแดง หรือปุ่มถัดไป) พร้อมสุ่มพิกัดนิ้วมือ"""
    if screen_img is None:
        return None

    mask = cv2.inRange(screen_img, np.array(lower_bgr), np.array(upper_bgr))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    best_center = None
    max_area = 0

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area > min_area and area > max_area:
            x, y, w, h = cv2.boundingRect(cnt)
            # ปุ่มมักจะอยู่โซนครึ่งล่างของหน้าจอ
            if y > screen_img.shape[0] * 0.5:
                max_area = area
                cx = x + w // 2
                cy = y + h // 2
                if randomize_offset:
                    cx += random.randint(-6, 6)
                    cy += random.randint(-6, 6)
                best_center = (cx, cy)

    if best_center:
        print(f"🔴 [OpenCV Color Match] พบปุ่มสีที่พิกัด {best_center}")
    return best_center


def detect_and_dismiss_popups_opencv(device_id: Optional[str] = None) -> bool:
    """ตรวจจับและกดข้ามหน้าต่างป๊อปอัปสุ่มต่าง ๆ ของ TikTok (เช่น ปุ่มยกเลิก / อนุญาต / ปิด)"""
    screen_img = capture_adb_screen(device_id)
    if screen_img is None:
        return False

    # 1. ลองค้นหาภาพต้นแบบปุ่ม Cancel / Dismiss / Close
    popups = ["cancel_btn.png", "dismiss_btn.png", "close_btn.png", "allow_btn.png"]
    for popup_file in popups:
        tpl_path = TEMPLATES_DIR / popup_file
        if tpl_path.exists():
            coords = find_template_on_screen(screen_img, tpl_path, threshold=0.80)
            if coords:
                print(f"🛑 [OpenCV PopUp Shield] ตรวจพบป๊อปอัป {popup_file} สั่งกดข้ามที่พิกัด {coords}...")
                cmd = ["adb"]
                if device_id:
                    cmd.extend(["-s", device_id])
                cmd.extend(["shell", "input", "tap", str(coords[0]), str(coords[1])])
                subprocess.run(cmd, timeout=5)
                return True
    return False
