#!/bin/bash
# ─────────────────────────────────────────────────────────────
# SSL Setup — Get free Let's Encrypt cert for your domain
# Usage: bash deploy/ssl.sh yourdomain.com
# Prerequisites: Domain DNS must already point to this EC2 IP
# ─────────────────────────────────────────────────────────────

set -e

DOMAIN=$1

if [ -z "$DOMAIN" ]; then
    echo "Usage: bash deploy/ssl.sh yourdomain.com"
    exit 1
fi

echo "=== Getting SSL cert for $DOMAIN ==="

# Create certbot dirs
mkdir -p deploy/certbot/conf deploy/certbot/www

# Get cert using standalone mode (stop nginx briefly)
docker compose -f docker-compose.prod.yml stop nginx

docker run --rm \
    -p 80:80 \
    -v "$(pwd)/deploy/certbot/conf:/etc/letsencrypt" \
    -v "$(pwd)/deploy/certbot/www:/var/www/certbot" \
    certbot/certbot certonly \
    --standalone \
    -d "$DOMAIN" \
    --non-interactive \
    --agree-tos \
    --email siddharthyadav555@gmail.com

echo "=== Updating nginx config for HTTPS ==="

# Replace YOUR_DOMAIN in nginx config
sed -i "s/YOUR_DOMAIN/$DOMAIN/g" deploy/nginx.conf

# Uncomment the HTTPS server block
sed -i 's/^# \(.*listen 443\)/\1/' deploy/nginx.conf
sed -i 's/^# \(.*server_name\)/\1/' deploy/nginx.conf
sed -i 's/^# \(.*ssl_certificate\)/\1/' deploy/nginx.conf
sed -i 's/^# \(.*proxy_\)/\1/' deploy/nginx.conf
sed -i 's/^# \(.*location\)/\1/' deploy/nginx.conf
sed -i 's/^# \(.*}\)/\1/' deploy/nginx.conf
sed -i 's/^# \(.*proxy_read_timeout\)/\1/' deploy/nginx.conf
sed -i 's/^# \(.*proxy_set_header\)/\1/' deploy/nginx.conf
sed -i 's/^# \(.*proxy_pass\)/\1/' deploy/nginx.conf

# Enable HTTP → HTTPS redirect
sed -i 's/^    # return 301/    return 301/' deploy/nginx.conf

# Restart everything
docker compose -f docker-compose.prod.yml up -d

echo ""
echo "=== Done! Your app is live at https://$DOMAIN ==="
