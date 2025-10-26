#!/usr/bin/env python3
"""
Script to retrospectively fix zero values in the database by replacing them
with the last known non-zero value.
"""
import sqlite3
import os
import logging
from typing import List, Tuple

logging.basicConfig(level=logging.INFO)

DB_PATH = os.getenv("ASSET_DB_PATH", "asset_reserve_metrics.sqlite")

# Columns that should never be 0 (those that show in charts)
METRICS_COLUMNS = [
    "price_usd",
    "fdv_usd", 
    "market_cap_usd",
    "circulating_supply",
    "real_tvl_total_usd",
    "volume_24h_usd"
]


def connect() -> sqlite3.Connection:
    """Connect to the database."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def get_all_timestamps(conn: sqlite3.Connection) -> List[str]:
    """Get all timestamps from metrics_snapshots ordered by time."""
    cur = conn.cursor()
    cur.execute("SELECT ts_utc FROM metrics_snapshots ORDER BY ts_utc ASC")
    return [row[0] for row in cur.fetchall()]


def get_last_non_zero_before(conn: sqlite3.Connection, column: str, before_ts: str) -> float:
    """Get the last non-zero value for a column before a given timestamp."""
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT {column}
        FROM metrics_snapshots
        WHERE {column} IS NOT NULL 
          AND {column} > 0 
          AND ts_utc < ?
        ORDER BY ts_utc DESC
        LIMIT 1
        """,
        (before_ts,)
    )
    row = cur.fetchone()
    return float(row[0]) if row and row[0] else 0.0


def fix_zero_values():
    """Fix all zero values in the database."""
    conn = connect()
    try:
        timestamps = get_all_timestamps(conn)
        logging.info(f"Found {len(timestamps)} snapshots to process")
        
        fixes_made = 0
        
        for ts in timestamps:
            cur = conn.cursor()
            
            # Get current values
            cur.execute(
                f"""
                SELECT {', '.join(METRICS_COLUMNS)}
                FROM metrics_snapshots
                WHERE ts_utc = ?
                """,
                (ts,)
            )
            row = cur.fetchone()
            
            if not row:
                continue
            
            # Check each column for zero values
            updates = {}
            for i, column in enumerate(METRICS_COLUMNS):
                current_value = row[i]
                
                if current_value is None or current_value <= 0:
                    # Get last known good value
                    last_good = get_last_non_zero_before(conn, column, ts)
                    
                    if last_good > 0:
                        updates[column] = last_good
                        logging.info(
                            f"Fixing {column} at {ts}: {current_value} -> {last_good}"
                        )
                        fixes_made += 1
            
            # Apply updates if any
            if updates:
                set_clause = ", ".join(f"{col} = ?" for col in updates.keys())
                values = list(updates.values()) + [ts]
                
                cur.execute(
                    f"""
                    UPDATE metrics_snapshots
                    SET {set_clause}
                    WHERE ts_utc = ?
                    """,
                    values
                )
        
        conn.commit()
        logging.info(f"✅ Fixed {fixes_made} zero values in the database")
        
        # Show summary statistics
        cur = conn.cursor()
        for column in METRICS_COLUMNS:
            cur.execute(
                f"""
                SELECT COUNT(*) 
                FROM metrics_snapshots 
                WHERE {column} IS NULL OR {column} <= 0
                """
            )
            remaining_zeros = cur.fetchone()[0]
            if remaining_zeros > 0:
                logging.warning(
                    f"⚠️  {column} still has {remaining_zeros} zero/null values "
                    "(likely no previous non-zero value exists)"
                )
        
    finally:
        conn.close()


if __name__ == "__main__":
    logging.info("Starting database cleanup...")
    fix_zero_values()
    logging.info("Database cleanup complete!")

