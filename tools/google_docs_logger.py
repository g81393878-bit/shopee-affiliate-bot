"""
tools/google_docs_logger.py
===========================
ระบบบันทึกและซิงค์เอกสารโครงการลง Google Docs อัตโนมัติ (Google Docs Master Logger)
- ผูกกับบัญชีหลัก: regency2919@gmail.com
- โฟลเดอร์โครงการ: Paa Khem Bot & Shopee Affiliate Master Workspace (ID: 1jbNqUdiKf0Zdhk218QT_2yb4q63Vk2rj)
- เอกสารหลัก:
  1) Master Documentation: 1dlKCrrrB3FvlAvHOwqvvI6ORnIcFAkKE7MB7TDxegaI
  2) Engineering Changelog: จัดการบันทึกประวัติการแก้ไขและอัปเดตระบบ
"""

import os
import sys
import json
import argparse
import datetime
try:
    import keyring
except ImportError:
    keyring = None
from typing import Optional, Dict, Any

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

MASTER_FOLDER_ID = "1jbNqUdiKf0Zdhk218QT_2yb4q63Vk2rj"
MASTER_DOC_ID = "1dlKCrrrB3FvlAvHOwqvvI6ORnIcFAkKE7MB7TDxegaI"
CHANGELOG_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "google_docs_registry.json")

CLIENT_ID = "338689075775-o75k922vn5fdl18qergr96rp8g63e4d7.apps.googleusercontent.com"
KEYRING_SERVICE = "gemini-cli-workspace-oauth/main-account"
KEYRING_USER = "main-account"


