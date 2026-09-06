#!/bin/bash
# GOD — Command helper (Linux/Mac)

GOD_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PY="$GOD_DIR/.venv/bin/python"
GOD_PORT="${GOD_PORT:-8000}"
PID_FILE="$GOD_DIR/data/god.pid"
LOG_DIR="$GOD_DIR/logs"

# Fallback to system Python if no venv
if [ ! -f "$VENV_PY" ]; then
    if command -v python3 &>/dev/null; then
        VENV_PY="python3"
    else
        echo "[FAIL] Python not found. Run ./setup.sh first."
        exit 1
    fi
fi

CMD="${1:-help}"

case "$CMD" in
    start)
        BIND="127.0.0.1"
        # Check port conflict
        if ss -tlnp 2>/dev/null | grep -q ":$GOD_PORT " || netstat -tlnp 2>/dev/null | grep -q ":$GOD_PORT "; then
            echo "[FAIL] Port $GOD_PORT is already in use."
            echo "       Stop the existing process or set GOD_PORT=<other>."
            exit 1
        fi
        # Check PID file
        if [ -f "$PID_FILE" ]; then
            OLD_PID=$(cat "$PID_FILE" 2>/dev/null)
            if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
                echo "[FAIL] GOD is already running (PID $OLD_PID)."
                echo "       Stop first: ./god.sh stop"
                exit 1
            fi
            rm -f "$PID_FILE"
        fi
        mkdir -p "$LOG_DIR"
        echo "Starting GOD on port $GOD_PORT..."
        echo "Dashboard: http://localhost:$GOD_PORT"
        echo "API docs:  http://localhost:$GOD_PORT/docs"
        echo "Bind:      $BIND (localhost only)"
        echo "Auth:      Required for admin endpoints"
        echo "Logs:      $LOG_DIR/"
        echo ""
        # Start in background, capture PID
        nohup $VENV_PY -m uvicorn server:app --host $BIND --port $GOD_PORT \
            > "$LOG_DIR/god.log" 2>&1 &
        GOD_PID=$!
        echo "$GOD_PID" > "$PID_FILE"
        # Wait briefly and verify
        sleep 2
        if kill -0 "$GOD_PID" 2>/dev/null; then
            echo "[OK] GOD started (PID $GOD_PID, port $GOD_PORT)."
            echo "     Dashboard: http://localhost:$GOD_PORT"
            echo "     Logs:      tail -f $LOG_DIR/god.log"
            echo "     Stop:      ./god.sh stop"
        else
            echo "[FAIL] GOD failed to start. Check logs:"
            echo "       tail -20 $LOG_DIR/god.log"
            rm -f "$PID_FILE"
            exit 1
        fi
        ;;
    start-lan)
        BIND="0.0.0.0"
        # Check port conflict
        if ss -tlnp 2>/dev/null | grep -q ":$GOD_PORT " || netstat -tlnp 2>/dev/null | grep -q ":$GOD_PORT "; then
            echo "[FAIL] Port $GOD_PORT is already in use."
            echo "       Stop the existing process or set GOD_PORT=<other>."
            exit 1
        fi
        if [ -f "$PID_FILE" ]; then
            OLD_PID=$(cat "$PID_FILE" 2>/dev/null)
            if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
                echo "[FAIL] GOD is already running (PID $OLD_PID)."
                echo "       Stop first: ./god.sh stop"
                exit 1
            fi
            rm -f "$PID_FILE"
        fi
        mkdir -p "$LOG_DIR"
        echo "WARNING: Starting GOD in LAN mode!"
        echo "This exposes GOD to your local network."
        echo "Authentication is required for admin endpoints."
        echo ""
        echo "Starting GOD on port $GOD_PORT..."
        echo "Dashboard: http://localhost:$GOD_PORT"
        echo "Bind:      $BIND (LAN accessible)"
        echo ""
        nohup $VENV_PY -m uvicorn server:app --host $BIND --port $GOD_PORT \
            > "$LOG_DIR/god.log" 2>&1 &
        GOD_PID=$!
        echo "$GOD_PID" > "$PID_FILE"
        sleep 2
        if kill -0 "$GOD_PID" 2>/dev/null; then
            echo "[OK] GOD started (PID $GOD_PID, port $GOD_PORT, LAN mode)."
        else
            echo "[FAIL] GOD failed to start. Check: tail -20 $LOG_DIR/god.log"
            rm -f "$PID_FILE"
            exit 1
        fi
        ;;
    stop)
        echo "Stopping GOD..."
        STOPPED=0
        # Try PID file first
        if [ -f "$PID_FILE" ]; then
            GOD_PID=$(cat "$PID_FILE" 2>/dev/null)
            if [ -n "$GOD_PID" ] && kill -0 "$GOD_PID" 2>/dev/null; then
                kill "$GOD_PID" 2>/dev/null
                # Wait up to 5s for graceful shutdown
                for i in 1 2 3 4 5; do
                    kill -0 "$GOD_PID" 2>/dev/null || break
                    sleep 1
                done
                # Force if still alive
                if kill -0 "$GOD_PID" 2>/dev/null; then
                    kill -9 "$GOD_PID" 2>/dev/null
                fi
                STOPPED=1
                echo "[OK] Stopped (PID $GOD_PID)."
            fi
            rm -f "$PID_FILE"
        fi
        # Fallback: find by process name
        if [ "$STOPPED" = "0" ]; then
            if pgrep -f "uvicorn server:app" > /dev/null 2>&1; then
                pkill -f "uvicorn server:app"
                echo "[OK] Stopped (by process name)."
            else
                echo "[WARN] Not running."
            fi
        fi
        ;;
    status)
        echo "Checking GOD status..."
        # Check PID file
        if [ -f "$PID_FILE" ]; then
            GOD_PID=$(cat "$PID_FILE" 2>/dev/null)
            if [ -n "$GOD_PID" ] && kill -0 "$GOD_PID" 2>/dev/null; then
                echo "[OK] Process alive (PID $GOD_PID)."
            else
                echo "[WARN] PID file exists but process not found."
                rm -f "$PID_FILE"
            fi
        fi
        # Check health endpoint
        if curl -s http://127.0.0.1:$GOD_PORT/api/health >/dev/null 2>&1; then
            echo "[OK] GOD is running on port $GOD_PORT."
            curl -s http://127.0.0.1:$GOD_PORT/api/health | $VENV_PY -m json.tool 2>/dev/null
            echo ""
            echo "Auth status:"
            curl -s http://127.0.0.1:$GOD_PORT/api/auth/status | $VENV_PY -m json.tool 2>/dev/null
        else
            echo "[WARN] GOD is not responding on port $GOD_PORT."
            echo "       Start with: ./god.sh start"
        fi
        ;;
    backup)
        BACKUP_DIR="$GOD_DIR/backups/$(date +%Y-%m-%d_%H-%M-%S)"
        mkdir -p "$BACKUP_DIR"
        echo "Creating backup: $BACKUP_DIR"
        # Backup config
        cp -v "$GOD_DIR/.env" "$BACKUP_DIR/.env" 2>/dev/null && echo "  [OK] .env" || echo "  [SKIP] .env"
        cp -v "$GOD_DIR/config.yaml" "$BACKUP_DIR/config.yaml" 2>/dev/null && echo "  [OK] config.yaml" || echo "  [SKIP] config.yaml"
        # Backup data
        if [ -d "$GOD_DIR/data" ]; then
            cp -r "$GOD_DIR/data" "$BACKUP_DIR/data" 2>/dev/null
            echo "  [OK] data/ ($(du -sh "$GOD_DIR/data" 2>/dev/null | cut -f1))"
        fi
        # Create manifest
        cat > "$BACKUP_DIR/manifest.json" << EOF
{
  "timestamp": "$(date -Iseconds)",
  "commit": "$(cd "$GOD_DIR" && git rev-parse --short HEAD 2>/dev/null || echo 'unknown')",
  "port": $GOD_PORT,
  "files": $(ls "$BACKUP_DIR" | wc -l)
}
EOF
        echo ""
        echo "[OK] Backup complete: $BACKUP_DIR"
        echo "     Size: $(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1)"
        ;;
    test)
        echo "Running tests..."
        $VENV_PY -m pytest tests/ -v
        ;;
    benchmark)
        echo "Running benchmark..."
        $VENV_PY -c "
