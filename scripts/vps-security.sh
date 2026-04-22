#!/bin/bash
# =============================================================================
# GoClaw VPS Security & Backup - Phase 3
# =============================================================================

set -e

echo "============================================"
echo "  GoClaw VPS Setup - Phase 3: Security"
echo "============================================"

# --- 1. Install fail2ban ---
echo "[1/4] Installing fail2ban..."
sudo apt install -y fail2ban
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
echo "  ✅ fail2ban active"

# --- 2. SSH Deploy Key for GitHub Actions ---
echo "[2/4] Creating SSH deploy key..."
if [ ! -f /opt/goclaw/deploy_key ]; then
    ssh-keygen -t ed25519 -C "github-actions-deploy" -f /opt/goclaw/deploy_key -N ""
    cat /opt/goclaw/deploy_key.pub >> ~/.ssh/authorized_keys
    chmod 600 ~/.ssh/authorized_keys
    echo ""
    echo "  ✅ Deploy key created!"
    echo ""
    echo "  ===== COPY THIS PRIVATE KEY TO GITHUB SECRETS (VPS_SSH_KEY) ====="
    echo ""
    cat /opt/goclaw/deploy_key
    echo ""
    echo "  ================================================================="
    echo ""
else
    echo "  Deploy key already exists"
fi

# --- 3. Backup script ---
echo "[3/4] Setting up automatic database backup..."
sudo tee /opt/goclaw/backup.sh > /dev/null << 'BACKUP_SCRIPT'
#!/bin/bash
BACKUP_DIR="/opt/goclaw/backups"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"

docker compose -f /opt/goclaw/docker-compose.yml \
  -f /opt/goclaw/docker-compose.postgres.yml \
  exec -T postgres pg_dump -U goclaw goclaw \
  | gzip > "$BACKUP_DIR/goclaw_${DATE}.sql.gz"

# Keep only last 7 backups
ls -t "$BACKUP_DIR"/goclaw_*.sql.gz | tail -n +8 | xargs -r rm --

echo "[$(date)] Backup completed: goclaw_${DATE}.sql.gz"
BACKUP_SCRIPT

chmod +x /opt/goclaw/backup.sh

# Add cron job for daily backup at 3 AM
(crontab -l 2>/dev/null | grep -v "goclaw/backup.sh"; echo "0 3 * * * /opt/goclaw/backup.sh >> /var/log/goclaw-backup.log 2>&1") | crontab -
echo "  ✅ Daily backup configured (3:00 AM)"

# --- 4. Secure .env ---
echo "[4/4] Securing configuration files..."
chmod 600 /opt/goclaw/.env
chmod 600 /opt/goclaw/deploy_key 2>/dev/null || true

echo ""
echo "============================================"
echo "  🔒 Security Setup COMPLETE!"
echo "============================================"
echo ""
echo "  GitHub Actions Secrets to add:"
echo "    VPS_HOST      → 104.36.23.199"
echo "    VPS_PORT      → 25300"
echo "    VPS_USER      → Administrator"
echo "    VPS_SSH_KEY   → (private key shown above)"
echo ""
echo "  All done! Your GoClaw is live at:"
echo "    https://abc.jocohome.shop"
echo ""
