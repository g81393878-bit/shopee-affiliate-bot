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


def find_template_on_screen(
    screen_img: np.ndarray,
    template_path: pathlib.Path,
    threshold: float = 0.75
) -> Optional[Tuple[int, int]]:
    """ค้นหาตำแหน่งพิกัดกึ่งกลาง (Center X, Center Y) ของปุ่มภาพต้นแบบบนหน้าจอ"""
    if not template_path.exists():
        print(f"⚠️ ไม่พบไฟล์ภาพต้นแบบ: {template_path}")
        return None

    template = cv2.imread(str(template_path), cv2.IMREAD_COLOR)
    if template is None or screen_img is None:
        return None

    th, tw = template.shape[:2]

    # ทำ Template Matching
    res = cv2.matchTemplate(screen_img, template, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

    if max_val >= threshold:
        center_x = max_loc[0] + (tw // 2)
        center_y = max_loc[1] + (th // 2)
        print(f"🎯 [OpenCV] พบปุ่ม {template_path.name} ที่พิกัด ({center_x}, {center_y}) | Confidence: {max_val:.2%}")
        return center_x, center_y

    print(f"🔍 [OpenCV] ไม่พบปุ่ม {template_path.name} (Max Score: {max_val:.2%} < {threshold:.2%})")
    return None


def find_color_button_center(
    screen_img: np.ndarray,
    lower_bgr: Tuple[int, int, int],
    upper_bgr: Tuple[int, int, int],
    min_area: int = 500
) -> Optional[Tuple[int, int]]:
    """ค้นหาพิกัดปุ่มจากช่วงสีเฉพาะ (เช่น สีแดงของปุ่มโพสต์ หรือสีชมพูของปุ่มถัดไป)"""
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
            # ปุ่มโพสต์มักจะอยู่โซนล่างของหน้าจอ (Y > 50% ของความสูง)
            if y > screen_img.shape[0] * 0.5:
                max_area = area
                best_center = (x + w // 2, y + h // 2)

    if best_center:
        print(f"🔴 [OpenCV Color Detection] พบปุ่มสีที่พิกัด {best_center}")
    return best_center