from superai.benchmark import run
s = run('cli')
print(f'BENCHMARK {s[\"run_id\"]}  n={s[\"n\"]}  passed={s[\"passed\"]}  skipped={s[\"skipped\"]}')
for r in s.get('rows') or []:
    st = 'SKIP' if r.get('skipped') else ('PASS' if r.get('passed') else 'FAIL')
    print(f'  {st} {r[\"case_id\"]}  score={r.get(\"score\")}  {r.get(\"latency_ms\")}ms')
"
        ;;
    doctor)
        echo "Running diagnostics..."
        $VENV_PY -c "
from superai import repair
r = repair.run()
print(f'REPAIR {r[\"kind\"]} ok={r[\"ok\"]}')
for a in r.get('actions') or []:
    st = 'OK' if a.get('ok') else 'FAIL'
    print(f'  [{st}] {a[\"check\"]} {a.get(\"error\") or a.get(\"fix\") or \"\"}')
print()
print(r.get('note') or '')
"
        ;;
    dev)
        BIND="127.0.0.1"
        # Check port conflict
        if ss -tlnp 2>/dev/null | grep -q ":$GOD_PORT " || netstat -tlnp 2>/dev/null | grep -q ":$GOD_PORT "; then
            echo "[FAIL] Port $GOD_PORT is already in use."
            exit 1
        fi
        mkdir -p "$LOG_DIR"
        echo "Starting GOD in DEV mode (auto-reload) on port $GOD_PORT..."
        echo "Dashboard: http://localhost:$GOD_PORT"
        echo "Auto-reload: ENABLED (watches .py files)"
        echo ""
        $VENV_PY -m uvicorn server:app --host $BIND --port $GOD_PORT --reload
        ;;
    update)
        echo "Updating GOD..."
        # Check for local changes
        if [ -d "$GOD_DIR/.git" ]; then
            CHANGES=$(cd "$GOD_DIR" && git status --porcelain 2>/dev/null | wc -l)
            if [ "$CHANGES" -gt 0 ]; then
                echo "[WARN] Local changes detected ($CHANGES files)."
                echo "       Stash or commit before updating."
                cd "$GOD_DIR" && git status --short
                echo ""
                read -p "Continue anyway? (y/N) " -n 1 -r
                echo
                if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                    echo "Cancelled."
                    exit 0
                fi
            fi
            # Backup before update
            echo "[*] Creating pre-update backup..."
            $0 backup 2>/dev/null || true
            # Pull
            echo "[*] Pulling updates..."
            cd "$GOD_DIR" && git pull
            # Update deps
            echo "[*] Updating dependencies..."
            $VENV_PY -m pip install -r requirements.txt --quiet 2>&1
            # Run tests
            echo "[*] Running tests..."
            $VENV_PY -m pytest tests/ -q 2>/dev/null
            echo "[OK] Update complete."
        else
            echo "[FAIL] Not a git repository. Manual update required."
            exit 1
        fi
        ;;
    uninstall)
        echo ""
        echo "GOD — Uninstall"
        echo ""
        echo "  [1] Remove application only (keep data)"
        echo "  [2] Remove application + cache"
        echo "  [3] Remove everything (application + data + config)"
        echo "  [4] Backup then remove everything"
        echo "  [0] Cancel"
        echo ""
        read -p "Choose: " CHOICE
        case "$CHOICE" in
            1)
                echo "[*] Stopping GOD..."
                $0 stop 2>/dev/null || true
                echo "[*] Removing application files..."
                rm -rf "$GOD_DIR/.venv"
                rm -f "$GOD_DIR/data/god.pid"
                echo "[OK] Application removed. Data preserved in: $GOD_DIR/data/"
                echo "     To fully remove: rm -rf $GOD_DIR"
                ;;
            2)
                echo "[*] Stopping GOD..."
                $0 stop 2>/dev/null || true
                echo "[*] Removing application + cache..."
                rm -rf "$GOD_DIR/.venv"
                rm -rf "$GOD_DIR/data/qdrant"
                rm -rf "$GOD_DIR/data/sandbox"
                rm -rf "$GOD_DIR/__pycache__"
                rm -f "$GOD_DIR/data/god.pid"
                echo "[OK] Application + cache removed. Data preserved."
                ;;
            3)
                echo ""
                echo "WARNING: This permanently removes:"
                echo "  - Application code"
                echo "  - Database (data/spine.db)"
                echo "  - Auth data (data/auth/)"
                echo "  - GOD profiles (data/gods/)"
                echo "  - Configuration (.env, config.yaml)"
                echo "  - Logs"
                echo ""
                read -p "Type DELETE to confirm: " CONFIRM
                if [ "$CONFIRM" = "DELETE" ]; then
                    $0 stop 2>/dev/null || true
                    rm -rf "$GOD_DIR/.venv"
                    rm -rf "$GOD_DIR/data"
                    rm -rf "$GOD_DIR/logs"
                    rm -rf "$GOD_DIR/backups"
                    rm -f "$GOD_DIR/.env"
                    echo "[OK] Everything removed."
                else
                    echo "Cancelled."
                fi
                ;;
            4)
                $0 backup
                echo ""
                read -p "Now remove everything? Type DELETE to confirm: " CONFIRM
                if [ "$CONFIRM" = "DELETE" ]; then
                    $0 stop 2>/dev/null || true
                    rm -rf "$GOD_DIR/.venv"
                    rm -rf "$GOD_DIR/data"
                    rm -rf "$GOD_DIR/logs"
                    rm -f "$GOD_DIR/.env"
                    echo "[OK] Everything removed. Backup preserved in: $GOD_DIR/backups/"
                else
                    echo "Cancelled. Backup preserved."
                fi
                ;;
            *)
                echo "Cancelled."
                ;;
        esac
        ;;
    config)
        echo ""
        echo "GOD — Configuration"
        echo ""
        if [ -f "$GOD_DIR/.env" ]; then
            echo "[OK] .env already exists."
            echo ""
            read -p "Overwrite? (y/N) " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                echo "Cancelled."
                exit 0
            fi
        fi
        echo ""
        echo "Select mode:"
        echo ""
        echo "  [1] API / Cloud  — Use providers (Groq, Google, Anthropic, etc.)"
        echo "  [2] Offline      — No LLM, tools only"
        echo "  [3] Local Model  — Ollama or local endpoint"
        echo "  [4] Manual       — I'll edit .env myself"
        echo ""
        read -p "Choose [1-4]: " MODE
        case "$MODE" in
            1)
                echo ""
                echo "Enter API keys (leave blank to skip):"
                echo ""
                read -p "  Groq API key (free, fast): " GROQ_KEY
                read -p "  Google API key (free, Gemini): " GOOGLE_KEY
                read -p "  Anthropic API key (paid, Claude): " ANTHRO_KEY
                read -p "  OpenRouter API key (aggregator): " OPENR_KEY
                read -p "  Cerebras API key (free, fast): " CEREB_KEY
                read -p "  NVIDIA API key (free, DeepSeek): " NVIDIA_KEY
                read -p "  Mistral API key (free, Codestral): " MISTRAL_KEY
                read -p "  SambaNova API key (free): " SAMBA_KEY
                echo ""
                cat > "$GOD_DIR/.env" << ENVEOF
