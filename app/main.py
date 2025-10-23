import os
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Load environment variables
load_dotenv()

from app.db import migrate, q
from app.auto_refresh import start_auto_refresh, get_auto_refresh_status
# Removed complex fee accumulation - using simple approach

app = FastAPI(title="ASSET Reserve Dashboard")

# Static and templates
base_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(base_dir)
static_dir = os.path.join(project_root, "static")
templates_dir = os.path.join(project_root, "templates")

os.makedirs(static_dir, exist_ok=True)
os.makedirs(templates_dir, exist_ok=True)

app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=templates_dir)

# Ensure migrations at startup
migrate()

# Start auto-refresh for VPS deployment (8 hour intervals)
start_auto_refresh(interval_minutes=480)


def _latest_metrics():
	rows = q("""
		SELECT ts_utc, price_usd, fdv_usd, market_cap_usd, circulating_supply, 
		       real_tvl_total_usd, volume_24h_usd, real_yield_daily, apy_simple, apy_compound
		FROM metrics_snapshots 
		ORDER BY ts_utc DESC LIMIT 1
	""")
	if rows:
		# Convert Row object to regular dict for template compatibility
		row = rows[0]
		return {
			'ts_utc': row['ts_utc'],
			'price_usd': row['price_usd'],
			'fdv_usd': row['fdv_usd'],
			'market_cap_usd': row['market_cap_usd'],
			'circulating_supply': row['circulating_supply'],
			'real_tvl_total_usd': row['real_tvl_total_usd'],
			'volume_24h_usd': row['volume_24h_usd'],
			'real_yield_daily': row['real_yield_daily'],
			'apy_simple': row['apy_simple'],
			'apy_compound': row['apy_compound']
		}
	return None


def _pools_for_ts(ts_utc: str):
	return q(
		"""
		SELECT family, source, quote_symbol, real_tvl_usd, volume_24h_usd,
		       fee_24h_usd, daily_yield, apy_simple, quote_units
		FROM pool_snapshots
		WHERE ts_utc = ?
		ORDER BY apy_simple DESC
		""",
		(ts_utc,),
	)


def _get_fee_metrics():
	"""Get simple fee metrics: 8hr = 24h/3, all-time = sum of all 8hr fees"""
	# Get latest 24h fees
	latest_24h = q("""
		SELECT COALESCE(SUM(fee_24h_usd), 0) as total_24h_fees
		FROM pool_snapshots
		WHERE ts_utc = (SELECT MAX(ts_utc) FROM pool_snapshots)
	""")
	
	latest_24h_fees = latest_24h[0]['total_24h_fees'] if latest_24h else 0.0
	fees_8hr = latest_24h_fees / 3.0  # Simple: 8hr = 24h / 3
	
	# Get all-time fees (sum of all 8hr fees)
	all_time = q("""
		SELECT COALESCE(SUM(fee_24h_usd / 3.0), 0) as all_time_fees
		FROM pool_snapshots
	""")
	
	all_time_fees = all_time[0]['all_time_fees'] if all_time else 0.0
	
	return {
		'latest_8hr_fees': fees_8hr,
		'latest_24h_fees': latest_24h_fees,
		'all_time_fees': all_time_fees
	}


def _get_volume_metrics():
	"""Get volume metrics: 8hr = 24h/3, all-time = sum of all 8hr volumes"""
	# Get latest 24h volume
	latest_24h = q("""
		SELECT COALESCE(SUM(volume_24h_usd), 0) as total_24h_volume
		FROM pool_snapshots
		WHERE ts_utc = (SELECT MAX(ts_utc) FROM pool_snapshots)
	""")
	
	latest_24h_volume = latest_24h[0]['total_24h_volume'] if latest_24h else 0.0
	volume_8hr = latest_24h_volume / 3.0  # Simple: 8hr = 24h / 3
	
	# Get all-time volume (sum of all 8hr volumes)
	all_time = q("""
		SELECT COALESCE(SUM(volume_24h_usd / 3.0), 0) as all_time_volume
		FROM pool_snapshots
	""")
	
	all_time_volume = all_time[0]['all_time_volume'] if all_time else 0.0
	
	return {
		'latest_8hr_volume': volume_8hr,
		'latest_24h_volume': latest_24h_volume,
		'all_time_volume': all_time_volume
	}


def _history_summaries():
	# Daily totals from metrics
	return q(
		"""
		SELECT date(substr(ts_utc,1,19)) AS day,
		       SUM(COALESCE(volume_24h_usd,0)) AS vol_sum,
		       SUM(0) AS fees_placeholder,
		       AVG(COALESCE(real_yield_daily,0)) AS real_yield_avg,
		       AVG(COALESCE(apy_simple,0)) AS apy_simple_avg
		FROM metrics_snapshots
		GROUP BY day
		ORDER BY day
		"""
	)


