#!/usr/bin/env bash
# ==============================================================================
# tools/vps_manager.sh — Shopee Bot Management Console for Linux VPS
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$ROOT_DIR"

if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

show_menu() {
    clear
    echo "====================================================================="
    echo "   🎬 Shopee Affiliate Bot & Reels Manager (Linux VPS Console)       "
    echo "====================================================================="
    echo ""
    echo "  [1] 📊 ตรวจสอบสถานะบอท (Service Status)"
    echo "  [2] ▶️  เริ่มการทำงาน 24/7 (Start Bot Service)"
    echo "  [3] ⏹️  หยุดการทำงานบอท (Stop Bot Service)"
    echo "  [4] 🔄 เริ่มต้นการทำงานใหม่ (Restart Bot Service)"
    echo "  [5] 📜 ดูบันทึกการทำงานสด (Live Logs Stream)"
    echo "  [6] 🎬 ผลิตคลิปวิดีโอใหม่ทันที (Produce 3 Videos Now)"
    echo "  [7] 🚀 บังคับโพสต์คลิปทันที 1 รายการ (Force Upload 4 Channels)"
    echo "  [8] 🚪 ออกจากเมนู"
    echo ""
    echo "====================================================================="
    read -p "กรุณาเลือกเมนู (1-8): " choice
}

while true; do
    show_menu
    case $choice in
        1)
            sudo systemctl status shopee-bot
            read -p "กด Enter เพื่อกลับสู่เมนูหลัก..."
            ;;
        2)
            sudo systemctl start shopee-bot
            echo "✅ สั่งเปิดบอท 24/7 เรียบร้อยแล้ว!"
            sleep 2
            ;;
        3)
            sudo systemctl stop shopee-bot
            echo "🛑 สั่งหยุดบอทเรียบร้อยแล้ว!"
            sleep 2
            ;;
        4)
            sudo systemctl restart shopee-bot
            echo "🔄 รีสตาร์ทบอทเรียบร้อยแล้ว!"
            sleep 2
            ;;
        5)
            echo "กำลังเปิด Live Logs (กด Ctrl+C เพื่อออก)..."
            sudo journalctl -u shopee-bot -f
            ;;
        6)
            python3 reels_uploader/auto_product_reels.py 3
            read -p "กด Enter เพื่อกลับสู่เมนูหลัก..."
            ;;
        7)
            python3 reels_uploader/uploader.py --force
            read -p "กด Enter เพื่อกลับสู่เมนูหลัก..."
            ;;
        8)
            echo "ออกจากเมนูแล้วครับ"
            exit 0
            ;;
        *)
            echo "ตัวเลือกไม่ถูกต้อง กรุณาลองใหม่"
            sleep 1
            ;;
    esac
done
