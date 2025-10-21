import os, math, time, json, datetime, tempfile, logging
from typing import Any, Dict, List, Tuple
import sqlite3

from app.db import migrate, _connect

# ENV / Config
BIRDEYE_API_KEY = os.getenv("BIRDEYE_API_KEY", "")
HELIUS_API_KEY  = os.getenv("HELIUS_API_KEY",  "")
ASSET_MINT      = os.getenv("ASSET_MINT", "assetSHnT4AzwSGDx6wqv7CWacqjg1LEXnbir3FnSSa")
RESERVE_WALLETS = os.getenv("RESERVE_WALLETS", "").split(",") if os.getenv("RESERVE_WALLETS") else []

BIRDEYE_BASE = "https://public-api.birdeye.so"
HELIUS_RPC   = "https://mainnet.helius-rpc.com"

DEFAULT_FEE_RATE = 0.01
USDC_FEE_RATE    = 0.0025

PROTOCOL_CUT_METEORA = 0.20

import requests

logging.basicConfig(level=logging.INFO)


def _be_headers() -> Dict[str, str]:
	if not BIRDEYE_API_KEY:
		raise RuntimeError("Missing BIRDEYE_API_KEY")
	return {"X-API-KEY": BIRDEYE_API_KEY, "x-chain": "solana", "accept": "application/json"}


def http_json(method: str, url: str, headers: Dict[str, str] = None,
             params: Dict[str, Any] = None, json_body: Any = None,
             retries: int = 3, backoff: float = 0.9) -> Any:
	for attempt in range(1, retries + 1):
		r = requests.request(method, url, headers=headers, params=params, json=json_body, timeout=25)
		if r.status_code == 429 and attempt < retries:
			time.sleep(backoff * attempt)
			continue
		r.raise_for_status()
		try:
			return r.json()
		except Exception:
			return r.text


def be_markets_v2(token_addr: str, *, sort_by="liquidity", limit=50, time_frame="24h") -> List[Dict[str, Any]]:
	url = f"{BIRDEYE_BASE}/defi/v2/markets"
	items: List[Dict[str, Any]] = []
	offset = 0
	while len(items) < limit:
		params = {
			"address": token_addr,
			"time_frame": time_frame,
			"sort_type": "desc",
			"sort_by": sort_by,
			"offset": offset,
			"limit": min(20, limit - len(items)),
		}
		j = http_json("GET", url, headers=_be_headers(), params=params)
		page = (j or {}).get("data", {}).get("items", []) or []
		items.extend(page)
		if not page:
			break
		offset += len(page)
	return items


def be_price(token_addr: str) -> float:
	j = http_json("GET", f"{BIRDEYE_BASE}/defi/price", headers=_be_headers(), params={"address": token_addr, "include_liquidity": "true"})
	data = j.get("data", j) or {}
	try:
		return float(data.get("value") or 0.0)
	except Exception:
		return 0.0


def helius_rpc(method: str, params: Any) -> Any:
	url = f"{HELIUS_RPC}/?api-key={HELIUS_API_KEY}"
	body = {"jsonrpc": "2.0", "id": method, "method": method, "params": params}
	return http_json("POST", url, headers={"accept": "application/json", "content-type": "application/json"}, json_body=body)


def helius_get_token_supply(mint: str) -> float:
	try:
		j = helius_rpc("getTokenSupply", [mint])
		val = j["result"]["value"]
		if val.get("uiAmount") is not None:
			return float(val["uiAmount"])
		return float(val["amount"]) / (10 ** int(val["decimals"]))
	except Exception:
		return 0.0


def helius_get_owner_token_balance(owner: str, mint: str) -> float:
	try:
		j = helius_rpc("getTokenAccountsByOwner", [owner, {"mint": mint}, {"encoding": "jsonParsed"}])
		total = 0.0
		for acc in j.get("result", {}).get("value", []):
			info = acc.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
			amt  = info.get("tokenAmount", {})
			if amt.get("uiAmount") is not None:
				total += float(amt["uiAmount"])
			else:
				total += float(amt.get("amount", 0)) / (10 ** int(amt.get("decimals", 0)))
		return total
	except Exception:
		return 0.0


def helius_get_reserve_total(mint: str, reserve_wallets: List[str]) -> float:
	s = 0.0
	for w in reserve_wallets:
		w = (w or "").strip()
		if not w:
			continue
		s += helius_get_owner_token_balance(w, mint)
	return s


