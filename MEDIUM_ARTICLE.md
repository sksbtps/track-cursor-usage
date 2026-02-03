# Building a macOS Menu Bar App to Track Cursor AI Usage

*A complete guide to creating a real-time usage tracker for Cursor AI using Python, rumps, and Playwright*

---

## Introduction

If you're a heavy Cursor AI user like me, you've probably found yourself constantly checking the dashboard to see how many requests you have left. Wouldn't it be nice to have that information right in your menu bar?

In this tutorial, I'll show you how to build a macOS menu bar application that:
- Displays your remaining Cursor AI requests in real-time
- Shows detailed usage statistics in a dropdown menu
- Automatically detects when you're using "thinking" or "max" modes
- Polls the Cursor dashboard during work hours
- Runs automatically on login

By the end of this guide, you'll have a fully functional menu bar app and learn about macOS app development, web scraping, and thread-safe programming in Python.

## What We're Building

Here's what the final app looks like:

**Menu Bar:** `C 482` (showing 482 requests remaining)

**Dropdown Menu:**
```
● Updated at 10:36
──────────────────
── Usage ──
  📊 Included: 18/500 (3.6%)
  💵 On-Demand: $0.00 / $10.00
──────────────────
── Last Request ──
  🤖 claude-4.5-opus-high-thinking
  🕐 Feb 3, 2026, 10:31:29 AM
  ⚡ Thinking: Yes (2x requests)
  🔥 Max Mode: No
──────────────────
↻ Refresh Now
🔑 Login to Cursor
🌐 Open Dashboard
──────────────────
⚙️ Settings
Quit
```

## Prerequisites

- macOS 10.14 or later
- Python 3.8+
- Basic understanding of Python
- A Cursor AI account

## Architecture Overview

Before we dive into code, let's understand the architecture:

1. **Main Thread (rumps):** Handles the macOS menu bar UI. macOS requires all UI updates to happen on the main thread.

2. **Browser Thread (Playwright):** Runs web scraping operations. This can't block the UI thread.

3. **Thread-Safe State:** A shared state object with locks that both threads can safely access.

4. **Timer-Based UI Updates:** A timer polls the state every second and updates the UI on the main thread.

This architecture prevents the common "greenlet switching" errors you get when mixing Playwright with UI frameworks.

## Step 1: Project Setup

First, let's set up our project structure:

```bash
mkdir cursor-usage-tracker
cd cursor-usage-tracker
```

Create a `requirements.txt` file:

```txt
rumps>=0.4.0
playwright>=1.40.0
beautifulsoup4>=4.12.0
```

Install dependencies:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

## Step 2: Configuration Module

Create `config.py` to store all configuration:

```python
"""Configuration for Cursor Usage Menu Bar App"""

import os

# Polling settings
POLL_INTERVAL_MINUTES = 15  # Default, can be changed in-app
WORK_HOURS_START = 9   # 9 AM
WORK_HOURS_END = 17    # 5 PM

# URLs
CURSOR_DASHBOARD_URL = "https://cursor.com/en-US/dashboard?tab=usage"

# Browser data directory (for persistent login)
BROWSER_DATA_DIR = os.path.expanduser("~/.cursor-usage-app/browser-data")

# Alert settings
ALERT_ON_MAX_MODE = True        # Show macOS notification for Max mode
ALERT_ON_THINKING_MODE = False  # Don't notify for thinking (just show in menu)
```

## Step 3: Data Models

Create `scraper.py` and start with the data models:

```python
"""Scraper module to fetch Cursor usage data"""

import os
import re
import queue
import threading
from dataclasses import dataclass, field
from typing import Optional
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import config


@dataclass
class UsageData:
    """Data class for Cursor usage information"""
    # Included requests
    included_used: int = 0
    included_total: int = 500
    
    # On-demand usage
    ondemand_used: float = 0.0
    ondemand_limit: float = 10.0
    
    # Last usage info
    last_model: Optional[str] = None
    last_timestamp: Optional[str] = None
    is_thinking_mode: bool = False
    is_max_mode: bool = False
    
    @property
    def included_percentage(self) -> float:
        if self.included_total == 0:
            return 0
        return (self.included_used / self.included_total) * 100
    
    @property
    def included_remaining(self) -> int:
        return self.included_total - self.included_used
    
    @property
    def display_model(self) -> str:
        """Get display name for the model"""
        if not self.last_model:
            return "Unknown"
        return self.last_model
```

