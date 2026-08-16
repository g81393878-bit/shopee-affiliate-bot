#!/usr/bin/env python
"""Backup config ของบอท — ก๊อป .env / คุกกี้ / db-password / DB ท้องถิ่น ไปโฟลเดอร์ backups/ (มี timestamp)

ใช้ก่อน deploy หรือก่อนแก้ config เพื่อกู้คืนได้เมื่อโค้ด/ค่าพัง:
    python tools/backup_config.py

ปลอดภัย: โฟลเดอร์ backups/ อยู่ใน .gitignore แล้ว (ไม่มีทาง commit secret)
"""
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STAMP = datetime.now().strftime("%Y%m%d-%H%M%S")
DEST = ROOT / "backups" / STAMP

# (source, is_dir) — ไฟล์/โฟลเดอร์ config ที่ต้องสำรอง (ไม่มี → ข้าม ไม่ error)
SOURCES = [
    (ROOT / "backend" / ".env", False),
    (ROOT / "fb_cookies.json", False),
    (ROOT / "affiliate_db.db", False),
    (Path.home() / ".supabase" / "db-password.txt", False),
    (Path.home() / ".render" / "cli.yaml", False),
]


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    copied = []
    for src, _is_dir in SOURCES:
        if not src.exists():
            continue
        dst = DEST / src.name
        shutil.copy2(src, dst)
        copied.append(str(src))
    print(f"✅ สำรอง config ไปที่: {DEST}")
    for s in copied:
        print(f"   • {s}")
    if not copied:
        print("⚠️ ไม่พบไฟล์ config ให้สำรอง (ตรวจ path ด้านบน)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
