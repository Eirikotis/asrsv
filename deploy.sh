#!/bin/bash
# Deployment script for VPS

set -e

echo "🚀 Deploying Asset Reserve Dashboard..."

# Update system
sudo apt update

# Install Python and dependencies
sudo apt install -y python3 python3-pip python3-venv nginx

# Create application directory
sudo mkdir -p /opt/asrsv
sudo chown $USER:$USER /opt/asrsv

# Copy application files
cp -r . /opt/asrsv/

# Create virtual environment
cd /opt/asrsv
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp .env.example .env
echo "⚠️  Please edit /opt/asrsv/.env with your actual API keys"

# Setup systemd service
sudo cp asrsv.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable asrsv
sudo systemctl start asrsv

# Setup nginx
sudo cp nginx.conf /etc/nginx/sites-available/asrsv
sudo ln -sf /etc/nginx/sites-available/asrsv /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx

echo "✅ Deployment complete!"
echo "📝 Don't forget to:"
echo "   1. Edit /opt/asrsv/.env with your API keys"
echo "   2. Restart the service: sudo systemctl restart asrsv"
echo "   3. Check status: sudo systemctl status asrsv"