# GOD — API Keys (generated by god config)
# $(date -Iseconds)

GROQ_API_KEY=${GROQ_KEY}
GOOGLE_API_KEY=${GOOGLE_KEY}
ANTHROPIC_API_KEY=${ANTHRO_KEY}
OPENROUTER_API_KEY=${OPENR_KEY}
CEREBRAS_API_KEY=${CEREB_KEY}
NVIDIA_API_KEY=${NVIDIA_KEY}
MISTRAL_API_KEY=${MISTRAL_KEY}
SAMBANOVA_API_KEY=${SAMBA_KEY}
ENVEOF
                echo "[OK] .env created."
                # Count configured keys
                COUNT=$(grep -c "_API_KEY=" "$GOD_DIR/.env" | head -1)
                CONFIGURED=$(grep "_API_KEY=." "$GOD_DIR/.env" | wc -l)
                echo "     $CONFIGURED/$COUNT keys configured."
                ;;
            2)
                cat > "$GOD_DIR/.env" << 'ENVEOF'
# GOD — Offline mode (no API keys)
ENVEOF
                echo "[OK] .env created (offline mode)."
                ;;
            3)
                echo ""
                read -p "  Ollama host [http://localhost:11434]: " OLLAMA_HOST
                OLLAMA_HOST="${OLLAMA_HOST:-http://localhost:11434}"
                cat > "$GOD_DIR/.env" << ENVEOF
