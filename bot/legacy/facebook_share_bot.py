# facebook_share_bot.py
# กลยุทธ์การเขียน Locator และ XPath สำหรับการกดตัวเลือก "แชร์ไปยังกลุ่ม" บน Facebook อย่างยั่งยืน
# อ้างอิงตามหลักการ ROBULA+, Similo, และ Playwright/Selenium Best Practices (2026)

import time
from typing import Optional

# ==============================================================================
# STRATEGY 1: PLAYWRIGHT (PYTHON)
# แนะนำมากที่สุดเนื่องจากมีระบบ Auto-Wait ในตัว และมี Selector ที่ทนทานสูง (Resilient)
# ==============================================================================

def share_to_group_playwright(page, group_name: str, message: Optional[str] = None):
    """
    ฟังก์ชันดำเนินการแชร์ไปยังกลุ่มบน Facebook โดยใช้ Playwright
    หลีกเลี่ยง Dynamic Class และโครงสร้าง DOM ที่เปราะบาง
    """
    print(f"[Playwright] เริ่มต้นกระบวนการแชร์ไปยังกลุ่ม: {group_name}")
    
    # 1. คลิกปุ่มตัวเลือกย่อย "แชร์ไปยังกลุ่ม" (Share to Group)
    # ใช้ get_by_text หรือ get_by_role ซึ่งจำลองพฤทีความมนุษย์และทนทานกว่า CSS/XPath เชิงโครงสร้าง
    # normalize-space ช่วยลบช่องว่างที่อาจเกิดขึ้นโดยรอบของปุ่ม
    share_to_group_option = page.get_by_role("button", name="แชร์ไปยังกลุ่ม")
    # สำรองในกรณีที่ระบบแสดงผลเป็นข้อความธรรมดาหรือ tag อื่น
    if not share_to_group_option.is_visible():
         share_to_group_option = page.get_by_text("แชร์ไปยังกลุ่ม", exact=False)
    
    share_to_group_option.click()
    print("[Playwright] คลิกตัวเลือก 'แชร์ไปยังกลุ่ม' สำเร็จ")

    # 2. รอให้กล่องป๊อปอัปและช่องค้นหากลุ่มแสดงผลสำเร็จ
    # Facebook มักใช้แอตทริบิวต์ placeholder เช่น "ค้นหากลุ่ม" หรือ "Search for groups"
    # การใช้ get_by_placeholder ช่วยให้อ่านง่ายและมีความเสถียรสูงกว่า class name ไดนามิก
    search_input = page.get_by_placeholder("ค้นหากลุ่ม")
    search_input.wait_for(state="visible", timeout=10000)
    
    # กรอกชื่อกลุ่มเป้าหมาย
    search_input.fill(group_name)
    print(f"[Playwright] พิมพ์ค้นหากลุ่ม: '{group_name}'")
    
    # รอให้ผลลัพธ์ปรากฏขึ้นมา
    # ใช้กลยุทธ์ข้อความคงที่ (Stable text matching) ค้นหากลุ่มที่ถูกต้องจากเมนูดรอปดาวน์
    group_item = page.get_by_text(group_name, exact=True)
    group_item.wait_for(state="visible", timeout=5000)
    group_item.click()
    print(f"[Playwright] เลือกกลุ่ม '{group_name}' สำเร็จ")

    # 3. กรอกข้อความโพสต์เพิ่มเติม (ถ้ามี)
    if message:
        # โดยทั่วไปช่องเขียนโพสต์ของ Facebook จะเป็น div ที่มี attribute 'contenteditable="true"' 
        # หรือมี placeholder เช่น "เขียนอะไรบางอย่าง..." หรือ "Say something about this..."
        post_input = page.get_by_role("textbox", name="เขียนอะไรบางอย่าง...")
        if post_input.is_visible():
            post_input.fill(message)
            print("[Playwright] ใส่ข้อความโพสต์เรียบร้อย")

    # 4. คลิกปุ่ม "โพสต์" (Post) เพื่อยืนยันการส่ง
    # ปุ่มยืนยันมักจะใช้ข้อความว่า "โพสต์" หรือ "Post"
    post_button = page.get_by_role("button", name="โพสต์", exact=True)
    post_button.click()
    print("[Playwright] คลิกปุ่มส่งแชร์ไปยังกลุ่มเสร็จสมบูรณ์!")


