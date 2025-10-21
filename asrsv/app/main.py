import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.db import migrate, q

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


def _latest_metrics():
	rows = q("SELECT * FROM metrics_snapshots ORDER BY ts_utc DESC LIMIT 1")
	return rows[0] if rows else None


def _pools_for_ts(ts_utc: str):
	return q(
		"""
		SELECT family, source, quote_symbol, real_tvl_usd, volume_24h_usd,
		       fee_24h_usd, daily_yield, apy_simple
		FROM pool_snapshots
		WHERE ts_utc = ?
		ORDER BY apy_simple DESC
		""",
		(ts_utc,),
	)


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
	m = _latest_metrics()
	if not m:
		return templates.TemplateResponse(
			"index.html",
			{"request": request, "summary": None, "pools": [], "no_data": True},
		)

	pools = _pools_for_ts(m["ts_utc"]) if m else []
	return templates.TemplateResponse(
		"index.html",
		{"request": request, "summary": m, "pools": pools, "no_data": False},
	)


@app.get("/history", response_class=HTMLResponse)
async def history(request: Request):
	daily = _history_summaries()
	pool_apy = _history_pool_apy()
	return templates.TemplateResponse(
		"history.html",
		{"request": request, "daily": daily, "pool_apy": pool_apy},
	)