def _history_pool_apy():
	return q(
		"""
		SELECT day, AVG(apy_simple_avg) AS apy_avg
		FROM v_pool_apy_daily
		GROUP BY day
		ORDER BY day
		"""
	)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
	"""Main dashboard page with working chart structure and real data"""
	m = _latest_metrics()
	if not m:
		return templates.TemplateResponse(
			"minimal-with-pools-table-test.html",
			{"request": request, "summary": None, "pools": [], "fees_8hr": 0, "fees_24h": 0, "fees_all_time": 0, "volume_8hr": 0, "volume_24h": 0, "volume_all_time": 0, "liquidity_deployed": 0, "no_data": True},
		)

	pools = _pools_for_ts(m["ts_utc"]) if m else []
	fee_metrics = _get_fee_metrics()
	volume_metrics = _get_volume_metrics()
	
	# Calculate liquidity deployed (market cap + real TVL)
	liquidity_deployed = (m.get('market_cap_usd', 0) or 0) + (m.get('real_tvl_total_usd', 0) or 0)
	
	return templates.TemplateResponse(
		"minimal-with-pools-table-test.html",
		{
			"request": request, 
			"summary": m, 
			"pools": pools, 
			"fees_8hr": fee_metrics['latest_8hr_fees'],
			"fees_24h": fee_metrics['latest_24h_fees'],
			"fees_all_time": fee_metrics['all_time_fees'],
			"volume_8hr": volume_metrics['latest_8hr_volume'],
			"volume_24h": volume_metrics['latest_24h_volume'],
			"volume_all_time": volume_metrics['all_time_volume'],
			"liquidity_deployed": liquidity_deployed,
			"daily_yield": m['real_yield_daily'] if m and 'real_yield_daily' in m else 0,
			"apy_simple": m['apy_simple'] if m and 'apy_simple' in m else 0,
			"apy_compound": m['apy_compound'] if m and 'apy_compound' in m else 0,
			"no_data": False
		},
	)


@app.get("/api/portfolio-composition")
async def portfolio_composition():
	"""Get portfolio composition data for pie chart"""
	rows = q("""
		SELECT quote_symbol, quote_units, quote_price_usd
		FROM pool_snapshots
		WHERE ts_utc = (SELECT MAX(ts_utc) FROM pool_snapshots)
		AND quote_units > 0 AND quote_price_usd > 0
		ORDER BY (quote_units * quote_price_usd) DESC
	""")
	
	composition = []
	total_value = 0.0
	
	for row in rows:
		value = row["quote_units"] * row["quote_price_usd"]
		total_value += value
		composition.append({
			"symbol": row["quote_symbol"],
			"units": row["quote_units"],
			"price": row["quote_price_usd"],
			"value": value
		})
	
	# Calculate percentages
	for item in composition:
		item["percentage"] = (item["value"] / total_value * 100) if total_value > 0 else 0
	
	return JSONResponse({
		"composition": composition,
		"total_value": total_value
	})


@app.get("/api/time-series")
async def time_series():
    """Get time series data for charts"""
    rows = q("""
        SELECT ts_utc, price_usd, market_cap_usd, volume_24h_usd, circulating_supply
        FROM metrics_snapshots
        ORDER BY ts_utc ASC
        LIMIT 100
    """)
    
    time_series_data = {
        "timestamps": [],
        "price": [],
        "market_cap": [],
        "volume_24h": [],
        "circulating_supply": []
    }
    
    for row in rows:
        time_series_data["timestamps"].append(row["ts_utc"])
        time_series_data["price"].append(row["price_usd"] or 0)
        time_series_data["market_cap"].append(row["market_cap_usd"] or 0)
        time_series_data["volume_24h"].append(row["volume_24h_usd"] or 0)
        time_series_data["circulating_supply"].append(row["circulating_supply"] or 0)
    
    return JSONResponse(time_series_data)

@app.get("/test-main", response_class=HTMLResponse)
async def test_main(request: Request):
    """Test main page for chart positioning"""
    return templates.TemplateResponse("test-main.html", {"request": request})

@app.get("/test-simple", response_class=HTMLResponse)
async def test_simple(request: Request):
    """Test simple charts with hardcoded data"""
    return templates.TemplateResponse("test-simple.html", {"request": request})

@app.get("/test-debug-structure", response_class=HTMLResponse)
async def test_debug_structure(request: Request):
    """Test charts with debug page structure (no CSS grid)"""
    return templates.TemplateResponse("test-debug-structure.html", {"request": request})

@app.get("/test-exact-debug", response_class=HTMLResponse)
async def test_exact_debug(request: Request):
    """Test charts with exact debug page structure"""
    return templates.TemplateResponse("test-exact-debug.html", {"request": request})

@app.get("/test-tabbed", response_class=HTMLResponse)
async def test_tabbed(request: Request):
    """Test tabbed charts - one chart at a time"""
    return templates.TemplateResponse("test-tabbed.html", {"request": request})

@app.get("/test-single-chart", response_class=HTMLResponse)
async def test_single_chart(request: Request):
    """Test single chart with dropdown selector"""
    return templates.TemplateResponse("test-single-chart.html", {"request": request})

