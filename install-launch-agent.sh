#!/bin/bash
# Install Launch Agent to start app on login

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLIST_NAME="com.cursor-usage.app.plist"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME"
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python"

# Create plist content with direct Python path
cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
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
echo "   The app should appear in your menu bar shortly."
echo ""
echo "   To check status: launchctl list | grep cursor-usage"
echo "   To view logs: tail -f ~/.cursor-usage-app/stderr.log"
echo "   To uninstall: launchctl unload $PLIST_PATH && rm $PLIST_PATH"
