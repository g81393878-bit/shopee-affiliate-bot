"""tools/cf_worker_manager.py
เครื่องมือจัดการเวอร์ชัน แบ็กอัป Deploy และ Rollback สำหรับ Cloudflare Worker (pakhem-line-webhook)

วิธีใช้งาน:
  1. แบ็กอัปเวอร์ชันที่รันอยู่จริงตอนนี้:
     python tools/cf_worker_manager.py backup --version v3.1 --note "รองรับคำถามสั้น 1-2 พยางค์"
  2. ดูรายการแบ็กอัปทั้งหมด:
     python tools/cf_worker_manager.py list
  3. Deploy ไฟล์ใหม่ (แบ็กอัปของเก่าให้อัตโนมัติก่อนทุกครั้ง):
     python tools/cf_worker_manager.py deploy --file <worker.js> --version v3.2 --note "สรุปสิ่งที่แก้"
  4. กู้คืนเวอร์ชันเก่า (Rollback ภายใน 3 วิ):
     python tools/cf_worker_manager.py rollback <backup_filename.js>
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKUP_DIR = ROOT_DIR / "backups" / "cf_workers"
CHANGELOG_PATH = BACKUP_DIR / "CHANGELOG.md"
ICT = timezone(timedelta(hours=7))


def _load_cf_config() -> tuple[str, str, str]:
    env_path = ROOT_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

    token = os.getenv("CF_API_TOKEN", "").strip()
    account_id = os.getenv("CF_ACCOUNT_ID", "").strip()
    worker_name = os.getenv("CF_WORKER_NAME", "pakhem-line-webhook").strip()

    # Fallback อ่านจาก tools/update_worker.py หากยังไม่ได้ตั้งค่าใน .env
    if not token or not account_id:
        legacy = ROOT_DIR / "tools" / "update_worker.py"
        if legacy.exists():
            txt = legacy.read_text(encoding="utf-8", errors="ignore")
            if not token:
                m = re.search(r'CF_API_TOKEN\s*=\s*"([^"]+)"', txt)
                if m:
                    token = m.group(1)
            if not account_id:
                m = re.search(r'CF_ACCOUNT_ID\s*=\s*"([^"]+)"', txt)
                if m:
                    account_id = m.group(1)

    if not token or not account_id:
        raise RuntimeError("ไม่พบ CF_API_TOKEN หรือ CF_ACCOUNT_ID ใน .env")
    return token, account_id, worker_name


def _extract_js_from_multipart(raw_text: str) -> str:
    lines = raw_text.splitlines()
    if lines and lines[0].startswith("--"):
        # ข้าม multipart header จนกว่าจะเจอบรรทัดว่างแรก
        body_start = 0
        for i, ln in enumerate(lines):
            if ln.strip() == "":
                body_start = i + 1
                break
        body_end = len(lines)
        for i in range(len(lines) - 1, -1, -1):
            if lines[i].startswith("--"):
                body_end = i
                break
        return "\n".join(lines[body_start:body_end]).strip() + "\n"
    return raw_text


def _append_changelog(action: str, version: str, filename: str, deployment_id: str, note: str) -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    if not CHANGELOG_PATH.exists():
        CHANGELOG_PATH.write_text(
            "# ประวัติเวอร์ชัน & แบ็กอัป Cloudflare Worker (`pakhem-line-webhook`)\n\n"
            "| วันเวลา (ICT) | การทำงาน | เวอร์ชัน | ไฟล์แบ็กอัป | Deployment ID | รายละเอียด |\n"
            "| :--- | :--- | :--- | :--- | :--- | :--- |\n",
            encoding="utf-8",
        )
    ts = datetime.now(ICT).strftime("%Y-%m-%d %H:%M:%S")
    row = f"| {ts} | {action} | `{version}` | `{filename}` | `{deployment_id or '-'}` | {note or '-'} |\n"
    with CHANGELOG_PATH.open("a", encoding="utf-8") as f:
        f.write(row)


def backup_live_worker(version: str = "snapshot", note: str = "") -> Path:
    token, account_id, worker_name = _load_cf_config()
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    r = httpx.get(
        f"https://api.cloudflare.com/client/v4/accounts/{account_id}/workers/scripts/{worker_name}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=20.0,
    )
    r.raise_for_status()
    js_body = _extract_js_from_multipart(r.text)
    safe_ver = re.sub(r"[^a-zA-Z0-9._-]", "_", version.strip() or "snapshot")
    ts = datetime.now(ICT).strftime("%Y%m%d_%H%M%S")
    out_path = BACKUP_DIR / f"{worker_name}_{safe_ver}_{ts}.js"
    out_path.write_text(js_body, encoding="utf-8")
    _append_changelog("BACKUP", safe_ver, out_path.name, "", note or "สำรองโค้ดจริงจาก Cloudflare")
    print(f"✅ แบ็กอัปสำเร็จ: {out_path} ({len(js_body)} bytes)")
    return out_path


def deploy_worker_file(file_path: Path, version: str, note: str = "", skip_backup: bool = False) -> dict:
    if not file_path.exists():
        raise FileNotFoundError(f"ไม่พบไฟล์: {file_path}")
    if not skip_backup:
        backup_live_worker(version=f"pre_{version}", note=f"สำรองอัตโนมัติก่อน Deploy {version}")

    token, account_id, worker_name = _load_cf_config()
    js_body = file_path.read_text(encoding="utf-8")
    metadata = json.dumps({"main_module": "worker.js"})
    files = {
        "metadata": ("metadata", metadata, "application/json"),
        "worker.js": ("worker.js", js_body.encode("utf-8"), "application/javascript+module"),
    }
    r = httpx.put(
        f"https://api.cloudflare.com/client/v4/accounts/{account_id}/workers/scripts/{worker_name}",
        headers={"Authorization": f"Bearer {token}"},
        files=files,
        timeout=20.0,
    )
    r.raise_for_status()
    data = r.json()
    dep_id = (data.get("result") or {}).get("deployment_id", "")

    # เก็บสำเนาเวอร์ชันที่เพิ่ง Deploy ด้วย
    safe_ver = re.sub(r"[^a-zA-Z0-9._-]", "_", version.strip() or "release")
    ts = datetime.now(ICT).strftime("%Y%m%d_%H%M%S")
    saved = BACKUP_DIR / f"{worker_name}_{safe_ver}_{ts}.js"
    saved.write_text(js_body, encoding="utf-8")
    _append_changelog("DEPLOY", safe_ver, saved.name, dep_id, note)
    print(f"🚀 Deploy สำเร็จ! version={safe_ver}, deployment_id={dep_id}")
    print(f"💾 บันทึกสำเนาไว้ที่: {saved}")
    return data


def list_backups() -> None:
    if not BACKUP_DIR.exists():
        print("ยังไม่มีไฟล์แบ็กอัปใน backups/cf_workers/")
        return
    files = sorted(BACKUP_DIR.glob("*.js"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        print("ยังไม่มีไฟล์แบ็กอัป")
        return
    print(f"📦 รายการแบ็กอัปทั้งหมด ({len(files)} เวอร์ชัน) ใน {BACKUP_DIR}:")
    for idx, p in enumerate(files, 1):
        mtime = datetime.fromtimestamp(p.stat().st_mtime, ICT).strftime("%Y-%m-%d %H:%M:%S")
        print(f"  {idx}. {p.name} ({p.stat().st_size:,} bytes | {mtime})")


def rollback_backup(filename: str) -> None:
    target = BACKUP_DIR / filename
    if not target.exists():
        raise FileNotFoundError(f"ไม่พบไฟล์แบ็กอัป: {target}")
    deploy_worker_file(target, version=f"rollback_{target.stem}", note=f"กู้คืนจาก {filename}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Cloudflare Worker Versioning, Backup & Rollback Tool")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_bak = sub.add_parser("backup", help="แบ็กอัปโค้ดจริงจาก Cloudflare ตอนนี้")
    p_bak.add_argument("--version", default="v3.1", help="ป้ายเวอร์ชัน เช่น v3.1")
    p_bak.add_argument("--note", default="", help="หมายเหตุบันทึกใน CHANGELOG")

    p_dep = sub.add_parser("deploy", help="แบ็กอัปของเก่าแล้ว Deploy เวอร์ชันใหม่")
    p_dep.add_argument("--file", required=True, help="ไฟล์ worker.js ที่ต้องการ Deploy")
    p_dep.add_argument("--version", required=True, help="ป้ายเวอร์ชันใหม่ เช่น v3.2")
    p_dep.add_argument("--note", default="", help="สรุปการแก้ไข")

    sub.add_parser("list", help="แสดงรายการไฟล์แบ็กอัปทุกเวอร์ชัน")

    p_rb = sub.add_parser("rollback", help="กู้คืนเวอร์ชันเก่ากลับขึ้น Cloudflare ทันที")
    p_rb.add_argument("filename", help="ชื่อไฟล์ใน backups/cf_workers/")

    args = parser.parse_args()
    if args.cmd == "backup":
        backup_live_worker(version=args.version, note=args.note)
    elif args.cmd == "deploy":
        deploy_worker_file(Path(args.file), version=args.version, note=args.note)
    elif args.cmd == "list":
        list_backups()
    elif args.cmd == "rollback":
        rollback_backup(args.filename)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
