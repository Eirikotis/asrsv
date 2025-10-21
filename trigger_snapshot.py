#!/usr/bin/env python3
"""
Simple script to manually trigger a snapshot
"""
import requests
import json

def trigger_snapshot():
    """Trigger a snapshot via the API"""
    try:
        response = requests.post("http://127.0.0.1:8000/api/trigger-snapshot")
        result = response.json()
        
        if result.get("success"):
            print("✅ Snapshot triggered successfully!")
            print(f"📅 Timestamp: {result.get('timestamp')}")
        else:
            print("❌ Snapshot failed!")
            print(f"Error: {result.get('error')}")
            
    except Exception as e:
        print(f"❌ Failed to trigger snapshot: {e}")

def check_status():
    """Check auto-refresh status"""
    try:
        response = requests.get("http://127.0.0.1:8000/api/auto-refresh-status")
        status = response.json()
        
        print("🔄 Auto-refresh Status:")
        print(f"  Running: {status.get('is_running')}")
        print(f"  Interval: {status.get('refresh_interval_minutes')} minutes")
        print(f"  Last refresh: {status.get('last_refresh')}")
        print(f"  Next refresh in: {status.get('next_refresh_in_seconds')} seconds")
        
    except Exception as e:
        print(f"❌ Failed to check status: {e}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        check_status()
    else:
        trigger_snapshot()