def get_credentials() -> Credentials:
    """ดึง OAuth Credentials จากไฟล์ JSON บนเซิร์ฟเวอร์ หรือ Windows Credential Manager สำหรับ regency2919@gmail.com"""
    from pathlib import Path
    token_file = Path(__file__).resolve().parent / "google_workspace_token.json"

    # 1. ตรวจสอบไฟล์ token JSON บน Linux VPS หรือเครื่องที่ไม่มี Windows Credential Manager
    if token_file.exists():
        try:
            token_data = json.loads(token_file.read_text(encoding="utf-8"))
            creds = Credentials(
                token=token_data.get("accessToken") or token_data.get("access_token"),
                refresh_token=token_data.get("refreshToken") or token_data.get("refresh_token"),
                token_uri="https://oauth2.googleapis.com/token",
                client_id=CLIENT_ID
            )
            return creds
        except Exception:
            pass

    # 2. ดึงจาก Windows Credential Manager
    raw = None
    if keyring:
        raw = keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
        if not raw:
            # Fallback format
            raw = keyring.get_password("gemini-cli-workspace-oauth", "main-account")
    
    if not raw:
        raise RuntimeError("ไม่พบ Google Workspace Credentials ในระบบ กรุณาตรวจสอบการล็อกอิน regency2919@gmail.com หรือ google_workspace_token.json")

    try:
        data = json.loads(raw)
    except Exception:
        data = json.loads(raw.encode("utf-16-le").decode("utf-8"))
    token_data = data.get("token", data.get("credentials", {}))

    # บันทึกเป็นไฟล์ JSON อัตโนมัติเพื่อใช้ส่งต่อไปยัง VPS
    try:
        token_file.write_text(json.dumps(token_data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

    creds = Credentials(
        token=token_data.get("accessToken") or token_data.get("access_token"),
        refresh_token=token_data.get("refreshToken") or token_data.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=CLIENT_ID
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        # อัปเดตกลับลง token store
        token_data["accessToken"] = creds.token
        data["token"] = token_data
        try:
            keyring.set_password(KEYRING_SERVICE, KEYRING_USER, json.dumps(data))
        except Exception:
            pass

    return creds


def get_drive_service(creds: Credentials):
    return build("drive", "v3", credentials=creds)


def get_docs_service(creds: Credentials):
    return build("docs", "v1", credentials=creds)


def load_registry() -> Dict[str, str]:
    """โหลดรายการเอกสารที่ลงทะเบียนไว้"""
    if os.path.exists(CHANGELOG_CONFIG_PATH):
        try:
            with open(CHANGELOG_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "master_folder_id": MASTER_FOLDER_ID,
        "master_doc_id": MASTER_DOC_ID,
        "changelog_doc_id": ""
    }


def save_registry(registry: Dict[str, str]):
    """บันทึกรายการเอกสารลงไฟล์ JSON ในโปรเจกต์"""
    with open(CHANGELOG_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)


def create_document(title: str, content: str = "", folder_id: str = MASTER_FOLDER_ID) -> Dict[str, Any]:
    """สร้างเอกสาร Google Docs ใหม่ลงในโฟลเดอร์ของโครงการทันที"""
    creds = get_credentials()
    drive = get_drive_service(creds)
    docs = get_docs_service(creds)

    file_metadata = {
        "name": title,
        "mimeType": "application/vnd.google-apps.document",
        "parents": [folder_id] if folder_id else []
    }

    file = drive.files().create(
        body=file_metadata,
        fields="id, name, webViewLink"
    ).execute()

    doc_id = file.get("id")
    web_link = file.get("webViewLink")

    if content:
        docs.documents().batchUpdate(
            documentId=doc_id,
            body={
                "requests": [
                    {
                        "insertText": {
                            "location": {"index": 1},
                            "text": content
                        }
                    }
                ]
            }
        ).execute()

    return {
        "id": doc_id,
        "name": title,
        "url": web_link,
        "folder_id": folder_id
    }


def append_to_document(doc_id: str, text_to_append: str) -> bool:
    """เพิ่มข้อความต่อท้ายเอกสาร Google Docs ที่มีอยู่แล้ว"""
    creds = get_credentials()
    docs = get_docs_service(creds)

    doc = docs.documents().get(documentId=doc_id).execute()
    body = doc.get("body", {})
    content = body.get("content", [])

    # หาตำแหน่งท้ายสุดของเอกสาร
    end_index = 1
    if content:
        last_element = content[-1]
        end_index = max(1, last_element.get("endIndex", 1) - 1)

    docs.documents().batchUpdate(
        documentId=doc_id,
        body={
            "requests": [
                {
                    "insertText": {
                        "location": {"index": end_index},
                        "text": text_to_append
                    }
                }
            ]
        }
    ).execute()
    return True


def get_or_create_changelog_doc() -> str:
    """ดึงหรือสร้างเอกสารบันทึกประวัติการเปลี่ยนแปลง (Changelog)"""
    registry = load_registry()
    changelog_id = registry.get("changelog_doc_id")

    creds = get_credentials()
    drive = get_drive_service(creds)

    if changelog_id:
        try:
            drive.files().get(fileId=changelog_id, fields="id, trashed").execute()
            return changelog_id
        except Exception:
            pass

    # สร้างเอกสาร Changelog ใหม่
    header = """================================================================================
บันทึกประวัติการเปลี่ยนแปลงและการอัปเดตระบบ (ENGINEERING CHANGELOG & UPDATES)
โครงการ: ระบบบอทป้าเข็ม 13 ช่องทาง, Dynamic Hashtag Intelligence & Google Cloud
บัญชีเจ้าของระบบ: regency2919@gmail.com
โฟลเดอร์หลัก: Paa Khem Bot & Shopee Affiliate Master Workspace
================================================================================
เอกสารนี้ถูกบันทึกและอัปเดตแบบเรียลไทม์โดย Antigravity AI Agent และทีมพัฒนา
--------------------------------------------------------------------------------

"""
    doc_info = create_document(
        title="บันทึกการเปลี่ยนแปลงและอัปเดตระบบ (Engineering Changelog)",
        content=header,
        folder_id=MASTER_FOLDER_ID
    )
    changelog_id = doc_info["id"]
    registry["changelog_doc_id"] = changelog_id
    save_registry(registry)
    print(f"✅ สร้างเอกสาร Changelog ใหม่สำเร็จ: {doc_info['url']}")
    return changelog_id


def log_system_update(title: str, details: str, author: str = "Antigravity AI") -> str:
    """บันทึกความเปลี่ยนแปลงของระบบลงใน Changelog Google Docs ทันที"""
    changelog_id = get_or_create_changelog_doc()
    now_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S (GMT+7)")

    entry = f"""
--------------------------------------------------------------------------------
📌 วันที่และเวลา: {now_str}
👤 ผู้ดำเนินการ / ผู้บันทึก: {author}
🎯 หัวข้อการเปลี่ยนแปลง: {title}
--------------------------------------------------------------------------------
{details.strip()}

"""
    append_to_document(changelog_id, entry)
    url = f"https://docs.google.com/document/d/{changelog_id}/edit"
    return url


def sync_local_file(file_path: str, custom_title: Optional[str] = None) -> Dict[str, Any]:
    """อ่านไฟล์ในเครื่อง (เช่น walkthrough.md หรือเอกสารสรุป) แล้วอัปโหลดเป็น Google Doc ใหม่ในโฟลเดอร์โครงการ"""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"ไม่พบไฟล์: {file_path}")

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    title = custom_title or os.path.basename(file_path)
    return create_document(title=title, content=content, folder_id=MASTER_FOLDER_ID)


def main():
    parser = argparse.ArgumentParser(description="Paa Khem Bot Google Docs Master Logger")
    subparsers = parser.add_subparsers(dest="command", help="คำสั่งที่ต้องการเรียกใช้")

    # Command: log
    log_parser = subparsers.add_parser("log", help="บันทึกประวัติการเปลี่ยนแปลงลงใน Changelog Doc")
    log_parser.add_argument("--title", required=True, help="หัวข้อการอัปเดต")
    log_parser.add_argument("--details", required=True, help="รายละเอียดของการเปลี่ยนแปลง")
    log_parser.add_argument("--author", default="Antigravity AI", help="ชื่อผู้ดำเนินการ")

    # Command: create
    create_parser = subparsers.add_parser("create", help="สร้างเอกสาร Google Docs ใหม่ในโฟลเดอร์โครงการ")
    create_parser.add_argument("--title", required=True, help="ชื่อเอกสารใหม่")
    create_parser.add_argument("--content", default="", help="เนื้อหาเริ่มต้น")
    create_parser.add_argument("--file", default="", help="พาธไฟล์ข้อความสำหรับนำเข้าเนื้อหา")

    # Command: sync
    sync_parser = subparsers.add_parser("sync", help="นำเข้าไฟล์ในเครื่องไปเป็น Google Docs ใหม่")
    sync_parser.add_argument("--file", required=True, help="พาธไฟล์ที่ต้องการนำเข้า")
    sync_parser.add_argument("--title", default="", help="ชื่อเอกสารใน Google Docs")

    # Command: append
    append_parser = subparsers.add_parser("append", help="เพิ่มข้อความต่อท้ายเอกสารเดิม")
    append_parser.add_argument("--doc-id", required=True, help="ID ของ Google Docs")
    append_parser.add_argument("--text", required=True, help="ข้อความที่ต้องการเพิ่ม")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        if args.command == "log":
            url = log_system_update(title=args.title, details=args.details, author=args.author)
            print(f"✅ บันทึกการเปลี่ยนแปลงลง Google Docs สำเร็จ!")
            print(f"🔗 URL: {url}")

        elif args.command == "create":
            content = args.content
            if args.file and os.path.exists(args.file):
                with open(args.file, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            res = create_document(title=args.title, content=content)
            print(f"✅ สร้างเอกสาร Google Docs ใหม่สำเร็จ!")
            print(f"📄 ชื่อ: {res['name']}")
            print(f"🆔 Doc ID: {res['id']}")
            print(f"🔗 URL: {res['url']}")

        elif args.command == "sync":
            res = sync_local_file(file_path=args.file, custom_title=args.title or None)
            print(f"✅ ซิงค์ไฟล์ขึ้น Google Docs สำเร็จ!")
            print(f"📄 ชื่อ: {res['name']}")
            print(f"🆔 Doc ID: {res['id']}")
            print(f"🔗 URL: {res['url']}")

        elif args.command == "append":
            append_to_document(doc_id=args.doc_id, text_to_append=args.text)
            print(f"✅ เพิ่มข้อความต่อท้ายเอกสารสำเร็จ!")
            print(f"🔗 URL: https://docs.google.com/document/d/{args.doc_id}/edit")

    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาด: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