# ==============================================================================
# STRATEGY 2: SELENIUM WEBDRIVER (PYTHON)
# ใช้กรณีโปรเจกต์เดิมรันบน Selenium โดยใช้กลยุทธ์ Dynamic XPath และ XPath Axes
# เพื่อป้องกันปัญหาสคริปต์พังเมื่อ Facebook อัปเดต UI (Self-Healing Concept)
# ==============================================================================

def share_to_group_selenium(driver, group_name: str, message: Optional[str] = None):
    """
    ฟังก์ชันแชร์ไปยังกลุ่ม Facebook บน Selenium โดยอิงจาก XPath เชิงสัมพันธ์ (Relative XPath) 
    และแกนความสัมพันธ์ (XPath Axes) แทนโครงสร้างพิกัดแบบ Absolute XPath
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    print(f"[Selenium] เริ่มต้นกระบวนการแชร์ไปยังกลุ่ม: {group_name}")
    wait = WebDriverWait(driver, 10)

    # 1. คลิกตัวเลือกย่อย "แชร์ไปยังกลุ่ม"
    # ใช้ contains(text(), ...) ร่วมกับ normalize-space() เพื่อรับมือช่องว่างส่วนเกินและรองรับการปรับ DOM
    # หลีกเลี่ยง Absolute XPath เด็ดขาด เนื่องจาก Facebook เปลี่ยนแปลง div บ่อยมาก
    xpath_share_option = "//*[normalize-space(text())='แชร์ไปยังกลุ่ม' or contains(text(), 'Share to a group')]"
    share_option_element = wait.until(EC.element_to_be_clickable((By.XPATH, xpath_share_option)))
    share_option_element.click()
    print("[Selenium] คลิกตัวเลือก 'แชร์ไปยังกลุ่ม' สำเร็จ")

    # 2. ค้นหาช่องกรอกชื่อกลุ่ม
    # เนื่องจาก ID ของอินพุตใน Facebook เป็นไดนามิก (เช่น Navyug-XXXX-text) หรือมีคลาสยุ่งเหยิง
    # เราจึงใช้ Heuristic สองแบบ:
    # แบบที่ 1: ค้นหาด้วย placeholder attribute ตรงๆ (ซึ่งมีโอกาสเปลี่ยนต่ำมาก)
    # แบบที่ 2: ใช้ XPath Axes (following/following-sibling) หา input ตัวแรกหลังจากข้อความ "ค้นหากลุ่ม"
    xpath_search_input = (
        "//input[@placeholder='ค้นหากลุ่ม'] | "
        "//*[contains(text(), 'ค้นหากลุ่ม')]/following::input[1]"
    )
    search_input_element = wait.until(EC.visibility_of_element_located((By.XPATH, xpath_search_input)))
    search_input_element.clear()
    search_input_element.send_keys(group_name)
    print(f"[Selenium] พิมพ์ค้นหากลุ่ม: '{group_name}'")

    # 3. คลิกเลือกกลุ่มเป้าหมายจากรายการผลลัพธ์
    # ใช้การค้นหา text() ของกลุ่มโดยตรง เพื่อให้ได้ความแม่นยำสูง
    xpath_group_item = f"//*[normalize-space(text())='{group_name}']"
    group_item_element = wait.until(EC.element_to_be_clickable((By.XPATH, xpath_group_item)))
    group_item_element.click()
    print(f"[Selenium] เลือกกลุ่ม '{group_name}' สำเร็จ")

    # 4. กรอกข้อความในโพสต์ (ถ้ามี)
    if message:
        xpath_post_input = "//*[@role='textbox'] | //div[contains(@aria-label, 'เขียนข้อความ')]"
        try:
            post_input_element = driver.find_element(By.XPATH, xpath_post_input)
            post_input_element.send_keys(message)
            print("[Selenium] กรอกข้อความโพสต์สำเร็จ")
        except Exception:
            print("[Selenium] ข้ามการกรอกข้อความ (ไม่พบช่องกรอกแบบดั้งเดิม)")

    # 5. คลิกปุ่ม "โพสต์" (Post) เพื่อแชร์จริง
    # ระบุปุ่ม "โพสต์" ด้วยข้อความที่ระบุความมุ่งหมายของผู้ใช้ (User Intent)
    xpath_post_button = "//*[@role='button'][normalize-space(text())='โพสต์' or normalize-space(text())='Post']"
    post_button_element = wait.until(EC.element_to_be_clickable((By.XPATH, xpath_post_button)))
    post_button_element.click()
    print("[Selenium] คลิกปุ่มโพสต์เสร็จสิ้น!")
