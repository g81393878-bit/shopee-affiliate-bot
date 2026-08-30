#!/usr/bin/env bash
# ==============================================================================
# Shopee Affiliate Automation — 1-Click Ubuntu/Debian VPS Installer
# ==============================================================================
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=====================================================================${NC}"
echo -e "${GREEN}   Shopee Affiliate Bot & Reels Automation — VPS 1-Click Installer   ${NC}"
echo -e "${BLUE}=====================================================================${NC}"
echo ""

if [ "$EUID" -ne 0 ]; then
  SUDO="sudo"
else
  SUDO=""
fi

echo -e "\n${YELLOW}[1/5] 📦 กำลังติดตั้ง System Packages, FFmpeg และฟอนต์ภาษาไทย...${NC}"
$SUDO apt update -y
$SUDO apt install -y python3 python3-pip python3-venv ffmpeg fonts-thai-tlwg fonts-noto-cjk git curl jq build-essential

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo -e "\n${YELLOW}[2/5] 🐍 กำลังตั้งค่า Python Virtual Environment (.venv)...${NC}"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate

echo -e "\n${YELLOW}[3/5] 📚 กำลังติดตั้ง Python Dependencies...${NC}"
pip install --upgrade pip
pip install -r backend/requirements.txt

echo -e "\n${YELLOW}[4/5] 🔐 กำลังตรวจสอบการตั้งค่า Environment Variables (.env)...${NC}"
if [ ! -f "backend/.env" ]; then
    echo -e "${RED}⚠️  ไม่พบไฟล์ backend/.env!${NC}"
    if [ -f "backend/.env.example" ]; then
        cp backend/.env.example backend/.env
        echo -e "${YELLOW}ℹ️  สร้างไฟล์ backend/.env ให้แล้ว กรุณาใส่ API Keys ให้ครบถ้วน${NC}"
    fi
else
    echo -e "${GREEN}✅ พบไฟล์ backend/.env เรียบร้อยแล้ว${NC}"
fi

echo -e "\n${YELLOW}[5/5] ⚙️  กำลังตั้งค่าระบบบริการอัตโนมัติ 24/7 (systemd service)...${NC}"
CURRENT_USER=$(logname 2>/dev/null || echo $USER)
SERVICE_FILE="/etc/systemd/system/shopee-bot.service"

$SUDO bash -c "cat <<EOF > $SERVICE_FILE
[Unit]
Description=Shopee Affiliate Reels & AI Automation 24/7
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/.venv/bin/python tools/system_runner.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF"

$SUDO systemctl daemon-reload
$SUDO systemctl enable shopee-bot.service

echo -e "\n${GREEN}=====================================================================${NC}"
echo -e "${GREEN}🎉 ติดตั้งและตั้งค่าระบบบอทบน VPS เสร็จสมบูรณ์ 100%!${NC}"
echo -e "${GREEN}=====================================================================${NC}"
echo -e "คำสั่งควบคุมบอท:"
echo -e "  ▶️  เริ่มการทำงาน 24/7 : ${YELLOW}sudo systemctl start shopee-bot${NC}"
echo -e "  ⏹️  หยุดการทำงาน       : ${YELLOW}sudo systemctl stop shopee-bot${NC}"
echo -e "  🔄 เริ่มการทำงานใหม่   : ${YELLOW}sudo systemctl restart shopee-bot${NC}"
echo -e "  📊 ตรวจสอบสถานะ        : ${YELLOW}sudo systemctl status shopee-bot${NC}"
echo -e "  📜 ดูการทำงานสด (Logs) : ${YELLOW}sudo journalctl -u shopee-bot -f${NC}"
echo -e "  🎛️  เมนูจัดการสะดวก     : ${YELLOW}./tools/vps_manager.sh${NC}"
echo ""