def fee_rate_for_pair(family: str, quote_symbol: str) -> float:
	qs = (quote_symbol or "").upper()
	fam = (family or "").lower()
	if qs == "USDC" or "usdc" in fam:
		return USDC_FEE_RATE
	return DEFAULT_FEE_RATE


class SnapshotLock:
	def __init__(self, name: str = "asset_reserve_snapshot.lock") -> None:
		self.path = os.path.join(tempfile.gettempdir(), name)
		self.fd = None

	def acquire(self) -> bool:
		try:
			self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
			os.write(self.fd, f"pid={os.getpid()} time={int(time.time())}\n".encode("utf-8"))
			return True
		except FileExistsError:
			return False
		except Exception:
			return False

	def release(self) -> None:
		try:
			if self.fd is not None:
				os.close(self.fd)
			self.fd = None
			if os.path.exists(self.path):
				os.unlink(self.path)
		except Exception:
			pass

	def __enter__(self):
		if not self.acquire():
			raise RuntimeError("snapshot already running")
		return self

	def __exit__(self, exc_type, exc, tb):
		self.release()


def snapshot_once() -> Dict[str, Any]:
	"""Run a single snapshot, persist into DB, and return the computed summary dict."""
	migrate()

	price = be_price(ASSET_MINT)
	total_supply = helius_get_token_supply(ASSET_MINT)
	reserve_total = helius_get_reserve_total(ASSET_MINT, RESERVE_WALLETS)
	circulating = max(total_supply - reserve_total, 0.0)
	fdv = price * total_supply
	mc  = price * circulating

	items = be_markets_v2(ASSET_MINT, sort_by="liquidity", limit=50, time_frame="24h")
	rows: List[Dict[str, Any]] = []

	total_real_tvl = 0.0
	total_vol_24h  = 0.0
	total_fees_24h = 0.0

	for it in items:
		pool_addr = it.get("address")
		base_sym  = (it.get("base")  or {}).get("symbol", "") or ""
		quote_sym = (it.get("quote") or {}).get("symbol", "") or ""
		liq_usd   = float(it.get("liquidity") or 0.0)
		vol_24h   = float(it.get("volume24h") or 0.0)
		family    = it.get("name") or ""
		source    = it.get("source") or ""

		real_tvl_usd = liq_usd / 2.0
		fee_rate = fee_rate_for_pair(family, quote_sym)
		protocol_cut = PROTOCOL_CUT_METEORA if "meteora" in (source or "").lower() else 0.0

		gross_fees_24h     = vol_24h * fee_rate
		protocol_fees_24h  = gross_fees_24h * protocol_cut
		net_fees_24h       = gross_fees_24h - protocol_fees_24h

		daily_yield = (net_fees_24h / real_tvl_usd) if real_tvl_usd > 0 else 0.0
		apy_simple  = daily_yield * 365.0
		apy_comp    = (math.pow(1.0 + daily_yield, 365.0) - 1.0) if daily_yield > 0 else 0.0

		rows.append({
			"pool_address": pool_addr,
			"family": family,
			"source": "Meteora" if "meteora" in (source or "").lower() else (source or "Unknown"),
			"base_symbol": base_sym,
			"quote_symbol": (quote_sym or "UNKNOWN").strip(),
			"liquidity_usd": liq_usd,
			"real_tvl_usd": real_tvl_usd,
			"volume_24h_usd": vol_24h,
			"fee_rate": fee_rate,
			"protocol_cut": protocol_cut,
			"gross_fee_24h_usd": gross_fees_24h,
			"protocol_fee_24h_usd": protocol_fees_24h,
			"fee_24h_usd": net_fees_24h,
			"daily_yield": daily_yield,
			"apy_simple": apy_simple,
			"apy_compound": apy_comp,
		})

		total_real_tvl += real_tvl_usd
		total_vol_24h  += vol_24h
		total_fees_24h += net_fees_24h

	ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
	conn = _connect()
	try:
		cur = conn.cursor()

		# write pool rows and update pools_state + family_totals
		for r in rows:
			cur.execute(
				"""
				INSERT INTO pool_snapshots
				(ts_utc, pool_address, family, base_symbol, quote_symbol,
				 liquidity_usd, real_tvl_usd, volume_24h_usd, fee_rate, protocol_cut, source,
				 gross_fee_24h_usd, protocol_fee_24h_usd, fee_24h_usd, daily_yield, apy_simple, apy_compound)
				VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
				""",
				(
					ts, r["pool_address"], r["family"], r["base_symbol"], r["quote_symbol"],
					r["liquidity_usd"], r["real_tvl_usd"], r["volume_24h_usd"], r["fee_rate"], r["protocol_cut"], r["source"],
					r["gross_fee_24h_usd"], r["protocol_fee_24h_usd"], r["fee_24h_usd"], r["daily_yield"], r["apy_simple"], r["apy_compound"],
				)
			)

			# delta accumulation using pools_state
			cur.execute("SELECT last_volume_24h_usd FROM pools_state WHERE pool_address = ?", (r["pool_address"],))
			prev = cur.fetchone()
			last = float(prev[0]) if prev and prev[0] is not None else 0.0
			curr = float(r["volume_24h_usd"])
			# If API resets (curr < last), treat delta as curr (not negative)
			delta_vol = curr - last if curr >= last else curr
			if delta_vol < 0:
				delta_vol = 0.0
			gross_delta = delta_vol * r["fee_rate"]
			net_delta   = gross_delta * (1.0 - r["protocol_cut"])

			cur.execute(
				"""
				INSERT INTO family_totals (family, all_time_volume_usd, all_time_fees_usd)
				VALUES (?, ?, ?)
				ON CONFLICT(family) DO UPDATE SET
				  all_time_volume_usd = COALESCE(all_time_volume_usd,0) + excluded.all_time_volume_usd,
				  all_time_fees_usd   = COALESCE(all_time_fees_usd,0) + excluded.all_time_fees_usd
				""",
				(r["family"], float(delta_vol or 0.0), float(net_delta or 0.0)),
			)

			cur.execute(
				"""
				INSERT INTO pools_state (pool_address, last_volume_24h_usd)
				VALUES (?, ?)
				ON CONFLICT(pool_address) DO UPDATE SET last_volume_24h_usd = excluded.last_volume_24h_usd
				""",
				(r["pool_address"], r["volume_24h_usd"]),
			)

		# write metrics snapshot with APY fields
		portfolio_daily_yield = (total_fees_24h / total_real_tvl) if total_real_tvl > 0 else 0.0
		portfolio_apy_simple  = portfolio_daily_yield * 365.0
		portfolio_apy_comp    = (math.pow(1.0 + portfolio_daily_yield, 365.0) - 1.0) if portfolio_daily_yield > 0 else 0.0

		cur.execute(
			"""
			INSERT OR REPLACE INTO metrics_snapshots
			(ts_utc, price_usd, fdv_usd, market_cap_usd, circulating_supply,
			 real_tvl_total_usd, volume_24h_usd, collateralization_ratio,
			 real_yield_daily, apy_simple, apy_compound)
			VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
			""",
			(
				ts, price, fdv, mc, circulating,
				total_real_tvl, total_vol_24h,
				(total_real_tvl / fdv) if fdv > 0 else 0.0,
				portfolio_daily_yield, portfolio_apy_simple, portfolio_apy_comp,
			),
		)

		conn.commit()

		# Post-commit validations
		row_sum = cur.execute("SELECT COALESCE(SUM(fee_24h_usd),0) FROM pool_snapshots WHERE ts_utc = ?", (ts,)).fetchone()
		db_sum_fees = float(row_sum[0] if row_sum and row_sum[0] is not None else 0.0)
		if abs(db_sum_fees - total_fees_24h) > 1e-6:
			logging.warning("fees24h_total_usd_est mismatch: computed=%s db_sum=%s ts=%s", total_fees_24h, db_sum_fees, ts)

		row_ms = cur.execute("SELECT real_yield_daily, apy_simple FROM metrics_snapshots WHERE ts_utc = ?", (ts,)).fetchone()
		if row_ms:
			db_daily = float(row_ms[0] or 0.0)
			db_apy_s = float(row_ms[1] or 0.0)
			if abs(db_apy_s - (db_daily * 365.0)) > 1e-6:
				logging.warning("APY simple mismatch: apy_simple=%s daily*365=%s ts=%s", db_apy_s, db_daily * 365.0, ts)

	finally:
		conn.close()

	return {
		"ts_utc": ts,
		"price_usd": price,
		"fdv_usd": fdv,
		"market_cap_usd": mc,
		"circulating_supply": circulating,
		"real_tvl_total_usd": total_real_tvl,
		"volume_24h_usd": total_vol_24h,
		"fees24h_total_usd_est": total_fees_24h,
		"real_yield_daily": portfolio_daily_yield,
		"apy_simple": portfolio_apy_simple,
		"apy_compound": portfolio_apy_comp,
		"per_pool": rows,
	}
