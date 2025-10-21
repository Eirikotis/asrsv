# Asset Reserve Dashboard

A real-time dashboard for monitoring asset reserve metrics, built with FastAPI and featuring automatic data collection every 30 minutes.

## Features

- **Real-time Metrics**: Price, market cap, circulating supply, and volume tracking
- **Portfolio Composition**: Visual breakdown of asset holdings
- **Fee Tracking**: 30-minute, 24-hour, and all-time fee calculations
- **Auto-refresh**: Automatic data collection every 30 minutes
- **Modern UI**: Cypherpunk-themed dashboard with responsive design

## Quick Start

### Local Development

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd asrsv
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

4. **Run the application**
   ```bash
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```

5. **Visit the dashboard**
   Open http://127.0.0.1:8000 in your browser

### VPS Deployment

1. **Run the deployment script**
   ```bash
   chmod +x deploy.sh
   ./deploy.sh
   ```

2. **Configure environment variables**
   ```bash
   sudo nano /opt/asrsv/.env
   # Add your API keys
   ```

3. **Restart the service**
   ```bash
   sudo systemctl restart asrsv
   sudo systemctl status asrsv
   ```

## Configuration

### Environment Variables

Create a `.env` file with the following variables:

```bash
# API Keys
BIRDEYE_API_KEY=your_birdeye_api_key_here
HELIUS_API_KEY=your_helius_api_key_here

# Database
DATABASE_URL=sqlite:///asset_reserve_metrics.sqlite

# Server settings
HOST=0.0.0.0
PORT=8000
```

### API Keys Required

- **BirdEye API**: For token price and market data
- **Helius RPC**: For blockchain data and token supply

## Architecture

```
asrsv/
├── app/                    # FastAPI application
│   ├── main.py            # Main application with routes
│   ├── db.py              # Database operations
│   └── auto_refresh.py    # Background data collection
├── core/                   # Core snapshot logic
│   └── snapshot.py        # Data collection from APIs
├── static/                # Static assets
│   └── images/           # Logo and images
├── templates/             # HTML templates
├── scripts/               # Utility scripts
└── requirements.txt       # Python dependencies
```

## Auto-refresh System

The application automatically collects data every 30 minutes using a background thread:

- **Interval**: 30 minutes (configurable)
- **Data Sources**: BirdEye API, Helius RPC, Meteora API
- **Storage**: SQLite database
- **Resilience**: Automatic restart on failure

## Fee Calculation

Simple and accurate fee tracking:

- **30m Fees**: `24h_fees ÷ 48`
- **All-time Fees**: `SUM(24h_fees ÷ 48)` from all snapshots
- **Real-time Updates**: Calculated on each page load

## API Endpoints

- `GET /` - Main dashboard
- `GET /api/portfolio-composition` - Portfolio data for charts
- `GET /api/time-series` - Time series data for charts
- `GET /api/auto-refresh-status` - Auto-refresh status
- `POST /api/trigger-snapshot` - Manual snapshot trigger

## Monitoring

Check service status:
```bash
sudo systemctl status asrsv
sudo journalctl -u asrsv -f
```

## Security

- API keys stored in environment variables
- Nginx reverse proxy with security headers
- Systemd service for process management
- Automatic restart on failure

## License

Private project - All rights reserved.
