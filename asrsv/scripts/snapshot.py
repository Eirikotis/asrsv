import sys
from core.snapshot import snapshot_once, SnapshotLock

if __name__ == "__main__":
	try:
		with SnapshotLock():
			res = snapshot_once()
			print({
				"ts": res.get("ts_utc"),
				"fees24h_total_usd_est": round(res.get("fees24h_total_usd_est", 0.0), 4),
				"real_yield_daily": round(res.get("real_yield_daily", 0.0), 6),
				"apy_simple": round(res.get("apy_simple", 0.0), 6),
				"apy_compound": round(res.get("apy_compound", 0.0), 6),
			})
	except RuntimeError:
		# Another snapshot is running; exit cleanly
		sys.exit(0)
