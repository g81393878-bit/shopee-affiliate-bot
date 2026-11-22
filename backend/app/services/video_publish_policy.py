"""Shared final preflight for every supported video uploader."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def public_text_block_reason(text):
    text = str(text or '')
    if any(k in text for k in ('ปลาสลิด', 'ปลาแดดเดียว', 'โรงตาก', 'สุพรรณ')):
        return ''
    if 'ราคา' in text or re.search(r'(?:\d[\d,.]*\s*(?:บาท|฿)|฿\s*\d)', text):
        return 'Price text is not allowed in video titles or captions'
    return ''


def publication_block_reason(video_path, caption="", metadata=None):
    reels = ROOT / "reels_uploader"
    if (reels / ".posting_paused").exists():
        return "Video publishing paused for quality repair"
    meta_text = metadata or {}
    text_reason = public_text_block_reason(str(caption) + ' ' + str(meta_text))
    if text_reason:
        return text_reason
    try:
        path = Path(video_path or "")
        if not path.is_file():
            return "A reviewed local video file is required"
        meta = metadata or {}
        product = (re.search(r"(?:^|_)prod_\d+_", path.name) is not None
                   or meta.get("content_mode") == "PRODUCT_HIGHLIGHT"
                   or bool(meta.get("affiliate_link")) or meta.get("product_id") is not None
                   or any(term in str(caption).lower() for term in ("shopee", "พิกัดสั่งซื้อ")))
        if product and (reels / ".product_posting_paused").exists():
            return "Product videos paused: restore varied, reviewed content first"
        approvals_path = reels / "video_quality_approvals.json"
        if approvals_path.exists():
            approvals = json.loads(approvals_path.read_text(encoding="utf-8"))
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            fingerprint = digest.hexdigest()
            approval = approvals.get(fingerprint, {})
            if approval.get("status") == "rejected":
                return "Video quality review rejected"
        return ""
    except (OSError, ValueError, TypeError, AttributeError):
        return "Video quality policy unavailable or invalid; publishing blocked"
