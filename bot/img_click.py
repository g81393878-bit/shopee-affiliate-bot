# -*- coding: utf-8 -*-
"""cv2 image-based clicking — กดปุ่ม Facebook ที่ DOM click โดนกัน (synthetic click ไม่ทำงาน).

หลักการ:
  1) capture_template() ครอปพิกเซลจริงของ element จาก screenshot หน้าต่างเบราว์เซอร์
     (พิกเซลเดียวกับหน้าจอ → cv2.matchTemplate แม่น)
  2) click_element() นำหน้าต่าง Chrome ขึ้นหน้า → ถ่ายเต็มจอ → cv2.matchTemplate หาปุ่ม
     → pyautogui คลิกเมาส์จริง (mouse event isTrusted=true → Facebook กันไม่ได้)

ต้องรันบนเครื่องที่มีจอจริง + Chrome เปิดเต็มจออยู่ (undetected_chromedriver start-maximized)
"""
import io
import time

import cv2
import numpy as np
import pyautogui
from PIL import Image

pyautogui.FAILSAFE = True


def bring_to_front(driver):
    """นำหน้าต่าง Chrome ของ driver ขึ้นหน้า (กันคลิกไปโดนหน้าต่างอื่น)."""
    try:
        import pygetwindow as gw
        title = (driver.title or "").strip()
        windows = gw.getAllWindows()
        # แม่นสุด: title ของหน้าเพจ driver ตรงกับ title หน้าต่าง
        candidates = [w for w in windows if w.title and title and title[:30] in w.title]
        if not candidates:
            # fallback: หน้าต่าง Chrome ที่มีคำว่า Facebook
            candidates = [w for w in windows if w.title and "Facebook" in w.title and "Chrome" in w.title]
        if not candidates:
            return False
        w = candidates[0]
        if w.isMinimized:
            w.restore()
        w.activate()
        time.sleep(0.5)
        return True
    except Exception:
        return False


def capture_template(driver, element, out_path):
    """ครอป template ของ element จาก screenshot หน้าต่างเบราว์เซอร์ (physical px).

    คืน (height, width) ของ template ที่เขียนลงไฟล์.
    """
    png = driver.get_screenshot_as_png()
    win = np.array(Image.open(io.BytesIO(png)))  # H x W x RGB
    win_h, win_w = win.shape[:2]
    dpr = driver.execute_script("return window.devicePixelRatio") or 1
    inner_h = driver.execute_script("return window.innerHeight") or win_h
    chrome_h = max(0, win_h - int(inner_h * dpr))

    r = element.rect  # CSS px, viewport-relative
    x0 = max(0, int(r["x"] * dpr))
    y0 = max(0, int(chrome_h + r["y"] * dpr))
    x1 = min(win_w, int((r["x"] + r["width"]) * dpr))
    y1 = min(win_h, int(chrome_h + (r["y"] + r["height"]) * dpr))
    if x1 <= x0 or y1 <= y0:
        raise RuntimeError(f"template crop ว่าง rect={r} dpr={dpr} chrome_h={chrome_h}")

    crop = win[y0:y1, x0:x1]
    cv2.imwrite(str(out_path), cv2.cvtColor(crop, cv2.COLOR_RGB2BGR))
    return crop.shape[:2]


def _match_score(screen_bgr, tmpl):
    """cv2.matchTemplate — คืน (score, (cx, cy)) ของ match ที่ดีที่สุด."""
    if tmpl.shape[0] > screen_bgr.shape[0] or tmpl.shape[1] > screen_bgr.shape[1]:
        return -1.0, None
    res = cv2.matchTemplate(screen_bgr, tmpl, cv2.TM_CCOEFF_NORMED)
    _, maxv, _, maxloc = cv2.minMaxLoc(res)
    if maxv < 0:
        return -1.0, None
    h, w = tmpl.shape[:2]
    return float(maxv), (maxloc[0] + w // 2, maxloc[1] + h // 2)


def find_on_screen(template_path, confidence=0.70, timeout=8):
    """หา template บนจอด้วย cv2.matchTemplate — คืน (cx, cy) หรือ None."""
    tmpl = cv2.imread(str(template_path))
    if tmpl is None:
        return None
    deadline = time.time() + timeout
    best = -1.0
    while time.time() < deadline:
        screen = pyautogui.screenshot()
        img = cv2.cvtColor(np.array(screen), cv2.COLOR_RGB2BGR)
        score, pos = _match_score(img, tmpl)
        best = max(best, score)
        if score >= confidence:
            return pos
        time.sleep(0.4)
    return None


def click_template(template_path, confidence=0.70, timeout=8):
    """หา + กด template บนจอด้วยเมาส์จริง — คืน True ถ้ากดติด."""
    pos = find_on_screen(template_path, confidence, timeout)
    if not pos:
        return False
    pyautogui.moveTo(pos[0], pos[1], duration=0.2)
    time.sleep(0.3)
    pyautogui.click(pos[0], pos[1])
    return True


def element_screen_center(driver, element):
    """คืนพิกัดจอจริง (physical px) ของจุดกลาง element — ใช้ get_window_rect() (แม่นกว่า template match)."""
    dpr = driver.execute_script("return window.devicePixelRatio") or 1
    win = driver.get_window_rect()
    inner_h = driver.execute_script("return window.innerHeight") or win["height"]
    chrome_h = max(0, win["height"] - inner_h)
    r = element.rect
    cx = int((win["x"] + r["x"] + r["width"] / 2) * dpr)
    cy = int((win["y"] + chrome_h + r["y"] + r["height"] / 2) * dpr)
    return cx, cy


def click_element_coord(driver, element, scroll=True):
    """กด element ด้วยพิกัดจอจริง + pyautogui (เมาส์จริง กัน FB กัน DOM click).

    แม่น + เร็ว ไม่ต้อง template match — คืน (cx, cy).
    """
    if scroll:
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
            time.sleep(0.8)
        except Exception:
            pass
    cx, cy = element_screen_center(driver, element)
    pyautogui.moveTo(cx, cy, duration=0.2)
    time.sleep(0.3)
    pyautogui.click(cx, cy)
    return cx, cy


def click_element(driver, element, template_path, confidence=0.70, timeout=10):
    """ครอป template จาก element แล้วกดด้วยเมาส์จริง (กัน DOM click ถูก FB กัน).

    คืน True ถ้ากดติด (template match เจอบนจอแล้วคลิก).
    """
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
        time.sleep(0.8)
    except Exception:
        pass
    try:
        capture_template(driver, element, template_path)
    except Exception as e:
        print(f"[IMG] capture template ล้ม: {str(e)[:80]}")
        return False
    bring_to_front(driver)
    return click_template(template_path, confidence, timeout)
