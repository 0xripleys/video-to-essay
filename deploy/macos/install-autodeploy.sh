#!/usr/bin/env bash
set -euo pipefail

# Install the auto-deploy LaunchAgent.
# Usage:
#   bash deploy/macos/install-autodeploy.sh
#   CHECK_INTERVAL=600 bash deploy/macos/install-autodeploy.sh

INSTALL_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT_DIR="$INSTALL_DIR/deploy/macos"
LAUNCH_DIR="$HOME/Library/LaunchAgents"
LABEL="com.video-to-essay.autodeploy"
CHECK_INTERVAL="${CHECK_INTERVAL:-300}"
BASH_PATH="$(command -v bash)"
GIT_PATH="$(command -v git)"
PATH_VALUE="$(dirname "$BASH_PATH"):$(dirname "$GIT_PATH"):/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

if ! [[ "$CHECK_INTERVAL" =~ ^[0-9]+$ ]] || [ "$CHECK_INTERVAL" -lt 60 ]; then
    echo "ERROR: CHECK_INTERVAL must be an integer >= 60 seconds"
    exit 1
fi

mkdir -p "$INSTALL_DIR/logs"
mkdir -p "$LAUNCH_DIR"
chmod +x "$SCRIPT_DIR/autodeploy.sh"

src="$SCRIPT_DIR/$LABEL.plist"
dst="$LAUNCH_DIR/$LABEL.plist"

sed \
    -e "s|__BASH_PATH__|$BASH_PATH|g" \
    -e "s|__INSTALL_DIR__|$INSTALL_DIR|g" \
    -e "s|__PATH__|$PATH_VALUE|g" \
    -e "s|__CHECK_INTERVAL__|$CHECK_INTERVAL|g" \
    "$src" > "$dst"

plutil -lint "$dst" >/dev/null

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$dst"

echo "Installed $LABEL"
echo "Interval: ${CHECK_INTERVAL}s"
echo "Log: $INSTALL_DIR/logs/autodeploy.log"
echo "Status: launchctl print gui/$(id -u)/$LABEL"
