#!/bin/bash
# =============================================================================
# GoClaw VPS Start Script - Phase 2: Docker Services + Nginx + SSL
# Domain: abc.jocohome.shop
# =============================================================================

set -e

echo "============================================"
echo "  GoClaw VPS Setup - Phase 2: Services"
echo "============================================"

# --- 1. Start Docker services ---
echo "[1/4] Starting GoClaw Docker services..."
cd /opt/goclaw

# Ensure 1 vCPU VPS can run compose limits safely
cat > /opt/goclaw/docker-compose.override.yml << 'OVERRIDE_EOF'
services:
  goclaw:
    deploy:
      resources:
        limits:
          cpus: "0.90"
          memory: 768M
          pids: 200
OVERRIDE_EOF

make up

echo "Waiting for GoClaw to be healthy..."
HEALTHY=false
for i in $(seq 1 30); do
    if curl -sf http://localhost:18790/health > /dev/null 2>&1; then
        echo "  ✅ GoClaw is healthy!"
        HEALTHY=true
        break
    fi
    echo "  Attempt $i/30 - waiting 5s..."
    sleep 5
done

if [ "$HEALTHY" = false ]; then
    echo "  ⚠️  GoClaw health check timeout. Showing recent logs..."
    docker compose -f docker-compose.yml -f docker-compose.postgres.yml logs --tail=80 goclaw || true
fi

# Verify
docker ps
echo ""

# --- 2. Configure Nginx ---
echo "[2/4] Configuring Nginx reverse proxy..."
sudo tee /etc/nginx/sites-available/goclaw > /dev/null << 'NGINX_CONF'
server {
    listen 80;
    server_name abc.jocohome.shop;

    location / {
        proxy_pass http://127.0.0.1:18790;
        proxy_http_version 1.1;

        # WebSocket support
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Proxy headers
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeout (important for LLM streaming)
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
NGINX_CONF

sudo ln -sf /etc/nginx/sites-available/goclaw /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
echo "  ✅ Nginx configured!"

# --- 3. SSL Certificate ---
echo "[3/4] Installing SSL certificate..."
sudo certbot --nginx -d abc.jocohome.shop --non-interactive --agree-tos --register-unsafely-without-email || {
    echo "  ⚠️  Certbot failed. You can retry manually:"
    echo "  sudo certbot --nginx -d abc.jocohome.shop"
}

# --- 4. Verify ---
echo "[4/4] Verifying deployment..."
echo ""
echo "============================================"
echo "  🎉 GoClaw Deployment COMPLETE!"
echo "============================================"
echo ""
echo "  Dashboard: https://abc.jocohome.shop"
echo "  Health:    https://abc.jocohome.shop/health"
echo ""
echo "  Useful commands:"
echo "    cd /opt/goclaw"
echo "    make logs       # View logs"
echo "    make down       # Stop services"
echo "    make up         # Start/update services"
echo ""
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo ""
