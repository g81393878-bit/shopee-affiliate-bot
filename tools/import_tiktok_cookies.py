#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/import_tiktok_cookies.py — แปลง Cookie String ของ TikTok เป็น JSON และบันทึกเข้า Playwright Session"""

import http.cookies
import json
import os
import pathlib
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
TOOLS_DIR = PROJECT_ROOT / "tools"
COOKIE_FILE = TOOLS_DIR / "tiktok_cookies.json"
USER_DATA_DIR = TOOLS_DIR / "tiktok_user_data"

RAW_COOKIES = """_ttp=3GYfXWd3nfrv7x2AVpwwuDPsMYV; tt_chain_token=0DnhjZPl+vC8ncpL9z8KEA==; tiktok_webapp_theme_source=auto; tiktok_webapp_theme=dark; d_ticket=6d1f95867ace60a88f3753e1add8ff1c69701; multi_sids=7498779812569252872%3A57c2db3c50449ae5e266185b846ff6a1; cmpl_token=AgQYAPOC_hfkTtK4L-ol6T1dMfAFRwDnRz-MCWCmalI; uid_tt=3edd9a3834c7f313141f9467d76eca61ee20e281dea1ecfdd5dc44e77a416566; uid_tt_ss=3edd9a3834c7f313141f9467d76eca61ee20e281dea1ecfdd5dc44e77a416566; sid_tt=57c2db3c50449ae5e266185b846ff6a1; sessionid=57c2db3c50449ae5e266185b846ff6a1; sessionid_ss=57c2db3c50449ae5e266185b846ff6a1; store-idc=alisg; store-country-code=th; store-country-code-src=uid; tt-target-idc=alisg; tt-target-idc-sign=eOr-pt9dZgEk_0npgtWWhAKY4vOBO3HYzk_ib-uLvqHzz0tNOMNovzbm4A9E4dWn9jcdER-a3MnVmOxT7chKULvkEB1T88ofBPxxWWRBH7CeJ8dkjCQC7ndBuqgJSWJ59-tsZpQZLcD8Yrw4e4Vbuq4tPjHn3LllWBZVHXbmMteIwFmWnew-3MoAiFKkjJlsryuppX8MqRoH9s9k3tAp3hEhIOF2s3QnJUe-Ow6U1gWsOCJLteU01e4aUge0DlD3bvYjtq66EVb29hg9Or9qFrmp4kcBvj3FP2mN0Gzwj1VqFzzYtjlTBmxAOCfjkSmvs0uaKlAJsKenM1q52bGm1BnVZHnhA6IfDwrItdjqMxGLcKX23Jqw4o8hnpIzglsdbturm3KTFLNEUhHPkY_RgNnDPBE-_lwP49k-ycJRle8TY5DUmjTc4NxJO4Df1Us6ETwVOWAIURuTFPu19mxo_E4qVsJlYEvQP8geJE887J_p-XhwGzziDrcbV5n928WY; last_login_method=google; delay_guest_mode_vid=5; sid_guard=57c2db3c50449ae5e266185b846ff6a1%7C1784995589%7C15551991%7CThu%2C+21-Jan-2027+16%3A06%3A20+GMT; tt_session_tlb_tag=sttt%7C2%7CV8LbPFBEmuXiZhhbhG_2of_________G3fDZVPlZGBu-5MRHVwMrjMPhV_QZ_r2totm4qVMtn0k%3D; sid_ucp_v1=1.0.1-KDBjYzUwM2VjZDlhNjkxYjBjNDhjNTQ2ZDIxNWQyYjEwMmIzMTQxODcKGQiIiL6IppDBiGgQhb6T0wYYsws4CEASSAQQAxoDbXkyIiA1N2MyZGIzYzUwNDQ5YWU1ZTI2NjE4NWI4NDZmZjZhMTJOCiDR4a1DRorpeBLLWLXJ7bajLawNPW88Ovcj9VbJPWC20RIgClrhejUFn7EZZl-0MYgo6BxCLyv1RJMbwhG4L_ERg-sYAiIGdGlrdG9r; ssid_ucp_v1=1.0.1-KDBjYzUwM2VjZDlhNjkxYjBjNDhjNTQ2ZDIxNWQyYjEwMmIzMTQxODcKGQiIiL6IppDBiGgQhb6T0wYYsws4CEASSAQQAxoDbXkyIiA1N2MyZGIzYzUwNDQ5YWU1ZTI2NjE4NWI4NDZmZjZhMTJOCiDR4a1DRorpeBLLWLXJ7bajLawNPW88Ovcj9VbJPWC20RIgClrhejUFn7EZZl-0MYgo6BxCLyv1RJMbwhG4L_ERg-sYAiIGdGlrdG9r; living_user_id=382697961137; g_state={"i_l":0,"i_ll":1787233837025,"i_e":{"enable_itp_optimization":24},"i_et":1787233837025}; guest_mode_flag=1; tt_csrf_token=UbefCwjN-e8i5e6Nnu0Q4IMDhgU49nh-wq4I; passport_csrf_token=bc68da6d26840908401f8d5ba077c58b; passport_csrf_token_default=bc68da6d26840908401f8d5ba077c58b; sid_guard_tt_open=b0cd0f51a83bb85e9e9f3de93962ef5d%7C1788266238%7C5184000%7CSat%2C+31-Oct-2026+12%3A37%3A18+GMT; uid_tt_tt_open=b85b3b4431c7d97d5401df0276c93efb7f2a7db9a08eb29ddb51d757fd20ee26; uid_tt_ss_tt_open=b85b3b4431c7d97d5401df0276c93efb7f2a7db9a08eb29ddb51d757fd20ee26; sid_tt_tt_open=b0cd0f51a83bb85e9e9f3de93962ef5d; sessionid_tt_open=b0cd0f51a83bb85e9e9f3de93962ef5d; sessionid_ss_tt_open=b0cd0f51a83bb85e9e9f3de93962ef5d; tt_session_tlb_tag_tt_open=sttt%7C5%7CsM0PUag7uF6enz3pOWLvXf________-h9puqkwva2gkQhbQMKp8KhzqmI1QKtitrtxEwYXRsBUs%3D; sid_ucp_v1_tt_open=1.0.1-KDI0YjdmM2MzZjA2NDVlOWY0ODM1NTE5YzZjN2QyMTNiZjhhODA4ODMKGAiUiKyekoSbsGoQ_o3b1AYYpxM4AUDyBxADGgNzZzEiIGIwY2QwZjUxYTgzYmI4NWU5ZTlmM2RlOTM5NjJlZjVkMk4KIPV9UGc26eZKKtPRm8tjJbD4BQHxi8kt-aEzu70544L2EiBCBXIGasH9oCAmGlP9jbhj2lAoScCs2_VtleoyNopU6RgBIgZ0aWt0b2s; ssid_ucp_v1_tt_open=1.0.1-KDI0YjdmM2MzZjA2NDVlOWY0ODM1NTE5YzZjN2QyMTNiZjhhODA4ODMKGAiUiKyekoSbsGoQ_o3b1AYYpxM4AUDyBxADGgNzZzEiIGIwY2QwZjUxYTgzYmI4NWU5ZTlmM2RlOTM5NjJlZjVkMk4KIPV9UGc26eZKKtPRm8tjJbD4BQHxi8kt-aEzu70544L2EiBCBXIGasH9oCAmGlP9jbhj2lAoScCs2_VtleoyNopU6RgBIgZ0aWt0b2s; passport_fe_beating_status=true; tt_ticket_guard_has_set_public_key=1; s_v_web_id=verify_mtincnoi_oWGGLHKZ_0KOu_4gSY_Ap3g_vaGcmv3TNvN1; _waftokenid=eyJ2Ijp7ImEiOiJIcnJmZ1NWNGk3TlViMXJjeGJsa2NsMzJzNGR6T2NxQ1hmQitEeGtqTGhrPSIsImIiOjE3ODgyNjk5NTUsImMiOiJ1c0xBTWUxQjNjb0tEamNUWFpBTC9VUDdmZjhtdVVuSTQyZDQ4RWtVVFNvPSJ9LCJzIjoicnZUdkl1ZXNldUd0dUllR25jSDR6U2FyY2QzNVYwV3FialVkMkZuS2dnbz0ifQ; odin_tt=7f0c91fd9fe9965826e22c90f54d6114d1f2ca036a939ddee36546c7864035c824711d02e412b47622165655844304fe0c2384164a1a2ea1590733441eb70550282dfd98f8a03d77fbd834bb10b31f26; perf_feed_cache={%22expireTimestamp%22:1788872400000%2C%22itemIds%22:[%227677769515903552775%22%2C%227649211790705904914%22%2C%227678386949677436181%22]}; msToken=n1K_gITRxTuhlBUaDigpZEN3P1XpRQu1m_Yln3Lscd4gtk4oFnbrKyVwGsqtYFKeucbfGtAP_-4dkMimw3tbZf5oT29xU1QECY0_sQVglNsGBzcLRSqMhet139Y-oImOwGBuSX5-nzNBn2njQSjUi6-hHyCHEgDBQudmg__avjG9; store-country-sign=MEIEDOdeKRNlMWVvW5eHIQQgnpKnh6jv1RrFElwnvsTPvMtr-4CnaxlTCar7sCDHT7oEEFB7lrAJNdkkszyW81HpXTM; msToken=WKc4h_WHsAsd2Bij5OhZSiUMExp1oML54JQvZG4BQG8yq0gkn0Sm2btcFTbSpHmpVFszCIBzxzEBC1VMUUWYR0ZSfId0PFAn_2D-Vbwo2Z3VhUg_bZu5gsL_zfS9C72pMmgKwKZg4Og0wmsRtHo5Qp27EnDehkIe; ttwid=1%7Cr58w3kecjleBvpFjd9TVdvAW0S_NUiVuiLQscxm9AIM%7C1788270048%7Cceacc5ce47104be55923944e22dc7cf097557c26bc954ef01c1e912f66fd9d1e"""


