import sys
from core.snapshot import snapshot_once

if __name__ == "__main__":
	try:
		print("Starting snapshot...")
		res = snapshot_once()
		print("Snapshot completed successfully!")
		print({
			"ts": res.get("ts_utc"),
			"fees24h_total_usd_est": round(res.get("fees24h_total_usd_est", 0.0), 4),
			"real_yield_daily": round(res.get("real_yield_daily", 0.0), 6),
			"apy_simple": round(res.get("apy_simple", 0.0), 6),
			"apy_compound": round(res.get("apy_compound", 0.0), 6),
		})
	except Exception as e:
		print(f"Snapshot failed: {e}")
		sys.exit(1)
