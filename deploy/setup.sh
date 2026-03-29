#!/usr/bin/env bash
set -euo pipefail

# Video-to-Essay backend server setup
# Usage: curl -sSL <raw-url> | bash
#   or:  ssh root@your-server 'bash -s' < deploy/setup.sh

echo "=== Installing system dependencies ==="
apt-get update -qq
apt-get install -y -qq ffmpeg unzip curl git

echo "=== Installing uv ==="
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

echo "=== Installing deno ==="
curl -fsSL https://deno.land/install.sh | sh
export PATH="$HOME/.deno/bin:$PATH"

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

echo ""
echo "=== Setup complete ==="
echo "Next steps:"
echo "  1. Edit $INSTALL_DIR/.env with your credentials"
echo "  2. Start workers:"
echo "     systemctl start video-to-essay-discover video-to-essay-download video-to-essay-process video-to-essay-deliver"
echo "  3. Check status:"
echo "     systemctl status video-to-essay-*"
echo "  4. View logs:"
echo "     journalctl -u video-to-essay-download -f"