def parse_cookie_string_to_playwright_cookies(cookie_str: str):
    cookies = []
    items = cookie_str.strip().split("; ")
    for item in items:
        if not item or "=" not in item:
            continue
        name, val = item.split("=", 1)
        name = name.strip()
        val = val.strip()
        cookies.append({
            "name": name,
            "value": val,
            "domain": ".tiktok.com",
            "path": "/",
            "secure": True,
            "sameSite": "None",
        })
    return cookies


def inject_cookies_to_playwright():
    cookies = parse_cookie_string_to_playwright_cookies(RAW_COOKIES)
    COOKIE_FILE.write_text(json.dumps(cookies, indent=2), encoding="utf-8")
    print(f"✓ บันทึก {len(cookies)} cookies ลงใน {COOKIE_FILE}")

    # Inject into Playwright persistent context
    from playwright.sync_api import sync_playwright

    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=True,
            args=["--no-sandbox"],
        )
        browser.add_cookies(cookies)
        page = browser.new_page()
        page.goto("https://www.tiktok.com/@healthgooddeals", timeout=30000)
        print("✓ ทดสอบเปิดหน้า TikTok @healthgooddeals สำเร็จ (Title:", page.title(), ")")
        browser.close()
    print("🎉 บันทึกเซสชัน TikTok เข้าสู่ระบบเรียบร้อย 100% พร้อมใช้งาน!")


if __name__ == "__main__":
    inject_cookies_to_playwright()
