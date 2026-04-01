#!/usr/bin/env bash
set -euo pipefail

# Video-to-Essay macOS setup (launchd)
# Usage: bash deploy/macos/setup.sh

INSTALL_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT_DIR="$INSTALL_DIR/deploy/macos"
LAUNCH_DIR="$HOME/Library/LaunchAgents"
WORKERS=(discover download process deliver)
UV_PATH="$(which uv)"
# PATH needed by download/process workers for ffmpeg, deno, etc.
WORKER_PATH="$(dirname "$UV_PATH"):/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

echo "=== Video-to-Essay macOS Setup ==="
echo "Install dir: $INSTALL_DIR"
echo "uv: $UV_PATH"

# Check dependencies
for cmd in uv ffmpeg deno; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "ERROR: $cmd not found. Install it first."
        exit 1
    fi
done

# Install Python deps
echo "=== Installing Python dependencies ==="
cd "$INSTALL_DIR"
uv sync

# Check .env
if [ ! -f "$INSTALL_DIR/.env" ]; then
    cat > "$INSTALL_DIR/.env" <<'ENVEOF'
DATABASE_URL=
ANTHROPIC_API_KEY=
DEEPGRAM_API_KEY=
AGENTMAIL_API_KEY=
AGENTMAIL_INBOX_ID=
S3_BUCKET_NAME=video-to-essay-runs
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=us-east-1
ENVEOF
    echo "Created .env — fill in the values before starting workers"
fi

# Load .env into plist EnvironmentVariables
echo "=== Loading .env ==="
ENV_VARS=""
while IFS='=' read -r key value; do
    [[ -z "$key" || "$key" =~ ^# ]] && continue
    # Strip surrounding quotes
    value="${value%\"}"
    value="${value#\"}"
    value="${value%\'}"
    value="${value#\'}"
    ENV_VARS="$ENV_VARS        <key>$key</key>\n        <string>$value</string>\n"
done < "$INSTALL_DIR/.env"

# Create logs dir
mkdir -p "$INSTALL_DIR/logs"
mkdir -p "$LAUNCH_DIR"

# Unload existing services
echo "=== Unloading existing services ==="
for w in "${WORKERS[@]}"; do
    launchctl bootout "gui/$(id -u)/com.video-to-essay.$w" 2>/dev/null || true
done

# Install plists with resolved paths and env vars
echo "=== Installing launchd plists ==="
for w in "${WORKERS[@]}"; do
    src="$SCRIPT_DIR/com.video-to-essay.$w.plist"
    dst="$LAUNCH_DIR/com.video-to-essay.$w.plist"

    sed \
        -e "s|__UV_PATH__|$UV_PATH|g" \
        -e "s|__INSTALL_DIR__|$INSTALL_DIR|g" \
        -e "s|__PATH__|$WORKER_PATH|g" \
        "$src" > "$dst"

    # Inject .env vars into EnvironmentVariables dict
    if [ -n "$ENV_VARS" ]; then
        # Insert env vars before the closing </dict> of EnvironmentVariables
        # (the first </dict> after <key>EnvironmentVariables</key>)
        python3 -c "
import re, sys
with open('$dst') as f:
    content = f.read()
env_block = '''$ENV_VARS'''.strip()
# Find the EnvironmentVariables dict and inject before its closing </dict>
pattern = r'(<key>EnvironmentVariables</key>\s*<dict>)(.*?)(</dict>)'
def inject(m):
    return m.group(1) + m.group(2) + env_block + '\n        ' + m.group(3)
content = re.sub(pattern, inject, content, count=1, flags=re.DOTALL)
with open('$dst', 'w') as f:
    f.write(content)
"
    fi

    echo "  Installed $dst"
done

# Load services
echo "=== Loading services ==="
for w in "${WORKERS[@]}"; do
    launchctl bootstrap "gui/$(id -u)" "$LAUNCH_DIR/com.video-to-essay.$w.plist"
    echo "  Loaded com.video-to-essay.$w"
done

echo ""
echo "=== Setup complete ==="
echo ""
echo "Commands:"
echo "  Status:  launchctl list | grep video-to-essay"
echo "  Logs:    tail -f $INSTALL_DIR/logs/discover.log"
echo "  Stop:    launchctl bootout gui/$(id -u)/com.video-to-essay.discover"
echo "  Start:   launchctl bootstrap gui/$(id -u) $LAUNCH_DIR/com.video-to-essay.discover.plist"
echo "  Restart: bash deploy/macos/setup.sh"
