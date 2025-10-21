import os
import sqlite3
from sqlite3 import Row
from typing import Any, Iterable, List, Optional, Sequence, Tuple

DB_PATH = os.getenv("ASSET_DB_PATH", "asset_reserve_metrics.sqlite")


def _connect() -> sqlite3.Connection:
	conn = sqlite3.connect(DB_PATH, timeout=30, isolation_level=None)
	conn.row_factory = Row
	cur = conn.cursor()
	cur.execute("PRAGMA journal_mode=WAL;")
	cur.execute("PRAGMA synchronous=NORMAL;")
	cur.execute("PRAGMA busy_timeout=5000;")
	return conn


def q(sql: str, params: Sequence[Any] = ()) -> List[Row]:
	conn = _connect()
	try:
		cur = conn.execute(sql, params)
		rows = cur.fetchall()
		return rows
	finally:
		conn.close()


def _col_exists(cur: sqlite3.Cursor, table: str, col: str) -> bool:
	cur.execute(f"PRAGMA table_info({table});")
	return any(r[1] == col for r in cur.fetchall())


def migrate() -> None:
	"""Create tables if missing and add required columns/views idempotently."""
	conn = _connect()
	try:
		cur = conn.cursor()

		# Base summary snapshots
		cur.execute(
			"""
			CREATE TABLE IF NOT EXISTS metrics_snapshots (
			  ts_utc TEXT PRIMARY KEY,
			  price_usd REAL,
			  fdv_usd REAL,
			  market_cap_usd REAL,
			  circulating_supply REAL,
			  real_tvl_total_usd REAL,
			  volume_24h_usd REAL,
			  collateralization_ratio REAL
			);
			"""
		)
		# Add APY fields to metrics_snapshots
		if not _col_exists(cur, "metrics_snapshots", "real_yield_daily"):
			cur.execute("ALTER TABLE metrics_snapshots ADD COLUMN real_yield_daily REAL;")
		if not _col_exists(cur, "metrics_snapshots", "apy_simple"):
			cur.execute("ALTER TABLE metrics_snapshots ADD COLUMN apy_simple REAL;")
		if not _col_exists(cur, "metrics_snapshots", "apy_compound"):
			cur.execute("ALTER TABLE metrics_snapshots ADD COLUMN apy_compound REAL;")

		# Per-pool snapshots
		cur.execute(
			"""
			CREATE TABLE IF NOT EXISTS pool_snapshots (
			  ts_utc TEXT,
			  pool_address TEXT,
			  family TEXT,
			  base_symbol TEXT,
			  quote_symbol TEXT,
			  liquidity_usd REAL,
			  real_tvl_usd REAL,
			  volume_24h_usd REAL,
			  fee_rate REAL,
			  protocol_cut REAL,
			  PRIMARY KEY (ts_utc, pool_address)
			);
			"""
		)
		# Add new columns on pool_snapshots
		for col, decl in [
			("daily_yield", "REAL"),
			("apy_simple", "REAL"),
			("apy_compound", "REAL"),
			("gross_fee_24h_usd", "REAL"),
			("protocol_fee_24h_usd", "REAL"),
			("fee_24h_usd", "REAL"),
			("source", "TEXT"),
			("interval_fee_usd", "REAL"),  # 30m incremental fees
			("all_time_fees_usd", "REAL"),  # Cumulative fees
		]:
			if not _col_exists(cur, "pool_snapshots", col):
				cur.execute(f"ALTER TABLE pool_snapshots ADD COLUMN {col} {decl};")

		# Pools state for 24h pointer
		cur.execute(
			"""
			CREATE TABLE IF NOT EXISTS pools_state (
			  pool_address TEXT PRIMARY KEY,
			  last_volume_24h_usd REAL
			);
			"""
		)

		# Families all-time counters
		cur.execute(
			"""
			CREATE TABLE IF NOT EXISTS family_totals (
			  family TEXT PRIMARY KEY,
			  all_time_volume_usd REAL,
			  all_time_fees_usd REAL
			);
			"""
		)

		# View: daily APY rollup
		cur.execute(
			"""
			CREATE VIEW IF NOT EXISTS v_pool_apy_daily AS
			SELECT date(substr(ts_utc,1,19)) AS day,
			       pool_address,
			       family,
			       AVG(daily_yield)   AS daily_yield_avg,
			       AVG(apy_simple)    AS apy_simple_avg,
			       AVG(apy_compound)  AS apy_compound_avg
			FROM pool_snapshots
			GROUP BY day, pool_address, family;
			"""
		)

		# Indexes
		cur.execute("CREATE INDEX IF NOT EXISTS idx_metrics_ts ON metrics_snapshots(ts_utc);")
		cur.execute("CREATE INDEX IF NOT EXISTS idx_pool_ts_addr_family ON pool_snapshots(ts_utc, pool_address, family);")

		conn.commit()
	finally:
		conn.close()
