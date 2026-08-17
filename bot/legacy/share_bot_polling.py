#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
บอทแชร์อัตโนมัติ (Share Bot Polling Mode)
ดึงงานคอมเมนต์แนะนำสินค้าแอฟฟิลิเอตจากเซิร์ฟเวอร์หลัก (Render) และพิมพ์ตอบกลับลูกค้าลงโพสต์ Facebook อัตโนมัติ
"""

import os
import sys
import time
import json
import random
import io
import argparse
import requests
from pathlib import Path
from typing import Optional

# เพิ่ม path เพื่อให้เข้าถึงโมดูลของโปรเจกต์ได้
sys.path.append(str(Path(__file__).resolve().parent.parent))

# ป้องกัน UnicodeEncodeError บนคอนโซล Windows (CP874/Thai) เมื่อพิมพ์ข้อความภาษาไทย
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def _launch_driver():
    import undetected_chromedriver as uc
    options = uc.ChromeOptions()
    options.headless = False
    options.add_argument("--no-first-run")
    options.add_argument("--no-service-autorun")
    options.add_argument("--password-store=basic")
    options.add_argument("--start-maximized")
    
    driver = uc.Chrome(options=options, version_main=151)
    driver.set_script_timeout(10)
    driver.set_page_load_timeout(20)
    return driver

def resolve_poster_image(path: str) -> Optional[str]:
    """ประมวลผลพาธโปสเตอร์ หากระบุเป็นโฟลเดอร์จะสุ่มรูปภาพที่ตรงเงื่อนไขเพื่อสลับใช้งาน"""
    if not path or not os.path.exists(path):
        return None
    p = Path(path)
    if p.is_file():
        return str(p.resolve())
    if p.is_dir():
        images = []
        for ext in ("*.png", "*.jpg", "*.jpeg"):
            images.extend(p.glob(ext))
        # กรองรูปที่ไม่ใช่โปสเตอร์ เช่น อวาตาร์โปรไฟล์บอท
        posters = [
            img for img in images 
            if "avatar" not in img.name.lower() and "icon" not in img.name.lower()
        ]
        if posters:
            chosen = random.choice(posters)
            print(f"[INFO] ค้นพบรูปภาพ {len(posters)} รูปในโฟลเดอร์แคมเปญ ทำการสุ่มเลือก: {chosen.name}")
            return str(chosen.resolve())
    return None

def inject_cookies(driver, cookie_path: Path) -> bool:
    if not cookie_path.exists():
        print(f"[ERROR] ไม่พบไฟล์คุกกี้ล็อกอิน: {cookie_path}")
        return False
        
    print("[INFO] เปิดหน้า Facebook เพื่อเริ่มฉีดเซสชันคุกกี้...")
    try:
        driver.get("https://www.facebook.com/")
    except Exception as e:
        print(f"[WARNING] คำเตือนโหลดหน้าแรก: {e}")
    time.sleep(3)
    
    try:
        with open(str(cookie_path), "r", encoding="utf-8") as f:
            cookies = json.load(f)
        for cookie in cookies:
            driver.add_cookie({
                "name": cookie["name"],
                "value": cookie["value"],
                "domain": cookie.get("domain", ".facebook.com"),
                "path": cookie.get("path", "/"),
            })
        print("[SUCCESS] ฉีดเซสชันล็อกอิน Facebook เรียบร้อย")
        driver.refresh()
        time.sleep(4)
        return True
    except Exception as e:
        print(f"[ERROR] เกิดข้อผิดพลาดในการโหลดคุกกี้: {e}")
        return False

def type_like_human(element, text: str):
    """พิมพ์จำลองแบบมนุษย์ทีละตัวอักษรเพื่อหลบระบบตรวจจับบอท (กรองอักษรนอก BMP เช่น Emoji เพื่อป้องกัน ChromeDriver พัง)"""
    # คลิกให้โฟกัส
    element.click()
    time.sleep(1)
    # กรองเอาเฉพาะตัวอักษรใน BMP (<= U+FFFF)
    clean_text = "".join(c for c in text if ord(c) <= 0xffff)
    # พิมพ์อักษรทีละตัว
    for char in clean_text:
        element.send_keys(char)
        time.sleep(random.uniform(0.03, 0.12))

def run_comment_task(driver, target_url: str, caption: str, dry_run: bool = False, poster_path: Optional[str] = None) -> bool:
    """เปิดหน้าโพสต์และพิมพ์คอมเมนต์ตอบกลับพิกัดสินค้า พร้อมแนบรูปโปสเตอร์"""
    print(f"[INFO] กำลังเดินทางไปยังโพสต์เป้าหมาย: {target_url}")
    try:
        driver.get(target_url)
    except Exception as e:
        print(f"[WARNING] เกิดปัญหาระหว่างโหลดหน้าโพสต์: {e}")
    time.sleep(6) # รอหน้าเว็บโหลดให้เรียบร้อย
    
    # 1. ค้นหากล่องเขียนคอมเมนต์ (Comment box textbox)
    print("[INFO] กำลังค้นหากล่องเขียนความคิดเห็น...")
    comment_box_locators = [
        (By.XPATH, '//div[@role="textbox" and (contains(@aria-label, "เขียนความคิดเห็น") or contains(@aria-label, "Write a comment") or contains(@aria-label, "แสดงความคิดเห็น") or contains(@aria-label, "comment"))]'),
        (By.XPATH, '//div[@role="textbox"]'),
        (By.XPATH, '//div[contains(@class, "xzsf02u")]')
    ]
    
    comment_box = None
    for by_type, selector in comment_box_locators:
        try:
            comment_box = WebDriverWait(driver, 6).until(
                EC.element_to_be_clickable((by_type, selector))
            )
            # เช็กว่าคลิกได้จริง
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", comment_box)
            time.sleep(1)
            break
        except Exception:
            continue
            
    if not comment_box:
        print("[ERROR] ไม่พบกล่องเขียนคอมเมนต์ในโพสต์นี้ (อาจโดนปิดคอมเมนต์ หรือบัญชีไม่มีสิทธิ์)")
        return False
        
    print("[SUCCESS] เจอกล่องคอมเมนต์แล้ว กำลังจำลองการพิมพ์คำแนะนำ...")
    try:
        type_like_human(comment_box, caption)
        time.sleep(3)
        
        # แนบรูปโปสเตอร์แนะนำบอท (ถ้ามีระบุ)
        resolved_poster = resolve_poster_image(poster_path)
        if resolved_poster:
            print(f"[INFO] เริ่มอัปโหลดไฟล์ภาพแนะนำ: {resolved_poster}")
            try:
                # ค้นหาอิลิเมนต์อินพุตอัปโหลดไฟล์ที่ซ่อนอยู่บนเว็บ Facebook
                file_input = driver.find_element(By.XPATH, '//input[@type="file"]')
                file_input.send_keys(resolved_poster)
                print("[SUCCESS] ส่งไฟล์ภาพให้เบราว์เซอร์แล้ว รอพรีวิวอัปโหลดเสร็จสิ้น...")
                time.sleep(6)
            except Exception as fe:
                print(f"[WARNING] แนบภาพโปสเตอร์ไม่สำเร็จ (ข้ามรูปภาพและคอมเมนต์ข้อความอย่างเดียว): {fe}")
        
        if dry_run:
            print("[DRY-RUN] ทำงานเรียบร้อย (ไม่ได้กดส่งจริงเนื่องจากเป็นโหมดจำลอง)")
            return True
        else:
            print("[INFO] กำลังส่งคอมเมนต์...")
            # ส่งด้วยการกด Enter
            comment_box.send_keys(Keys.ENTER)
            print("[SUCCESS] ส่งความคิดเห็นพิกัดสินค้าสำเร็จเรียบร้อยแล้ว!")
            time.sleep(5)
            return True
    except Exception as e:
        print(f"[ERROR] เกิดข้อผิดพลาดขณะกรอกหรือส่งคอมเมนต์: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Facebook Group Comment Sharing Bot (Polling Mode)")
    parser.add_argument("--api-url", type=str, default="https://shopee-affiliate-bot-9e9n.onrender.com", help="URL ของเซิร์ฟเวอร์หลัก (Render)")
    parser.add_argument("--token", type=str, default=None, help="Token สำหรับยืนยันสิทธิ์แอดมิน (หากไม่มีจะพยายามอ่านจาก .env)")
    parser.add_argument("--interval", type=int, default=30, help="เวลาหน่วงการเช็กงานรอบใหม่ (วินาที)")
    parser.add_argument("--cookies", type=str, default=None, help="พาธคุกกี้เซสชันล็อกอิน")
    parser.add_argument("--poster", type=str, default=r"D:\Shopee_Web_Scraping\assets", help="พาธโฟลเดอร์หรือไฟล์ภาพโปสเตอร์ที่จะสลับแชร์")
    parser.add_argument("--dry-run", action="store_true", help="โหมดจำลองการรันโดยไม่บันทึกโพสต์จริงลงเฟสบุ๊ก")
    args = parser.parse_args()

    # พยายามโหลด token จาก .env หรือใช้ค่าแมนนวล
    token = args.token
    root_dir = Path(__file__).resolve().parent.parent
    cookie_path = Path(args.cookies) if args.cookies else root_dir / "fb_cookies.json"
    
    if not token:
        # พยายามโหลดจากไฟล์ .env
        try:
            with open(root_dir / "backend" / ".env", "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("CRON_TOKEN="):
                        token = line.strip().split("=", 1)[1]
                        break
        except:
            pass
            
    api_base = args.api_url.rstrip("/")
    print("==========================================================")
    print("🚀 เริ่มระบบบอทแชร์อัตโนมัติ (Polling Queue Mode)")
    print(f"📡 เชื่อมต่อเซิร์ฟเวอร์: {api_base}")
    print(f"🔑 Admin Token: {'มีค่าตั้งค่าแล้ว' if token else 'ไม่ได้ระบุ (รันแบบไม่มี Token)'}")
    print("==========================================================")
    
    driver = None
    try:
        # เปิดเบราว์เซอร์เตรียมล็อกอิน
        driver = _launch_driver()
        if not inject_cookies(driver, cookie_path):
            print("[ERROR] ไม่สามารถตั้งค่าล็อกอินระบบได้ ยกเลิกการทำงาน")
            return
            
        while True:
            headers = {}
            if token:
                headers["X-Admin-Token"] = token
                
            # 1. ทำการ Polling ค้นหาคิวงานแชร์
            print(f"\n📥 [{time.strftime('%H:%M:%S')}] กำลังตรวจสอบคิวงานที่ยังไม่ได้รันจากระบบ...")
            try:
                # ส่ง token ผ่าน query parameter หรือ headers ก็ได้
                params = {"token": token} if token else {}
                response = requests.get(f"{api_base}/api/admin/facebook-radar/tasks/pending", params=params, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    tasks = response.json()
                    if not tasks:
                        print(f"😴 ไม่มีงานโพสต์ค้างในระบบ รอตรวจสอบรอบถัดไปใน {args.interval} วินาที...")
                    else:
                        print(f"🔥 ตรวจพบงานค้างสะสม {len(tasks)} รายการ เริ่มประมวลผลทันที!")
                        for task in tasks:
                            task_id = task["task_id"]
                            post_url = task["post_url"]
                            caption = task["caption"]
                            
                            print(f"\n👉 [งาน ID: {task_id}] เริ่มดำเนินการตอบโพสต์...")
                            success = run_comment_task(driver, post_url, caption, args.dry_run, args.poster)
                            
                            if args.dry_run:
                                # DRY-RUN: ไม่แตะสถานะบน server — ไม่งั้นงานในคิวจะถูกตีเป็น
                                # "shared" ถาวรทั้งที่ยังไม่ได้แชร์จริง (งานหายจากคิวเปล่า ๆ)
                                print(f"[DRY-RUN] ไม่รายงานสถานะกลับ server (งาน {task_id} ยังอยู่ในคิว)")
                            else:
                                # 2. ส่งสถานะกลับไปยังเซิร์ฟเวอร์หลักเพื่ออัปเดตและลบคิวงาน
                                status_endpoint = f"{api_base}/api/admin/facebook-radar/tasks/{task_id}/status"
                                status_payload = {
                                    "status": "completed" if success else "failed",
                                    "error_message": None if success else "Failed to post comment using Selenium"
                                }
                                
                                try:
                                    res_status = requests.post(status_endpoint, json=status_payload, params=params, headers=headers, timeout=10)
                                    if res_status.status_code == 200:
                                        print(f"✅ บันทึกสถานะงาน {task_id} สำเร็จ!")
                                    else:
                                        print(f"❌ บันทึกสถานะงาน {task_id} ล้มเหลว รหัสสถานะ {res_status.status_code}")
                                except Exception as ex:
                                    print(f"⚠️ ไม่สามารถเชื่อมต่อส่งผลลัพธ์กลับไปยังเซิร์ฟเวอร์: {ex}")
                                
                            # เว้นระยะห่างการทำแต่ละงานเพื่อความเนียน
                            time.sleep(random.uniform(10, 20))
                else:
                    print(f"❌ ตรวจสอบคิวงานไม่สำเร็จ รหัสความผิดพลาด: {response.status_code}")
            except Exception as e:
                print(f"⚠️ เกิดปัญหาระหว่างทำ Polling: {e}")
                
            time.sleep(args.interval)
            
    except KeyboardInterrupt:
        print("\n👋 บอทถูกระงับด้วยผู้ใช้งาน")
    finally:
        if driver:
            print("[INFO] ปิดบราวเซอร์และทำความสะอาดระบบ...")
            driver.quit()
            print("[INFO] เสร็จสิ้นการทำงานบอทแชร์")

if __name__ == "__main__":
    main()
