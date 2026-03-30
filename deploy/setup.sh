#!/usr/bin/env bash
set -euo pipefail

# Video-to-Essay backend server setup
# Usage: curl -sSL <raw-url> | bash
#   or:  ssh root@your-server 'bash -s' < deploy/setup.sh

echo "=== Installing system dependencies ==="
PACKAGES=""
for pkg in ffmpeg unzip curl git; do
    if ! command -v "$pkg" &>/dev/null; then
        PACKAGES="$PACKAGES $pkg"
    fi
done
if [ -n "$PACKAGES" ]; then
    apt-get update -qq
    apt-get install -y -qq $PACKAGES
else
    echo "All system packages already installed"
fi

echo "=== Installing uv ==="
export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv &>/dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
else
    echo "uv already installed"
fi

echo "=== Installing deno ==="
export PATH="$HOME/.deno/bin:$PATH"
if ! command -v deno &>/dev/null; then
    curl -fsSL https://deno.land/install.sh | sh
else
    echo "deno already installed"
fi

echo "=== Cloning repo ==="
INSTALL_DIR="$HOME/video-to-essay"
if [ -d "$INSTALL_DIR" ]; then
    echo "Repo already exists, pulling latest..."
    cd "$INSTALL_DIR" && git pull
else
    git clone https://github.com/0xripleys/video-to-essay.git "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

echo "=== Installing Python dependencies ==="
uv sync

echo "=== Setting up .env ==="
if [ ! -f .env ]; then
    cat > .env <<'ENVEOF'
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
else
    echo ".env already exists, skipping"
fi

echo "=== Installing systemd services ==="
cp deploy/*.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable video-to-essay-discover video-to-essay-download video-to-essay-process video-to-essay-deliver

echo "=== Restarting workers ==="
systemctl restart video-to-essay-discover video-to-essay-download video-to-essay-process video-to-essay-deliver

echo ""
echo "=== Setup complete ==="
echo "Worker status:"
systemctl is-active video-to-essay-discover video-to-essay-download video-to-essay-process video-to-essay-deliver || true
echo ""
echo "View logs: journalctl -u video-to-essay-download -f"