## Step 4: Thread-Safe State Container

This is crucial for communication between threads:

```python
@dataclass
class ScraperState:
    """Thread-safe state container"""
    status: str = "idle"  # idle, fetching, logging_in, error
    error: Optional[str] = None
    logged_in: bool = False
    usage_data: Optional[UsageData] = None
    last_fetch_time: Optional[str] = None
    _lock: threading.Lock = field(default_factory=threading.Lock)
    
    def update(self, **kwargs):
        """Thread-safe update of state"""
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self, key) and not key.startswith('_'):
                    setattr(self, key, value)
    
    def get_snapshot(self) -> dict:
        """Get a thread-safe snapshot of the state"""
        with self._lock:
            return {
                "status": self.status,
                "error": self.error,
                "logged_in": self.logged_in,
                "usage_data": self.usage_data,
                "last_fetch_time": self.last_fetch_time,
            }
```

**Why this matters:** The `_lock` ensures that when one thread is reading/writing state, the other thread waits. This prevents race conditions.

## Step 5: The Scraper Class

Now let's build the scraper that runs in its own thread:

```python
class CursorScraper:
    """
    Scraper for Cursor dashboard.
    Uses a dedicated thread for all Playwright operations.
    """
    
    def __init__(self):
        self._task_queue = queue.Queue()
        self._browser_thread: Optional[threading.Thread] = None
        self._running = False
        self._playwright = None
        self._browser = None
        self._page = None
        self.state = ScraperState()
        self._ensure_data_dir()
    
    def _ensure_data_dir(self):
        """Ensure browser data directory exists"""
        os.makedirs(config.BROWSER_DATA_DIR, exist_ok=True)
    
    def start(self):
        """Start the browser thread"""
        if self._running:
            return
        
        self._running = True
        self._browser_thread = threading.Thread(target=self._browser_loop, daemon=True)
        self._browser_thread.start()
    
    def stop(self):
        """Stop the browser thread"""
        self._running = False
        self._task_queue.put("STOP")
        if self._browser_thread:
            self._browser_thread.join(timeout=5)
```

The scraper uses a **task queue** pattern. The main thread puts tasks (like "FETCH" or "LOGIN") into the queue, and the browser thread processes them one by one.

## Step 6: Browser Thread Loop

This is the heart of the scraper - the loop that runs in the browser thread:

```python
    def _browser_loop(self):
        """Main loop running in the browser thread"""
        try:
            self._playwright = sync_playwright().start()
        except Exception as e:
            self.state.update(status="error", error=f"Failed to start browser: {e}")
            return
        
        try:
            while self._running:
                try:
                    task = self._task_queue.get(timeout=1)
                except queue.Empty:
                    continue
                
                if task == "STOP":
                    break
                elif task == "LOGIN":
                    self._do_login()
                elif task == "FETCH":
                    self._do_fetch()
        
        finally:
            self._cleanup_browser()
            if self._playwright:
                try:
                    self._playwright.stop()
                except:
                    pass
    
    def _ensure_browser(self, headless: bool = True):
        """Ensure browser is started"""
        if self._browser is not None:
            return
        
        try:
            self._browser = self._playwright.chromium.launch_persistent_context(
                config.BROWSER_DATA_DIR,
                headless=headless,
                viewport={"width": 1280, "height": 800},
                args=["--disable-blink-features=AutomationControlled"]
            )
            if self._browser.pages:
                self._page = self._browser.pages[0]
            else:
                self._page = self._browser.new_page()
        except Exception as e:
            self.state.update(status="error", error=f"Browser launch failed: {e}")
            raise
    
    def _cleanup_browser(self):
        """Clean up browser"""
        if self._browser:
            try:
                self._browser.close()
            except:
                pass
            self._browser = None
            self._page = None
```

