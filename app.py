#!/usr/bin/env python3
"""
Cursor Usage Menu Bar App for macOS
Shows Cursor API usage in the menu bar with detailed dropdown

Architecture:
- Main thread: rumps UI (required by macOS)
- Browser thread: Playwright operations
- Communication: Thread-safe ScraperState object
- UI updates: rumps.Timer polls state and updates UI on main thread
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
        self.last_status = None
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
    
    def _set_item_text(self, item: rumps.MenuItem, text: str):
        """Update menu item text with proper styling"""
        item.title = text
        
        # Also update attributed string for better visibility
        try:
            ns_item = item._menuitem
            color = NSColor.labelColor()
            font = NSFont.menuFontOfSize_(13)
            attrs = {'NSColor': color, 'NSFont': font}
            attributed_string = NSAttributedString.alloc().initWithString_attributes_(text, attrs)
            ns_item.setAttributedTitle_(attributed_string)
        except:
            pass  # Fallback to regular title
    
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
        
        self.menu_dashboard = rumps.MenuItem("🌐 Open Dashboard", callback=self._on_open_dashboard)
        self.menu.add(self.menu_dashboard)
        
        self.menu.add(rumps.separator)
        
        # Settings
        self.menu_settings = rumps.MenuItem("⚙️ Settings")
        self.menu_poll_interval = rumps.MenuItem("Polling Interval")
        
        for interval in POLL_INTERVALS:
            label = f"{interval} min"
            if interval == self.poll_interval:
                label += " ✓"
            item = rumps.MenuItem(label, callback=self._make_interval_callback(interval))
            self.menu_poll_interval.add(item)
        
        self.menu_settings.add(self.menu_poll_interval)
        self.menu.add(self.menu_settings)
        
        self.menu.add(rumps.separator)
        self.menu.add(rumps.MenuItem("Quit", callback=self._on_quit))
    
    def _make_interval_callback(self, interval: int):
        """Create callback for interval selection"""
        def callback(sender):
            self._set_poll_interval(interval)
        return callback
    
    def _on_startup(self, timer):
        """Called once after startup"""
        timer.stop()
        self.scraper.request_fetch()
    
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
            self._set_item_text(self.menu_included, f"  📊 Included: {used}/{total} ({pct:.1f}%)")
            
            # On-demand
            self._set_item_text(self.menu_ondemand, f"  💵 On-Demand: ${data.ondemand_used:.2f} / ${data.ondemand_limit:.2f}")
            
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
                self._set_item_text(self.menu_thinking, "  ⚡ Thinking: Yes (2x requests)")
            else:
                self._set_item_text(self.menu_thinking, "  ⚡ Thinking: No")
            
            # Max mode
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
    
    def _set_poll_interval(self, interval: int):
        """Set polling interval"""
        self.poll_interval = interval
        self.seconds_since_fetch = 0  # Reset counter
        
        # Update menu checkmarks
        for key in list(self.menu_poll_interval.keys()):
            item = self.menu_poll_interval[key]
            if isinstance(item, rumps.MenuItem):
                # Extract the number from the title
                title = item.title.replace(" ✓", "")
                if f"{interval} min" == title:
                    item.title = f"{interval} min ✓"
                else:
                    item.title = title
    
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
