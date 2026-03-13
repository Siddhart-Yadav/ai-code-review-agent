#!/bin/bash
# ─────────────────────────────────────────────────────────────
# Quick deploy — pull latest code and restart
# Run this every time you push changes to GitHub
# Usage: bash deploy/deploy.sh
# ─────────────────────────────────────────────────────────────

set -e

cd ~/ai-code-review-agent

echo "=== Pulling latest code ==="
git pull origin main

echo "=== Rebuilding and restarting ==="
docker compose -f docker-compose.prod.yml up -d --build

echo "=== Cleaning up old images ==="
docker image prune -f

echo "=== Done! ==="
docker compose -f docker-compose.prod.yml ps
