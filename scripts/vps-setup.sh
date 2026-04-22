#!/bin/bash
# =============================================================================
# GoClaw VPS Setup Script
# Chạy trực tiếp trên VPS (copy-paste vào SSH terminal)
# Domain: abc.jocohome.shop
# =============================================================================

set -e

echo "============================================"
echo "  GoClaw VPS Setup - Phase 1: System Prep"
echo "============================================"

# --- 1. Cập nhật hệ thống ---
echo "[1/6] Updating system..."
sudo apt update && sudo apt upgrade -y

# --- 2. Cài Docker ---
echo "[2/6] Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker $USER
    echo "Docker installed successfully"
else
    echo "Docker already installed: $(docker --version)"
fi

# --- 3. Cài các packages cần thiết ---
echo "[3/6] Installing required packages..."
sudo apt install -y nginx certbot python3-certbot-nginx git make ufw

# --- 4. Cấu hình Firewall ---
echo "[4/6] Configuring Firewall..."
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 25300/tcp
echo "y" | sudo ufw enable || true
sudo ufw status

# --- 5. Clone repo GoClaw ---
echo "[5/6] Cloning GoClaw..."
if [ ! -d /opt/goclaw ]; then
    sudo git clone https://github.com/buisytymkt-coder/AI.git /opt/goclaw
    sudo chown -R $USER:$USER /opt/goclaw
else
    echo "GoClaw directory already exists, pulling latest..."
    cd /opt/goclaw && git pull origin main
fi

# --- 6. Cấu hình GoClaw ---
echo "[6/6] Configuring GoClaw..."
cd /opt/goclaw
chmod +x prepare-env.sh
./prepare-env.sh

# Thêm POSTGRES_PASSWORD nếu chưa có
if ! grep -q "POSTGRES_PASSWORD=.\+" .env 2>/dev/null; then
    PG_PASS=$(openssl rand -base64 24)
    echo "POSTGRES_PASSWORD=$PG_PASS" >> .env
    echo "  [generated] POSTGRES_PASSWORD"
fi

chmod 600 .env

echo ""
echo "============================================"
echo "  Phase 1 COMPLETE!"
echo "============================================"
echo ""
echo "  .env file created at /opt/goclaw/.env"
echo ""
echo "  Next: Run phase 2 (start Docker services)"
echo "  → bash /opt/goclaw/scripts/vps-start.sh"
echo ""
