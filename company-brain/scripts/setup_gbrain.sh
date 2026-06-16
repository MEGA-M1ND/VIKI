#!/usr/bin/env bash
set -euo pipefail

PID_FILE="$(pwd)/.gbrain.pid"
GBRAIN_PORT="${GBRAIN_PORT:-3721}"

log() { echo "[setup_gbrain] $*"; }

# 1. Install Bun
if ! command -v bun &>/dev/null; then
    log "Bun not found — installing..."
    curl -fsSL https://bun.sh/install | bash
    export PATH="$HOME/.bun/bin:$PATH"
    log "Bun installed: $(bun --version)"
else
    log "Bun found: $(bun --version)"
fi

# Ensure bun is on PATH for remainder of script
export PATH="$HOME/.bun/bin:$PATH"

# 2. Install GBrain
if ! command -v gbrain &>/dev/null; then
    log "Installing GBrain..."
    bun install -g github:garrytan/gbrain
    log "GBrain installed"
else
    log "GBrain found: $(gbrain --version 2>/dev/null || echo 'unknown version')"
fi

# 3. Initialise brain (PGLite, zero-config)
BRAIN_DIR="$HOME/.gbrain"
if [ ! -d "$BRAIN_DIR" ]; then
    log "Initialising brain with PGLite..."
    gbrain init --pglite
else
    log "Brain already initialised at $BRAIN_DIR"
fi

# 4. Run doctor
log "Running gbrain doctor..."
gbrain doctor || {
    log "WARNING: gbrain doctor reported issues. Check output above."
}

# 5. Kill any existing server process
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        log "Stopping existing GBrain server (PID $OLD_PID)..."
        kill "$OLD_PID" || true
    fi
    rm -f "$PID_FILE"
fi

# 6. Start GBrain HTTP MCP server in background
log "Starting GBrain HTTP MCP server on port $GBRAIN_PORT..."
gbrain serve --http --port "$GBRAIN_PORT" &>/tmp/gbrain-server.log &
GBRAIN_PID=$!
echo "$GBRAIN_PID" > "$PID_FILE"
log "GBrain server started (PID $GBRAIN_PID)"
log "Logs: /tmp/gbrain-server.log"
log "Admin dashboard: http://localhost:$GBRAIN_PORT/admin"
log "MCP endpoint:    http://localhost:$GBRAIN_PORT/mcp"

# 7. Wait for server to be healthy
log "Waiting for server to respond..."
for i in $(seq 1 20); do
    if curl -sf "http://localhost:$GBRAIN_PORT/health" &>/dev/null; then
        log "Server is healthy!"
        break
    fi
    if [ "$i" -eq 20 ]; then
        log "ERROR: Server did not start within 10s. Check /tmp/gbrain-server.log"
        exit 1
    fi
    sleep 0.5
done

log "Setup complete. PID saved to $PID_FILE"