# GOD — Local model via Ollama
OLLAMA_HOST=${OLLAMA_HOST}
ENVEOF
                echo "[OK] .env created (Ollama at $OLLAMA_HOST)."
                ;;
            *)
                if [ ! -f "$GOD_DIR/.env" ]; then
                    cp "$GOD_DIR/.env.example" "$GOD_DIR/.env" 2>/dev/null
                    echo "[OK] Copied .env.example to .env. Edit with your keys."
                fi
                ;;
        esac
        echo ""
        echo "Edit later: $GOD_DIR/.env"
        ;;
    gpu)
        echo "GPU Detection"
        echo ""
        # NVIDIA
        if command -v nvidia-smi &>/dev/null; then
            echo "[OK] NVIDIA GPU detected:"
            nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || echo "  (nvidia-smi found but query failed)"
        else
            echo "[INFO] No NVIDIA GPU detected."
        fi
        # AMD
        if command -v rocm-smi &>/dev/null; then
            echo "[OK] AMD GPU detected."
        fi
        echo ""
        echo "GOD works without GPU in API/CPU mode."
        echo "Local AI models may be slower without dedicated GPU."
        ;;
    help|*)
        echo ""
        echo "GOD — Commands"
        echo ""
        echo "  ./god.sh start       Start the server (localhost only, port $GOD_PORT)"
        echo "  ./god.sh start-lan   Start the server (LAN accessible, port $GOD_PORT)"
        echo "  ./god.sh config      Configure API keys"
        echo "  ./god.sh dev         Start in dev mode (auto-reload)"
        echo "  ./god.sh stop        Stop the server"
        echo "  ./god.sh status      Check if server is running"
        echo "  ./god.sh test        Run test suite"
        echo "  ./god.sh benchmark   Run benchmark suite"
        echo "  ./god.sh doctor      Run diagnostics"
        echo "  ./god.sh backup      Backup config + data"
        echo "  ./god.sh update      Pull updates + deps + tests"
        echo "  ./god.sh uninstall   Remove GOD"
        echo "  ./god.sh gpu         Detect GPU"
        echo "  ./god.sh help        Show this help"
        echo ""
        echo "Environment:"
        echo "  GOD_PORT=9000 ./god.sh start   Use custom port"
        echo ""
        echo "Security:"
        echo "  Authentication required for admin endpoints."
        echo "  Create owner: POST /api/auth/setup"
        echo "  Login:        POST /api/auth/login"
        echo ""
        ;;
esac