**Key insight:** Using `launch_persistent_context` with a data directory allows the browser to save cookies and stay logged in between runs.

## Step 7: Login Flow

Here's how we handle the login:

```python
    def _do_login(self):
        """Perform login - opens visible browser for user"""
        self.state.update(status="logging_in", error=None)
        
        try:
            # Close any existing browser
            self._cleanup_browser()
            
            # Open visible browser
            self._ensure_browser(headless=False)
            self._page.goto(config.CURSOR_DASHBOARD_URL, timeout=60000)
            
            # Wait for user to log in - poll for success
            max_wait = 300  # 5 minutes
            waited = 0
            
            while waited < max_wait and self._running:
                try:
                    # Check if we can see the usage section
                    usage_elem = self._page.query_selector("text=Included-Request Usage")
                    if usage_elem:
                        self.state.update(status="idle", logged_in=True, error=None)
                        # Close visible browser
                        self._cleanup_browser()
                        # Now fetch data
                        self._do_fetch()
                        return
                except:
                    pass
                
                self._page.wait_for_timeout(2000)
                waited += 2
            
            self.state.update(status="error", error="Login timeout - please try again")
            self._cleanup_browser()
        
        except Exception as e:
            self.state.update(status="error", error=f"Login failed: {str(e)[:50]}")
            self._cleanup_browser()
```

**How it works:**
1. Opens a visible browser window
2. Navigates to Cursor dashboard
3. Polls every 2 seconds looking for "Included-Request Usage" text
4. When found, knows user is logged in
5. Closes the visible browser and fetches data in headless mode

## Step 8: Fetching and Parsing Data

Now the most important part - scraping the dashboard:

```python
    def _do_fetch(self):
        """Fetch usage data"""
        self.state.update(status="fetching", error=None)
        
        try:
            self._ensure_browser(headless=True)
            
            # Navigate to dashboard
            self._page.goto(config.CURSOR_DASHBOARD_URL, 
                          wait_until="domcontentloaded", 
                          timeout=30000)
            
            # Wait for the page to load
            try:
                self._page.wait_for_selector("text=Included-Request Usage", timeout=10000)
            except:
                # Not logged in
                self.state.update(status="idle", logged_in=False, error="Please login")
                return
            
            # Additional wait for dynamic content
            self._page.wait_for_timeout(2000)
            
            # Parse the page
            html = self._page.content()
            data = self._parse_usage(html)
            
            from datetime import datetime
            now = datetime.now().strftime("%H:%M")
            
            self.state.update(
                status="idle",
                logged_in=True,
                usage_data=data,
                last_fetch_time=now,
                error=None
            )
        
        except Exception as e:
            error_msg = str(e)
            if "Timeout" in error_msg:
                error_msg = "Page load timeout"
            elif len(error_msg) > 50:
                error_msg = error_msg[:50] + "..."
            self.state.update(status="error", error=error_msg)
    
    def _parse_usage(self, html: str) -> UsageData:
        """Parse usage data from HTML"""
        soup = BeautifulSoup(html, 'html.parser')
        data = UsageData()
        
        # Find usage sections by looking for the specific text patterns
        all_text = soup.get_text()
        
        # Parse included usage - find pattern like "12 / 500"
        included_match = re.search(
            r'Included-Request Usage.*?(\d+)\s*/\s*(\d+)', 
            all_text, 
            re.DOTALL
        )
        if included_match:
            data.included_used = int(included_match.group(1))
            data.included_total = int(included_match.group(2))
        
        # Parse on-demand usage - find pattern like "$0 / $10"
        ondemand_match = re.search(
            r'On-Demand Usage.*?\$(\d+(?:\.\d+)?)\s*/\s*\$(\d+(?:\.\d+)?)', 
            all_text, 
            re.DOTALL
        )
        if ondemand_match:
            data.ondemand_used = float(ondemand_match.group(1))
            data.ondemand_limit = float(ondemand_match.group(2))
        
        # Find last usage row
        rows = soup.find_all('div', role='row', class_='dashboard-table-row')
        if rows:
            first_row = rows[0]
            cells = first_row.find_all('div', role='cell')
            
            if len(cells) >= 4:
                # Timestamp (first cell)
                timestamp_span = cells[0].find('span')
                if timestamp_span:
                    data.last_timestamp = timestamp_span.get('title') or \
                                        timestamp_span.get_text(strip=True)
                
                # Model name (4th cell)
                model_span = cells[3].find('span', title=True)
                if model_span:
                    data.last_model = model_span.get('title') or \
                                    model_span.get_text(strip=True)
                    if data.last_model and 'thinking' in data.last_model.lower():
                        data.is_thinking_mode = True
                
                # Check for Max mode badge anywhere in the row
                max_badge = first_row.find(string=re.compile(r'\bMax\b', re.I))
                if max_badge:
                    data.is_max_mode = True
        
        return data
    
    # Public API - queue tasks
    
    def request_fetch(self):
        """Request a fetch operation"""
        if self.state.status not in ("fetching", "logging_in"):
            self._task_queue.put("FETCH")
    
    def request_login(self):
        """Request a login operation"""
        if self.state.status != "logging_in":
            self._task_queue.put("LOGIN")
```

