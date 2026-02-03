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
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self, key) and not key.startswith('_'):
                    setattr(self, key, value)
    
    def get_snapshot(self) -> dict:
        with self._lock:
            return {
                "status": self.status,
                "error": self.error,
                "logged_in": self.logged_in,
                "usage_data": self.usage_data,
                "last_fetch_time": self.last_fetch_time,
            }


class CursorScraper:
    """
    Scraper for Cursor dashboard.
    Uses a dedicated thread for all Playwright operations.
    State is shared via a thread-safe ScraperState object.
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
            # If we need different headless mode, restart
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
    
    def _do_fetch(self):
        """Fetch usage data"""
        self.state.update(status="fetching", error=None)
        
        try:
            self._ensure_browser(headless=True)
            
            # Navigate to dashboard
            self._page.goto(config.CURSOR_DASHBOARD_URL, wait_until="domcontentloaded", timeout=30000)
            
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
        included_match = re.search(r'Included-Request Usage.*?(\d+)\s*/\s*(\d+)', all_text, re.DOTALL)
        if included_match:
            data.included_used = int(included_match.group(1))
            data.included_total = int(included_match.group(2))
        
        # Parse on-demand usage - find pattern like "$0 / $10"
        ondemand_match = re.search(r'On-Demand Usage.*?\$(\d+(?:\.\d+)?)\s*/\s*\$(\d+(?:\.\d+)?)', all_text, re.DOTALL)
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
                    data.last_timestamp = timestamp_span.get('title') or timestamp_span.get_text(strip=True)
                
                # Model name (4th cell)
                model_span = cells[3].find('span', title=True)
                if model_span:
                    data.last_model = model_span.get('title') or model_span.get_text(strip=True)
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
