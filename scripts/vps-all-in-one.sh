#!/bin/bash
# =============================================================================
# 🚀 GoClaw ALL-IN-ONE Setup Script
# =============================================================================
# Chỉ cần SSH vào VPS và chạy:
#   curl -fsSL https://raw.githubusercontent.com/buisytymkt-coder/AI/main/scripts/vps-all-in-one.sh | bash
#
# Hoặc copy-paste toàn bộ script này vào terminal VPS.
# =============================================================================

set -e
export DEBIAN_FRONTEND=noninteractive

DOMAIN="abc.jocohome.shop"
REPO_URL="https://github.com/buisytymkt-coder/AI.git"
GOCLAW_DIR="/opt/goclaw"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║  🐙 GoClaw All-In-One Deployment Script     ║"
echo "║  Domain: $DOMAIN                  ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ─────────────────────────────────────────────────
# PHASE 1: System Preparation
# ─────────────────────────────────────────────────
echo "━━━ PHASE 1: System Preparation ━━━"

echo "[1.1] Updating system packages..."
sudo apt update -y && sudo apt upgrade -y

echo "[1.2] Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker $USER
    echo "  ✅ Docker installed: $(docker --version)"
else
    echo "  ✅ Docker already installed: $(docker --version)"
fi

# Ensure docker compose plugin is available
if ! docker compose version &> /dev/null; then
    sudo apt install -y docker-compose-plugin
fi
echo "  ✅ Docker Compose: $(docker compose version)"

echo "[1.3] Installing Nginx, Certbot, Git, Make..."
sudo apt install -y nginx certbot python3-certbot-nginx git make ufw fail2ban

echo "[1.4] Configuring Firewall..."
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 25300/tcp
echo "y" | sudo ufw enable 2>/dev/null || true
echo "  ✅ Firewall configured"
sudo ufw status numbered

echo ""
echo "━━━ PHASE 1 COMPLETE ━━━"
echo ""

# ─────────────────────────────────────────────────
# PHASE 2: Clone & Configure GoClaw
# ─────────────────────────────────────────────────
echo "━━━ PHASE 2: Clone & Configure ━━━"

echo "[2.1] Cloning GoClaw repository..."
if [ -d "$GOCLAW_DIR/.git" ]; then
    echo "  Repository exists, pulling latest..."
    cd "$GOCLAW_DIR"
    git fetch origin main
    git reset --hard origin/main
else
    sudo rm -rf "$GOCLAW_DIR"
    sudo git clone "$REPO_URL" "$GOCLAW_DIR"
    sudo chown -R $USER:$USER "$GOCLAW_DIR"
fi
cd "$GOCLAW_DIR"

echo "[2.2] Generating .env with secrets..."
chmod +x prepare-env.sh
./prepare-env.sh

# Add POSTGRES_PASSWORD if missing
if ! grep -q "POSTGRES_PASSWORD=.\+" .env 2>/dev/null; then
    PG_PASS=$(openssl rand -base64 24 | tr -d '/+=')
    # Check if key exists but empty
    if grep -q "^POSTGRES_PASSWORD=" .env 2>/dev/null; then
        sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$PG_PASS|" .env
    else
        echo "POSTGRES_PASSWORD=$PG_PASS" >> .env
    fi
    echo "  [generated] POSTGRES_PASSWORD"
else
    echo "  [exists]    POSTGRES_PASSWORD"
fi

chmod 600 .env
echo "  ✅ .env configured"

echo ""
echo "━━━ PHASE 2 COMPLETE ━━━"
echo ""

# ─────────────────────────────────────────────────
# PHASE 3: Start Docker Services
# ─────────────────────────────────────────────────
echo "━━━ PHASE 3: Starting Docker Services ━━━"

echo "[3.1] Starting GoClaw + PostgreSQL..."
cd "$GOCLAW_DIR"

# Need to reload group membership for docker without re-login
if ! groups | grep -q docker; then
    echo "  Adding current user to docker group..."
    sudo usermod -aG docker $USER
    # Run make up with sudo for this session
    sudo -E make up
else
    make up
fi

echo "[3.2] Waiting for GoClaw health check..."
HEALTHY=false
for i in $(seq 1 60); do
    if curl -sf http://localhost:18790/health > /dev/null 2>&1; then
        echo "  ✅ GoClaw is healthy! (attempt $i)"
        HEALTHY=true
        break
    fi
    if [ $((i % 5)) -eq 0 ]; then
        echo "  Waiting... attempt $i/60"
    fi
    sleep 3
done

if [ "$HEALTHY" = false ]; then
    echo "  ⚠️  Health check did not pass in 3 minutes."
    echo "  Checking Docker logs..."
    docker compose -f docker-compose.yml -f docker-compose.postgres.yml logs --tail=30 goclaw
    echo ""
    echo "  The services may still be starting. Continue with Nginx setup..."
fi

echo ""
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo ""
echo "━━━ PHASE 3 COMPLETE ━━━"
echo ""

# ─────────────────────────────────────────────────
# PHASE 4: Nginx Reverse Proxy + SSL
# ─────────────────────────────────────────────────
echo "━━━ PHASE 4: Nginx + SSL ━━━"