**Parsing strategy:** We use BeautifulSoup to parse the HTML and regex to extract the numbers. The Cursor dashboard has consistent class names and structure, making this reliable.

## Step 9: The Menu Bar App

Now let's build the UI with rumps. Create `app.py`:

```python
#!/usr/bin/env python3
"""
Cursor Usage Menu Bar App for macOS
"""

import rumps
import webbrowser
from typing import Optional
from AppKit import NSAttributedString, NSColor, NSFont

import config
from scraper import CursorScraper, UsageData

# Polling interval options (in minutes)
POLL_INTERVALS = [5, 10, 15, 30, 60]


def create_menu_item(text: str, callback=None) -> rumps.MenuItem:
    """Create a menu item with proper text styling for visibility"""
    item = rumps.MenuItem(text, callback=callback)
    
    # Get the underlying NSMenuItem and set attributed title
    # This ensures text is visible in both light and dark mode
    ns_item = item._menuitem
    
    # Use system label color (adapts to light/dark mode)
    color = NSColor.labelColor()
    font = NSFont.menuFontOfSize_(13)
    
    attrs = {
        'NSColor': color,
        'NSFont': font
    }
    
    attributed_string = NSAttributedString.alloc().initWithString_attributes_(text, attrs)
    ns_item.setAttributedTitle_(attributed_string)
    
    return item


class CursorUsageApp(rumps.App):
    """Menu bar application for Cursor usage tracking"""
    
    def __init__(self):
        super().__init__(
            name="Cursor Usage",
            title="C",
            quit_button=None
        )
        
        self.scraper = CursorScraper()
        self.poll_interval = config.POLL_INTERVAL_MINUTES
        self.last_alerted_max_mode = False
        self.seconds_since_fetch = 0
        
        # Build menu
        self._build_menu()
        
        # Start scraper thread
        self.scraper.start()
        
        # Timer to poll scraper state and update UI (runs on main thread)
        self.ui_timer = rumps.Timer(self._on_ui_timer, 1)
        self.ui_timer.start()
        
        # Request initial fetch after a short delay
        self.startup_timer = rumps.Timer(self._on_startup, 2)
        self.startup_timer.start()
```

**Key point:** The `NSAttributedString` approach ensures text is visible in dark mode. rumps by default uses gray text which can be hard to read.

## Step 10: Building the Menu

