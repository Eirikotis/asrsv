# VPS Deployment Checklist

## Pre-Deployment

- [ ] **API Keys**: Get your BirdEye and Helius API keys
- [ ] **Domain**: Set up your domain name (optional, can use IP)
- [ ] **VPS**: Ubuntu 20.04+ VPS with root access

## Deployment Steps

### 1. Upload to GitHub
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin <your-github-repo>
git push -u origin main
```

### 2. VPS Setup
```bash
# Clone the repository
git clone <your-github-repo>
cd asrsv

# Run deployment script
chmod +x deploy.sh
./deploy.sh
```

### 3. Configure Environment
```bash
# Edit environment variables
sudo nano /opt/asrsv/.env

# Add your API keys:
BIRDEYE_API_KEY=your_actual_key_here
HELIUS_API_KEY=your_actual_key_here
```

### 4. Start Services
```bash
# Restart the application
sudo systemctl restart asrsv

# Check status
sudo systemctl status asrsv
sudo journalctl -u asrsv -f
```

### 5. Configure Domain (Optional)
```bash
# Edit nginx config
sudo nano /etc/nginx/sites-available/asrsv

# Update server_name
server_name your-domain.com;

# Test and reload
sudo nginx -t
sudo systemctl reload nginx
```

## Verification

- [ ] **Dashboard**: Visit http://your-vps-ip or http://your-domain.com
- [ ] **Auto-refresh**: Check logs for "Auto-refresh started (interval: 30 minutes)"
- [ ] **Charts**: Verify all charts load correctly
- [ ] **Metrics**: Check that fee calculations work
- [ ] **Logo**: Confirm logo displays properly

## Monitoring

```bash
# Check service status
sudo systemctl status asrsv

# View logs
sudo journalctl -u asrsv -f

# Check auto-refresh
curl http://localhost:8000/api/auto-refresh-status
```

## Troubleshooting

### Service won't start
```bash
# Check logs
sudo journalctl -u asrsv -n 50

# Check environment
sudo -u www-data cat /opt/asrsv/.env
```

### Charts not loading
- Check browser console for errors
- Verify API endpoints: `/api/portfolio-composition`, `/api/time-series`
- Check database has data: `sqlite3 /opt/asrsv/asset_reserve_metrics.sqlite`

### Auto-refresh not working
- Check logs: `sudo journalctl -u asrsv -f`
- Verify API keys in `.env`
- Test manual snapshot: `curl -X POST http://localhost:8000/api/trigger-snapshot`

## Security Notes

- ✅ API keys in environment variables (not in code)
- ✅ Nginx reverse proxy with security headers
- ✅ Systemd service for process management
- ✅ Automatic restart on failure
- ✅ Database file permissions secured

## Maintenance

### Update Application
```bash
cd /opt/asrsv
git pull origin main
sudo systemctl restart asrsv
```

### Backup Database
```bash
# Create backup
cp /opt/asrsv/asset_reserve_metrics.sqlite /opt/asrsv/backup_$(date +%Y%m%d).sqlite

# Restore from backup
cp /opt/asrsv/backup_20240101.sqlite /opt/asrsv/asset_reserve_metrics.sqlite
sudo systemctl restart asrsv
```

### Log Rotation
```bash
# Logs are managed by systemd journal
sudo journalctl --vacuum-time=7d
```
