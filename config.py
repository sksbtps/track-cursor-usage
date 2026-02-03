"""Configuration for Cursor Usage Menu Bar App"""

import os

# Polling settings
POLL_INTERVAL_MINUTES = 15  # Default, can be changed in app
WORK_HOURS_START = 9   # 9 AM
WORK_HOURS_END = 17    # 5 PM

# URLs
CURSOR_DASHBOARD_URL = "https://cursor.com/en-US/dashboard?tab=usage"

# Browser data directory (for persistent login)
BROWSER_DATA_DIR = os.path.expanduser("~/.cursor-usage-app/browser-data")

# Alert settings
ALERT_ON_MAX_MODE = True        # Show macOS notification for Max mode
ALERT_ON_THINKING_MODE = False  # Don't notify for thinking (just show in menu)