```python
    def _build_menu(self):
        """Build the menu items"""
        self.menu.clear()
        
        # Status
        self.menu_status = create_menu_item("● Starting...")
        self.menu.add(self.menu_status)
        
        self.menu.add(rumps.separator)
        
        # Usage header
        self.menu.add(create_menu_item("── Usage ──"))
        
        self.menu_included = create_menu_item("  📊 Included: --/--")
        self.menu.add(self.menu_included)
        
        self.menu_ondemand = create_menu_item("  💵 On-Demand: --/--")
        self.menu.add(self.menu_ondemand)
        
        self.menu.add(rumps.separator)
        
        # Last request header
        self.menu.add(create_menu_item("── Last Request ──"))
        
        self.menu_model = create_menu_item("  🤖 Model: --")
        self.menu.add(self.menu_model)
        
        self.menu_timestamp = create_menu_item("  🕐 Time: --")
        self.menu.add(self.menu_timestamp)
        
        self.menu_thinking = create_menu_item("  ⚡ Thinking: --")
        self.menu.add(self.menu_thinking)
        
        self.menu_max = create_menu_item("  🔥 Max Mode: --")
        self.menu.add(self.menu_max)
        
        self.menu.add(rumps.separator)
        
        # Actions
        self.menu_refresh = rumps.MenuItem("↻ Refresh Now", callback=self._on_refresh)
        self.menu.add(self.menu_refresh)
        
        self.menu_login = rumps.MenuItem("🔑 Login to Cursor", callback=self._on_login)
        self.menu.add(self.menu_login)
        
        self.menu_dashboard = rumps.MenuItem("🌐 Open Dashboard", 
                                            callback=self._on_open_dashboard)
        self.menu.add(self.menu_dashboard)
        
        self.menu.add(rumps.separator)
        
        # Settings with polling interval submenu
        self.menu_settings = rumps.MenuItem("⚙️ Settings")
        self.menu_poll_interval = rumps.MenuItem("Polling Interval")
        
        for interval in POLL_INTERVALS:
            label = f"{interval} min"
            if interval == self.poll_interval:
                label += " ✓"
            item = rumps.MenuItem(label, 
                                callback=self._make_interval_callback(interval))
            self.menu_poll_interval.add(item)
        
        self.menu_settings.add(self.menu_poll_interval)
        self.menu.add(self.menu_settings)
        
        self.menu.add(rumps.separator)
        self.menu.add(rumps.MenuItem("Quit", callback=self._on_quit))
```

## Step 11: The UI Update Loop

This is the magic that makes everything work smoothly:

```python
    def _on_ui_timer(self, timer):
        """Called every second to update UI from scraper state"""
        state = self.scraper.state.get_snapshot()
        
        # Track time for auto-refresh
        self.seconds_since_fetch += 1
        
        # Check if it's time to auto-fetch (during work hours)
        if self._should_auto_fetch(state):
            self.seconds_since_fetch = 0
            self.scraper.request_fetch()
        
        # Update UI based on state
        self._update_ui(state)
    
    def _should_auto_fetch(self, state: dict) -> bool:
        """Check if we should auto-fetch"""
        from datetime import datetime
        now = datetime.now()
        
        # Only during work hours
        if not (config.WORK_HOURS_START <= now.hour < config.WORK_HOURS_END):
            return False
        
        # Not if already fetching
        if state["status"] in ("fetching", "logging_in"):
            return False
        
        # Check interval
        return self.seconds_since_fetch >= (self.poll_interval * 60)
    
    def _set_item_text(self, item: rumps.MenuItem, text: str):
        """Update menu item text with proper styling"""
        item.title = text
        
        # Also update attributed string for better visibility
        try:
            ns_item = item._menuitem
            color = NSColor.labelColor()
            font = NSFont.menuFontOfSize_(13)
            attrs = {'NSColor': color, 'NSFont': font}
            attributed_string = NSAttributedString.alloc().initWithString_attributes_(
                text, attrs
            )
            ns_item.setAttributedTitle_(attributed_string)
        except:
            pass  # Fallback to regular title
```

**Why a 1-second timer?** 
- It's frequent enough to feel responsive
- Lightweight (just reads state and updates text)
- Allows accurate polling interval tracking

## Step 12: Updating the UI

