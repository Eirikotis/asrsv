"""
Auto-refresh mechanism for VPS deployment
This module provides automatic data refresh without requiring server restarts
"""
import asyncio
import threading
import time
import logging
from datetime import datetime, timedelta
from typing import Optional
import sqlite3
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AutoRefreshManager:
    """Manages automatic data refresh for the dashboard"""
    
    def __init__(self, refresh_interval_minutes: int = 15):
        self.refresh_interval = refresh_interval_minutes * 60  # Convert to seconds
        self.is_running = False
        self.thread: Optional[threading.Thread] = None
        self.last_refresh: Optional[datetime] = None
        
    def start(self):
        """Start the auto-refresh background thread"""
        if self.is_running:
            logger.warning("Auto-refresh is already running")
            return
            
        self.is_running = True
        self.thread = threading.Thread(target=self._refresh_loop, daemon=True)
        self.thread.start()
        logger.info(f"Auto-refresh started (interval: {self.refresh_interval // 60} minutes)")
        
    def stop(self):
        """Stop the auto-refresh background thread"""
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("Auto-refresh stopped")
        
    def _refresh_loop(self):
        """Main refresh loop running in background thread"""
        while self.is_running:
            try:
                self._run_snapshot()
                self.last_refresh = datetime.now()
                logger.info(f"Auto-refresh completed at {self.last_refresh}")
            except Exception as e:
                logger.error(f"Auto-refresh failed: {e}")
                
            # Wait for next refresh
            time.sleep(self.refresh_interval)
            
    def _run_snapshot(self):
        """Run a snapshot and update the database"""
        try:
            # Import here to avoid circular imports
            from core.snapshot import snapshot_once
            
            logger.info("Running automatic snapshot...")
            result = snapshot_once()
            
            if result and result.get('ts_utc'):
                logger.info(f"Snapshot completed: {result['ts_utc']}")
            else:
                logger.warning("Snapshot completed but no timestamp returned")
                
        except Exception as e:
            logger.error(f"Snapshot failed: {e}")
            raise
            
    def get_status(self) -> dict:
        """Get the current status of auto-refresh"""
        return {
            "is_running": self.is_running,
            "refresh_interval_minutes": self.refresh_interval // 60,
            "last_refresh": self.last_refresh.isoformat() if self.last_refresh else None,
            "next_refresh_in_seconds": self._get_next_refresh_seconds()
        }
        
    def _get_next_refresh_seconds(self) -> Optional[int]:
        """Calculate seconds until next refresh"""
        if not self.last_refresh:
            return None
            
        next_refresh = self.last_refresh + timedelta(seconds=self.refresh_interval)
        now = datetime.now()
        
        if next_refresh > now:
            return int((next_refresh - now).total_seconds())
        else:
            return 0

# Global instance
auto_refresh_manager = AutoRefreshManager()

def start_auto_refresh(interval_minutes: int = 15):
    """Start auto-refresh with specified interval"""
    auto_refresh_manager.refresh_interval = interval_minutes * 60
    auto_refresh_manager.start()

def stop_auto_refresh():
    """Stop auto-refresh"""
    auto_refresh_manager.stop()

def get_auto_refresh_status() -> dict:
    """Get auto-refresh status"""
    return auto_refresh_manager.get_status()