@app.get("/debug-real-data", response_class=HTMLResponse)
async def debug_real_data(request: Request):
    """Debug page with real data - byte-for-byte identical to working debug page"""
    return templates.TemplateResponse("debug-real-data.html", {"request": request})

@app.get("/new", response_class=HTMLResponse)
async def new_dashboard(request: Request):
    """New dashboard - completely fresh start based on working debug page"""
    m = _latest_metrics()
    if not m:
        return templates.TemplateResponse(
            "index-new.html",
            {"request": request, "summary": None, "pools": [], "total_fees_24h": 0, "no_data": True},
        )

    pools = _pools_for_ts(m["ts_utc"]) if m else []
    total_fees_24h = _total_fees_24h(m["ts_utc"]) if m else 0.0
    
    return templates.TemplateResponse(
        "index-new.html",
        {
            "request": request, 
            "summary": m, 
            "pools": pools, 
            "total_fees_24h": total_fees_24h,
            "daily_yield": m['real_yield_daily'] if m and 'real_yield_daily' in m else 0,
            "apy_simple": m['apy_simple'] if m and 'apy_compound' in m else 0,
            "apy_compound": m['apy_compound'] if m and 'apy_compound' in m else 0,
            "no_data": False
        },
    )

@app.get("/minimal", response_class=HTMLResponse)
async def minimal_test(request: Request):
    """Minimal test page - absolutely nothing but a single chart"""
    return templates.TemplateResponse("minimal-test.html", {"request": request})

@app.get("/minimal-api", response_class=HTMLResponse)
async def minimal_api_test(request: Request):
    """Minimal test page with real API data"""
    return templates.TemplateResponse("minimal-api-test.html", {"request": request})

@app.get("/minimal-dropdown", response_class=HTMLResponse)
async def minimal_dropdown_test(request: Request):
    """Minimal test page with dropdown selector"""
    return templates.TemplateResponse("minimal-dropdown-test.html", {"request": request})

@app.get("/minimal-content", response_class=HTMLResponse)
async def minimal_content_test(request: Request):
    """Minimal test page with metrics content"""
    return templates.TemplateResponse("minimal-content-test.html", {"request": request})

@app.get("/minimal-table", response_class=HTMLResponse)
async def minimal_table_test(request: Request):
    """Minimal test page with pools table"""
    return templates.TemplateResponse("minimal-table-test.html", {"request": request})

@app.get("/minimal-jinja", response_class=HTMLResponse)
async def minimal_jinja_test(request: Request):
    """Minimal test page with Jinja2 template rendering"""
    m = _latest_metrics()
    if not m:
        return templates.TemplateResponse(
            "minimal-jinja-test.html",
            {"request": request, "summary": None, "total_fees_24h": 0, "daily_yield": 0, "apy_simple": 0, "no_data": True},
        )

    total_fees_24h = _total_fees_24h(m["ts_utc"]) if m else 0.0
    
    return templates.TemplateResponse(
        "minimal-jinja-test.html",
        {
            "request": request, 
            "summary": m, 
            "total_fees_24h": total_fees_24h,
            "daily_yield": m['real_yield_daily'] if m and 'real_yield_daily' in m else 0,
            "apy_simple": m['apy_simple'] if m and 'apy_simple' in m else 0,
            "no_data": False
        },
    )

@app.get("/minimal-exact-structure", response_class=HTMLResponse)
async def minimal_exact_structure_test(request: Request):
    """Minimal test page with exact same structure as main page"""
    return templates.TemplateResponse("minimal-exact-structure-test.html", {"request": request})

@app.get("/minimal-with-pools-table", response_class=HTMLResponse)
async def minimal_with_pools_table_test(request: Request):
    """Minimal test page with pools table after chart"""
    return templates.TemplateResponse("minimal-with-pools-table-test.html", {"request": request})

@app.get("/working-copy", response_class=HTMLResponse)
async def working_copy_test(request: Request):
    """Copy of working minimal page to test if route affects it"""
    return templates.TemplateResponse("minimal-with-pools-table-test.html", {"request": request})

@app.get("/history", response_class=HTMLResponse)
async def history(request: Request):
	daily = _history_summaries()
	pool_apy = _history_pool_apy()
	return templates.TemplateResponse(
		"history.html",
		{"request": request, "daily": daily, "pool_apy": pool_apy},
	)

@app.get("/api/auto-refresh-status")
async def auto_refresh_status():
	"""Get the status of the auto-refresh system"""
	return get_auto_refresh_status()

@app.post("/api/trigger-snapshot")
async def trigger_snapshot():
	"""Manually trigger a snapshot"""
	try:
		from core.snapshot import snapshot_once
		result = snapshot_once()
		return {
			"success": True,
			"timestamp": result.get("ts_utc"),
			"message": "Snapshot completed successfully"
		}
	except Exception as e:
		return {
			"success": False,
			"error": str(e),
			"message": "Snapshot failed"
		}