```python
    def _update_ui(self, state: dict):
        """Update UI based on current state"""
        status = state["status"]
        error = state["error"]
        logged_in = state["logged_in"]
        data: Optional[UsageData] = state["usage_data"]
        last_fetch = state["last_fetch_time"]
        
        # Update status line
        if status == "fetching":
            self._set_item_text(self.menu_status, "⏳ Fetching...")
            self.title = "C ⏳"
        elif status == "logging_in":
            self._set_item_text(self.menu_status, "🔑 Waiting for login...")
            self.title = "C 🔑"
        elif error:
            self._set_item_text(self.menu_status, f"⚠️ {error}")
            if not logged_in:
                self.title = "C ?"
            else:
                self.title = "C ⚠️"
        elif last_fetch:
            self._set_item_text(self.menu_status, f"● Updated at {last_fetch}")
        else:
            self._set_item_text(self.menu_status, "● Ready")
        
        # Update usage data if available
        if data:
            # Menu bar title shows remaining
            self.title = f"C {data.included_remaining}"
            
            # Included usage
            used = data.included_used
            total = data.included_total
            pct = data.included_percentage
            self._set_item_text(
                self.menu_included, 
                f"  📊 Included: {used}/{total} ({pct:.1f}%)"
            )
            
            # On-demand
            self._set_item_text(
                self.menu_ondemand, 
                f"  💵 On-Demand: ${data.ondemand_used:.2f} / ${data.ondemand_limit:.2f}"
            )
            
            # Model
            if data.last_model:
                model = data.last_model
                if len(model) > 35:
                    model = model[:32] + "..."
                self._set_item_text(self.menu_model, f"  🤖 {model}")
            
            # Timestamp
            if data.last_timestamp:
                self._set_item_text(self.menu_timestamp, f"  🕐 {data.last_timestamp}")
            
            # Thinking mode
            if data.is_thinking_mode:
                self._set_item_text(
                    self.menu_thinking, 
                    "  ⚡ Thinking: Yes (2x requests)"
                )
            else:
                self._set_item_text(self.menu_thinking, "  ⚡ Thinking: No")
            
            # Max mode with alert
            if data.is_max_mode:
                self._set_item_text(self.menu_max, "  🔥 Max Mode: Yes")
                if not self.last_alerted_max_mode:
                    self._alert_max_mode(data)
                    self.last_alerted_max_mode = True
            else:
                self._set_item_text(self.menu_max, "  🔥 Max Mode: No")
                self.last_alerted_max_mode = False
    
    def _alert_max_mode(self, data: UsageData):
        """Show notification for max mode"""
        if config.ALERT_ON_MAX_MODE:
            rumps.notification(
                title="Cursor Max Mode Detected",
                subtitle="⚠️ High resource usage",
                message=f"Model: {data.last_model or 'Unknown'}",
                sound=True
            )
```

## Step 13: Menu Actions

```python
    def _make_interval_callback(self, interval: int):
        """Create callback for interval selection"""
        def callback(sender):
            self._set_poll_interval(interval)
        return callback
    
    def _set_poll_interval(self, interval: int):
        """Set polling interval"""
        self.poll_interval = interval
        self.seconds_since_fetch = 0  # Reset counter
        
        # Update menu checkmarks
        for key in list(self.menu_poll_interval.keys()):
            item = self.menu_poll_interval[key]
            if isinstance(item, rumps.MenuItem):
                title = item.title.replace(" ✓", "")
                if f"{interval} min" == title:
                    item.title = f"{interval} min ✓"
                else:
                    item.title = title
    
    def _on_startup(self, timer):
        """Called once after startup"""
        timer.stop()
        self.scraper.request_fetch()
    
    def _on_refresh(self, sender):
        """Manual refresh"""
        self.seconds_since_fetch = 0
        self.scraper.request_fetch()
    
    def _on_login(self, sender):
        """Start login flow"""
        self.scraper.request_login()
    
    def _on_open_dashboard(self, sender):
        """Open dashboard in browser"""
        webbrowser.open(config.CURSOR_DASHBOARD_URL)
    
    def _on_quit(self, sender):
        """Quit app"""
        self.ui_timer.stop()
        self.scraper.stop()
        rumps.quit_application()


def main():
    """Main entry point"""
    rumps.debug_mode(False)
    app = CursorUsageApp()
    app.run()


if __name__ == "__main__":
    main()
```

