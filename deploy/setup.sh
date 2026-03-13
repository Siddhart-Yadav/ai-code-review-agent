#!/bin/bash
# ─────────────────────────────────────────────────────────────
# EC2 Setup Script — AI Code Review Agent
# Run this once on a fresh Ubuntu 22.04 EC2 instance (t2.micro)
# Usage: ssh into EC2, then: bash setup.sh
# ─────────────────────────────────────────────────────────────

set -e

echo "=== Updating system ==="
sudo apt update && sudo apt upgrade -y

echo "=== Installing Docker ==="
sudo apt install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Let current user run docker without sudo
sudo usermod -aG docker $USER

echo "=== Installing Git ==="
sudo apt install -y git

echo "=== Cloning repo ==="
cd ~
git clone https://github.com/Siddhart-Yadav/ai-code-review-agent.git
cd ai-code-review-agent

echo "=== Setting up environment ==="
cp backend/.env.example backend/.env

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Setup complete! Next steps:                                ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║                                                            ║"
echo "║  1. LOG OUT AND LOG BACK IN (for docker group to apply):   ║"
echo "║     exit                                                   ║"
echo "║     ssh -i your-key.pem ubuntu@YOUR_EC2_IP                 ║"
echo "║                                                            ║"
echo "║  2. Add your Groq API key:                                 ║"
echo "║     cd ~/ai-code-review-agent                              ║"
echo "║     nano backend/.env                                      ║"
echo "║     # Set: GROQ_API_KEY=gsk_your_key_here                  ║"
echo "║                                                            ║"
echo "║  3. Start the app:                                         ║"
echo "║     docker compose -f docker-compose.prod.yml up -d --build║"
echo "║                                                            ║"
echo "║  4. Open in browser:                                       ║"
echo "║     http://YOUR_EC2_PUBLIC_IP                               ║"
echo "║                                                            ║"
echo "║  Optional — Add SSL (after pointing a domain to this IP):  ║"
echo "║     bash deploy/ssl.sh your-domain.com                     ║"
echo "║                                                            ║"
echo "╚══════════════════════════════════════════════════════════════╝"