echo "[4.1] Configuring Nginx reverse proxy..."
sudo tee /etc/nginx/sites-available/goclaw > /dev/null << 'NGINX_EOF'
# GoClaw Reverse Proxy - abc.jocohome.shop
server {
    listen 80;
    server_name abc.jocohome.shop;

    location / {
        proxy_pass http://127.0.0.1:18790;
        proxy_http_version 1.1;

        # WebSocket support (critical for GoClaw real-time features)
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Standard proxy headers
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeout settings (important for LLM streaming responses)
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
        proxy_connect_timeout 75s;

        # Disable buffering for streaming
        proxy_buffering off;
        proxy_cache off;

        # Max upload size
        client_max_body_size 50M;
    }

    location /health {
        proxy_pass http://127.0.0.1:18790/health;
        access_log off;
    }
}
NGINX_EOF

sudo ln -sf /etc/nginx/sites-available/goclaw /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

echo "[4.2] Testing Nginx config..."
sudo nginx -t

echo "[4.3] Reloading Nginx..."
sudo systemctl reload nginx
echo "  ✅ Nginx configured!"

echo "[4.4] Installing SSL certificate (Let's Encrypt)..."
sudo certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --register-unsafely-without-email 2>&1 || {
    echo ""
    echo "  ⚠️  SSL certificate failed. This might be because:"
    echo "  - DNS hasn't propagated yet (wait 5-10 minutes and retry)"
    echo "  - Port 80 is not reachable from internet"
    echo ""
    echo "  Retry manually: sudo certbot --nginx -d $DOMAIN"
    echo ""
}

# Verify SSL auto-renewal
sudo certbot renew --dry-run 2>/dev/null && echo "  ✅ SSL auto-renewal verified" || true

echo ""
echo "━━━ PHASE 4 COMPLETE ━━━"
echo ""

# ─────────────────────────────────────────────────
# PHASE 5: Security & Backup
# ─────────────────────────────────────────────────
echo "━━━ PHASE 5: Security & Backup ━━━"

echo "[5.1] Enabling fail2ban..."
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
echo "  ✅ fail2ban active"

echo "[5.2] Creating SSH deploy key for GitHub Actions..."
if [ ! -f "$GOCLAW_DIR/deploy_key" ]; then
    ssh-keygen -t ed25519 -C "github-actions-deploy" -f "$GOCLAW_DIR/deploy_key" -N ""
    mkdir -p ~/.ssh
    cat "$GOCLAW_DIR/deploy_key.pub" >> ~/.ssh/authorized_keys
    chmod 700 ~/.ssh
    chmod 600 ~/.ssh/authorized_keys
    chmod 600 "$GOCLAW_DIR/deploy_key"
    echo "  ✅ Deploy key created"
else
    echo "  Deploy key already exists"
fi

echo "[5.3] Setting up daily database backup..."
sudo tee "$GOCLAW_DIR/backup.sh" > /dev/null << 'BACKUP_EOF'
#!/bin/bash
BACKUP_DIR="/opt/goclaw/backups"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"

docker compose -f /opt/goclaw/docker-compose.yml \
  -f /opt/goclaw/docker-compose.postgres.yml \
  exec -T postgres pg_dump -U goclaw goclaw \
  | gzip > "$BACKUP_DIR/goclaw_${DATE}.sql.gz"

# Keep only last 7 backups
ls -t "$BACKUP_DIR"/goclaw_*.sql.gz 2>/dev/null | tail -n +8 | xargs -r rm --

echo "[$(date)] Backup completed: goclaw_${DATE}.sql.gz"
BACKUP_EOF

chmod +x "$GOCLAW_DIR/backup.sh"
(crontab -l 2>/dev/null | grep -v "goclaw/backup.sh"; echo "0 3 * * * /opt/goclaw/backup.sh >> /var/log/goclaw-backup.log 2>&1") | crontab -
echo "  ✅ Daily backup configured (3:00 AM)"

echo ""
echo "━━━ PHASE 5 COMPLETE ━━━"
echo ""

# ─────────────────────────────────────────────────
# FINAL SUMMARY
# ─────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║  🎉 GoClaw Deployment COMPLETE!              ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "  🌐 Dashboard:  https://$DOMAIN"
echo "  🏥 Health:     https://$DOMAIN/health"
echo ""
echo "  📋 Docker containers:"
docker ps --format "  │ {{.Names}}\t{{.Status}}" 2>/dev/null || true
echo ""
echo "  🔑 GitHub Actions Secrets to configure:"
echo "  ┌──────────────────────────────────────────────┐"
echo "  │ VPS_HOST    → 104.36.23.199                  │"
echo "  │ VPS_PORT    → 25300                          │"
echo "  │ VPS_USER    → Administrator                  │"
echo "  │ VPS_SSH_KEY → (private key below)            │"
echo "  └──────────────────────────────────────────────┘"
echo ""

if [ -f "$GOCLAW_DIR/deploy_key" ]; then
    echo "  ====== PRIVATE KEY (copy to GitHub Secret VPS_SSH_KEY) ======"
    cat "$GOCLAW_DIR/deploy_key"
    echo "  ============================================================="
fi

echo ""
echo "  📌 Useful commands:"
echo "    cd /opt/goclaw"
echo "    make logs          # View live logs"
echo "    make down          # Stop all services"
echo "    make up            # Start/update services"
echo "    make reset         # ⚠️ Wipe data and restart"
echo "    ./backup.sh        # Manual database backup"
echo ""
echo "  🔄 To update GoClaw:"
echo "    cd /opt/goclaw && git pull origin main && make up"
echo ""