## Step 14: Running the App

Create a simple `run.sh` script:

```bash
#!/bin/bash
# Run the Cursor Usage Menu Bar App

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Activate virtual environment
source venv/bin/activate

# Run the app
python app.py
```

Make it executable and run:

```bash
chmod +x run.sh
./run.sh
```

You should see "C" appear in your menu bar!

## Step 15: Auto-Start on Login (Optional)

To make the app start automatically, create `install-launch-agent.sh`:

```bash
#!/bin/bash
# Install Launch Agent to start app on login

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLIST_NAME="com.cursor-usage.app.plist"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME"
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python"

# Create plist content with direct Python path
cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" 
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.cursor-usage.app</string>
    <key>ProgramArguments</key>
    <array>
        <string>$VENV_PYTHON</string>
        <string>$SCRIPT_DIR/app.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$SCRIPT_DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$HOME/.cursor-usage-app/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>$HOME/.cursor-usage-app/stderr.log</string>
</dict>
</plist>
EOF

# Unload if already loaded
launchctl unload "$PLIST_PATH" 2>/dev/null || true

# Load the launch agent
launchctl load "$PLIST_PATH"

echo "✅ Launch agent installed and started!"
```

Run it:

```bash
chmod +x install-launch-agent.sh
./install-launch-agent.sh
```

## Key Lessons Learned

### 1. Thread Safety is Critical

When building macOS apps, UI updates **must** happen on the main thread. Playwright operations block, so they **must** happen on a background thread. The solution:

- Use a thread-safe state object with locks
- Use a task queue for communication
- Use a timer to poll state and update UI

### 2. Persistent Browser Context

Using `launch_persistent_context()` with a data directory:
- Saves cookies between runs
- Keeps you logged in
- Avoids constant re-authentication

### 3. Polling vs. Real-time

We use polling (checking every 15 minutes) instead of real-time updates because:
- Cursor's dashboard doesn't have a public API
- Web scraping is resource-intensive
- We only need updates during work hours
- It's respectful to Cursor's servers

### 4. Error Handling

Always handle errors gracefully:
- Show status in the UI
- Log errors to files
- Provide manual refresh option
- Allow users to re-login easily

### 5. Dark Mode Support

macOS dark mode can make text invisible. Use `NSAttributedString` with `NSColor.labelColor()` to ensure text adapts to the color scheme.

## Potential Improvements

Here are some ideas to extend this app:

1. **Notifications**: Alert when you're running low on requests
2. **History Tracking**: Store usage data to CSV for trend analysis
3. **Cost Calculator**: Estimate your monthly on-demand costs
4. **Model Recommendations**: Suggest using non-thinking models when appropriate
5. **Team View**: If you manage a team, show aggregate usage
6. **Export Data**: Button to export usage history

## Common Issues and Solutions

### Issue: "Operation not permitted"
**Solution:** The launch agent needs direct Python path, not a shell script. Use the launch agent configuration shown above.

### Issue: Text appears gray
**Solution:** Use `NSAttributedString` with `NSColor.labelColor()` as shown in the code.

### Issue: App crashes with "greenlet" error
**Solution:** Never call Playwright from a thread other than where it was created. Use the task queue pattern.

### Issue: Login doesn't work
**Solution:** Make sure you're waiting long enough. Some SSO flows take 30+ seconds. Increase the timeout in `_do_login()`.

## Conclusion

You've just built a complete macOS menu bar app! You learned:

- How to use rumps for menu bar apps
- Thread-safe programming patterns
- Web scraping with Playwright
- macOS launch agents
- Dark mode support

This same architecture can be adapted for tracking other web services - GitHub actions, CI/CD pipelines, API quotas, or anything else you need to monitor.

The key is the separation of concerns:
- **Scraper thread**: Does the heavy lifting
- **Main thread**: Handles UI
- **State object**: Bridges them safely

Happy coding!

---

*Have questions or improvements? Let me know in the comments!*

**Tags:** #macOS #Python #MenuBar #Playwright #WebScraping #CursorAI #rumps #Threading
