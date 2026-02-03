#!/bin/bash
# Install Launch Agent to start app on login

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLIST_NAME="com.cursor-usage.app.plist"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME"

# Create plist content
cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.cursor-usage.app</string>
    <key>ProgramArguments</key>
    <array>
        <string>$SCRIPT_DIR/run.sh</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>$HOME/.cursor-usage-app/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>$HOME/.cursor-usage-app/stderr.log</string>
</dict>
</plist>
EOF

# Load the launch agent
launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load "$PLIST_PATH"

echo "✅ Launch agent installed!"
echo "   The app will now start automatically on login."
echo ""
echo "   To uninstall: launchctl unload $PLIST_PATH && rm $PLIST_PATH"
