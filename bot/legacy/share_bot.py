#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import time
import json
import argparse
import io
import random
from pathlib import Path
from typing import Optional

# Ensure backend/app paths are accessible if needed
sys.path.append(str(Path(__file__).resolve().parent.parent))

# Configure console output to support UTF-8 on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

# Import WebDriver elements
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException

def _launch_driver():
    """ริเริ่มบราวเซอร์ด้วย undetected_chromedriver"""
    import undetected_chromedriver as uc
    options = uc.ChromeOptions()
    options.headless = False
    options.add_argument("--no-first-run")
    options.add_argument("--no-service-autorun")
    options.add_argument("--password-store=basic")
    options.add_argument("--start-maximized")
    
    # พยายามเปิด Chrome
    driver = uc.Chrome(options=options, version_main=151)
    driver.set_script_timeout(10)
    driver.set_page_load_timeout(20)
    return driver

def type_like_human(element, text: str):
    """จำลองการพิมพ์ข้อความทีละตัวอักษรพร้อมหน่วงเวลาสุ่มแบบมนุษย์ (กรองอักษรนอก BMP เช่น Emoji เพื่อป้องกัน ChromeDriver พัง)"""
    element.clear()
    clean_text = "".join(c for c in text if ord(c) <= 0xffff)
    for char in clean_text:
        element.send_keys(char)
        # สุ่มดีเลย์ 0.03 ถึง 0.12 วินาทีต่อ 1 อักษร
        time.sleep(random.uniform(0.03, 0.12))

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
    """โหลด fb_cookies.json และฉีดเข้า browser session"""
    if not cookie_path.exists():
        print(f"[ERROR] ไม่พบไฟล์คุกกี้ที่พาธ: {cookie_path}")
        return False
        
    print("[INFO] กำลังเปิดหน้า Facebook เพื่อเตรียมฉีดคุกกี้...")
    try:
        driver.get("https://www.facebook.com/")
    except Exception as e:
        print(f"[WARNING] คำเตือนการโหลดหน้าแรก: {e}")
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
        print("[SUCCESS] ฉีด Facebook session cookies เรียบร้อยแล้ว")
        driver.refresh()
        time.sleep(3)
        return True
    except Exception as e:
        print(f"[ERROR] เกิดข้อผิดพลาดในการฉีดคุกกี้: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Facebook Direct Group Post Automator")
    parser.add_argument("--url", type=str, required=True, help="ลิงก์โพสต์เฟสบุ๊กที่ต้องการนำไปโพสต์แชร์")
    parser.add_argument("--group-url", type=str, required=True, help="ลิงก์หน้ากลุ่มเฟสบุ๊กเป้าหมายที่จะเข้าไปโพสต์")
    parser.add_argument("--caption", type=str, default="ฝากติดตามโพสต์นี้ด้วยครับ", help="แคปชั่นข้อความที่จะพิมพ์ก่อนวางลิงก์")
    parser.add_argument("--cookies", type=str, default=None, help="พาธไฟล์คุกกี้ (ค่าเริ่มต้นคือ ../fb_cookies.json)")
    parser.add_argument("--poster", type=str, default=r"D:\Shopee_Web_Scraping\assets", help="พาธโฟลเดอร์หรือไฟล์ภาพโปสเตอร์ที่จะสลับแชร์")
    parser.add_argument("--dry-run", action="store_true", help="โหมดจำลองการรันเพื่อทดสอบระบบ โดยจะไม่กดปุ่มโพสต์ส่งจริงลงเฟสบุ๊ก")
    args = parser.parse_args()

    # ตั้งค่าพาธคุกกี้เริ่มต้น
    root_dir = Path(__file__).resolve().parent.parent
    cookie_path = Path(args.cookies) if args.cookies else root_dir / "fb_cookies.json"

    print("[BOT] บอทโพสต์แชร์ลงกลุ่มเฟสบุ๊กเริ่มต้นทำงาน...")
    driver = None
    try:
        driver = _launch_driver()
        
        # 1. ฉีดคุกกี้เพื่อล็อกอิน
        if not inject_cookies(driver, cookie_path):
            print("[ERROR] ยกเลิกการทำงานเนื่องจากล็อกอินไม่สำเร็จ")
            return
            
        # 2. ไปที่ลิงก์กลุ่มเป้าหมายโดยตรง
        print(f"[INFO] กำลังเดินทางไปยังกลุ่มเป้าหมาย: {args.group_url}")
        driver.get(args.group_url)
        time.sleep(6)
        
        # 3. ค้นหาและคลิกช่อง "เขียนอะไรบางอย่าง..."
        print("[INFO] กำลังค้นหาช่องเขียนโพสต์ใหม่...")
        post_trigger_locators = [
            (By.XPATH, '//span[contains(text(), "เขียนอะไรสักหน่อย") or contains(text(), "เขียนอะไรบางอย่าง") or contains(text(), "Write something") or contains(text(), "สร้างโพสต์สาธารณะ") or contains(text(), "Create a public post")]'),
            (By.XPATH, '//div[@role="button"][contains(., "เขียนอะไรสักหน่อย") or contains(., "เขียนอะไรบางอย่าง") or contains(., "Write something") or contains(., "สร้างโพสต์") or contains(., "Create a public post")]'),
            (By.XPATH, '//div[contains(@class, "x1i10hfl")][contains(., "เขียนอะไรสักหน่อย") or contains(., "เขียนอะไรบางอย่าง") or contains(., "Write something")]')
        ]
        
        trigger_btn = None
        for by_type, selector in post_trigger_locators:
            try:
                trigger_btn = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((by_type, selector))
                )
                break
            except:
                continue
                
        if trigger_btn:
            print("[SUCCESS] พบช่องเขียนโพสต์ใหม่ กำลังทำการเปิดกล่องข้อความ...")
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", trigger_btn)
            time.sleep(1)
            try:
                trigger_btn.click()
            except Exception:
                driver.execute_script("arguments[0].click();", trigger_btn)
            time.sleep(4)
            
            # 4. ค้นหาช่องกรอกข้อความ (Textbox inside dialog)
            print("[INFO] กำลังค้นหาช่องกรอกข้อความของโพสต์...")
            textbox_locators = [
                (By.XPATH, '//div[@role="dialog"]//div[@role="textbox" or @contenteditable="true"]'),
                (By.XPATH, '//div[@role="textbox" or @contenteditable="true"]'),
                (By.XPATH, '//div[contains(@class, "xzsf02u")]')
            ]
            
            textbox = None
            for by_type, selector in textbox_locators:
                try:
                    textbox = WebDriverWait(driver, 5).until(
                        EC.visibility_of_element_located((by_type, selector))
                    )
                    break
                except:
                    continue
                    
            if textbox:
                print("[SUCCESS] พบช่องกรอกข้อความ กำลังพิมพ์แคปชั่นและลิงก์โพสต์...")
                post_content = f"{args.caption}\n\n{args.url}"
                
                # ใช้ระบบพิมพ์จำลองแบบมนุษย์ป้องกันระบบตรวจจับบอท
                type_like_human(textbox, post_content)
                print("[INFO] พิมพ์เนื้อหาเสร็จสิ้น รอพรีวิวลิงก์โหลด...")
                time.sleep(6) # รอพรีวิวรูปภาพของลิงก์แชร์โหลดขึ้นมาตามธรรมชาติ
                
                # แนบรูปโปสเตอร์แนะนำบอท (ถ้ามีระบุ)
                resolved_poster = resolve_poster_image(args.poster)
                if resolved_poster:
                    print(f"[INFO] เริ่มอัปโหลดไฟล์ภาพแนะนำ: {resolved_poster}")
                    try:
                        file_input = driver.find_element(By.XPATH, '//input[@type="file"]')
                        file_input.send_keys(resolved_poster)
                        print("[SUCCESS] ส่งไฟล์ภาพให้เบราว์เซอร์แล้ว รอพรีวิวอัปโหลดเสร็จสิ้น...")
                        time.sleep(6)
                    except Exception as fe:
                        print(f"[WARNING] แนบภาพโปสเตอร์ไม่สำเร็จ (ข้ามการแนบรูปภาพ): {fe}")
                
                # 5. ค้นหาปุ่มโพสต์ (Post)
                print("[INFO] กำลังค้นหาปุ่ม 'โพสต์' (Post)...")
                post_btn_locators = [
                    (By.XPATH, '//div[@role="dialog"]//div[@role="button"][contains(., "โพสต์") or contains(., "Post") or contains(., "Share") or contains(., "แชร์")]'),
                    (By.XPATH, '//div[@role="button"][text()="โพสต์" or text()="Post"]'),
                    (By.XPATH, '//span[text()="โพสต์" or text()="Post"]/ancestor::div[@role="button"][1]')
                ]
                
                post_btn = None
                for by_type, selector in post_btn_locators:
                    try:
                        post_btn = WebDriverWait(driver, 5).until(
                            EC.element_to_be_clickable((by_type, selector))
                        )
                        break
                    except:
                        continue
                        
                if post_btn:
                    if args.dry_run:
                        print("[DRY-RUN] พบปุ่มโพสต์เรียบร้อยแล้ว! แต่จะไม่คลิกโพสต์จริงเนื่องจากรันอยู่ในโหมด --dry-run")
                        time.sleep(3)
                    else:
                        print("[INFO] กำลังคลิกปุ่มโพสต์...")
                        try:
                            post_btn.click()
                        except Exception:
                            driver.execute_script("arguments[0].click();", post_btn)
                        print("[SUCCESS] โพสต์แชร์ลงกลุ่มสำเร็จเรียบร้อยแล้ว!")
                        time.sleep(6)
                else:
                    print("[ERROR] ไม่พบปุ่ม 'โพสต์' (Post) สำหรับส่งข้อมูล")
                    screenshot_path = str(root_dir / "bot" / "post_btn_error.png")
                    driver.save_screenshot(screenshot_path)
            else:
                print("[ERROR] ไม่พบช่องกรอกข้อความในป๊อปอัปสร้างโพสต์")
                screenshot_path = str(root_dir / "bot" / "textbox_error.png")
                driver.save_screenshot(screenshot_path)
        else:
            print("[ERROR] ไม่พบช่อง 'เขียนอะไรบางอย่าง...' ในหน้ากลุ่ม")
            screenshot_path = str(root_dir / "bot" / "trigger_btn_error.png")
            driver.save_screenshot(screenshot_path)
            
    except Exception as e:
        print(f"[FATAL] เกิดข้อผิดพลาดร้ายแรง: {e}")
        if driver:
            try:
                screenshot_path = str(root_dir / "bot" / "fatal_error.png")
                driver.save_screenshot(screenshot_path)
            except:
                pass
    finally:
        if driver:
            print("[INFO] กำลังปิดบราวเซอร์...")
            driver.quit()
            print("[INFO] เสร็จสิ้นการทำงาน")

if __name__ == "__main__":
    main()
