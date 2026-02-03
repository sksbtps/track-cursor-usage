# Cursor Usage Tracker - macOS Menu Bar App

<div align="center">

A lightweight macOS menu bar application that displays your Cursor AI usage statistics in real-time.

![Status: Active](https://img.shields.io/badge/status-active-success.svg)
![Platform: macOS](https://img.shields.io/badge/platform-macOS-lightgrey.svg)
![Python: 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)

</div>

## ✨ Features

- **📊 Real-time Usage Tracking**: Monitor included requests remaining directly in your menu bar
- **💵 On-Demand Monitoring**: Track your on-demand spending against your limit
- **🤖 Model Information**: See the last AI model you used and when
- **⚡ Thinking Mode Alert**: Visual indicator when thinking models are active (costs 2x requests)
- **🔥 Max Mode Alert**: Automatic notification when Max mode is detected
- **⏰ Smart Polling**: Only fetches during work hours (9 AM - 5 PM) to save resources
- **🔐 Secure Authentication**: Uses persistent browser session - no password storage
- **⚙️ Configurable**: Choose your own polling interval (5, 10, 15, 30, or 60 minutes)

## 🖥️ Menu Bar Display

The menu bar shows the remaining included requests with a simple indicator:

- `C 488` - Normal mode, 488 requests remaining
- `C ⏳` - Currently fetching data
- `C 🔑` - Login required
- `C ?` - Not authenticated
- `C ⚠️` - Error occurred

## 📋 Dropdown Menu

Click the menu bar icon to see detailed information:

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
    Polling Interval > [5, 10, 15✓, 30, 60 min]
──────────────────
Quit
```

## 🚀 Installation

### Prerequisites

- macOS 10.14 or later
- Python 3.8 or later
- Homebrew (for installing Python if needed)

### Quick Start

1. **Clone the repository**:
   ```bash
   cd ~/Desktop/projects
   git clone https://github.com/sksbtps/track-cursor-usage.git
   cd track-cursor-usage
   ```

2. **Run the setup script**:
   ```bash
   chmod +x setup.sh
   ./setup.sh
   ```
   This will:
   - Create a Python virtual environment
   - Install required dependencies (rumps, playwright, beautifulsoup4)
   - Install Playwright browser (Chromium)
   - Create necessary data directories

3. **Start the app**:
   ```bash
   ./run.sh
   ```

4. **Login to Cursor**:
   - Look for "C" in your menu bar
   - Click it and select "🔑 Login to Cursor"
   - A browser window will open
   - Log in with your Cursor account
   - The app will auto-detect successful login and close the browser
   - Your usage data will start appearing!

### Auto-Start on Login (Optional)

To have the app start automatically when you log in:

```bash
./install-launch-agent.sh
```

To remove auto-start:
```bash
launchctl unload ~/Library/LaunchAgents/com.cursor-usage.app.plist
rm ~/Library/LaunchAgents/com.cursor-usage.app.plist
```

## ⚙️ Configuration

Edit `config.py` to customize the app behavior:

```python
# Polling interval (default: 15 minutes, can also be changed in-app)
POLL_INTERVAL_MINUTES = 15

# Work hours for automatic polling (9 AM - 5 PM)
WORK_HOURS_START = 9
WORK_HOURS_END = 17

# Alert settings
ALERT_ON_MAX_MODE = True        # Show notification when Max mode detected
ALERT_ON_THINKING_MODE = False  # No notification for thinking (shown in menu)
```

## 🛠️ How It Works

### Architecture

The app uses a thread-safe architecture to avoid UI blocking:

1. **Main Thread**: Handles the rumps UI (required by macOS)
2. **Browser Thread**: Runs all Playwright operations for web scraping
3. **Communication**: A thread-safe `ScraperState` object shared between threads
4. **UI Updates**: A 1-second timer polls the state and updates the UI on the main thread

### Data Collection

1. **Authentication**: Uses Playwright with a persistent browser context to maintain login state
2. **Scraping**: Fetches the Cursor dashboard page and parses HTML for usage statistics
3. **Polling**: Automatically refreshes during work hours at your chosen interval
4. **Notifications**: Shows macOS notifications for Max mode usage

## 📁 Project Structure

```
track-cursor-usage/
├── app.py                      # Main menu bar application
├── scraper.py                  # Cursor dashboard scraper
├── config.py                   # Configuration settings
├── requirements.txt            # Python dependencies
├── setup.sh                    # Setup script
├── run.sh                      # Run script
├── install-launch-agent.sh     # Auto-start installer
└── README.md                   # This file
```

## 🔒 Privacy & Security

- Your Cursor credentials are **never stored** by this app
- Login session is maintained via browser cookies in `~/.cursor-usage-app/browser-data`
- All data stays **local on your machine**
- The app only reads your usage statistics from the dashboard

## 🐛 Troubleshooting

### "Login Required" keeps appearing

- Click "🔑 Login to Cursor" in the menu
- Make sure you complete the login in the browser window
- Wait for the app to auto-detect (it checks every 2 seconds)
- If using SSO, ensure the login completes fully

### App not starting

- Check logs: `cat ~/.cursor-usage-app/stderr.log`
- Ensure Python virtual environment is set up: `./setup.sh`
- Make sure Python 3.8+ is installed: `python3 --version`

### Data not updating

- Click "↻ Refresh Now" in the menu to manually fetch
- Check if it's within work hours (9 AM - 5 PM by default)
- Verify internet connection
- Check the status message in the dropdown

### Browser issues

- Delete browser data and re-login:
  ```bash
  rm -rf ~/.cursor-usage-app/browser-data
  ```
- Restart the app and login again

### Text appears too light (dark mode)

The latest version includes proper text styling. If text is still hard to read, restart the app:
```bash
pkill -f "python.*app.py"
./run.sh
```

## 🤝 Contributing

Contributions are welcome! Feel free to:

- Report bugs by opening an issue
- Suggest new features
- Submit pull requests

## 📝 License

MIT License - feel free to modify and distribute.

## 🙏 Acknowledgments

- Built with [rumps](https://github.com/jaredks/rumps) - Ridiculously Uncomplicated macOS Python Statusbar apps
- Uses [Playwright](https://playwright.dev/) for reliable web scraping
- Inspired by the need to track Cursor AI usage efficiently

---

<div align="center">

**Made with ❤️ for the Cursor community**

[Report Bug](https://github.com/sksbtps/track-cursor-usage/issues) · [Request Feature](https://github.com/sksbtps/track-cursor-usage/issues)

</div>
