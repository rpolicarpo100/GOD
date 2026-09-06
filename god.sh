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
    help|*)
        echo ""
        echo "GOD — Commands"
        echo ""
        echo "  ./god.sh start       Start the server (localhost only, port $GOD_PORT)"
        echo "  ./god.sh start-lan   Start the server (LAN accessible, port $GOD_PORT)"
        echo "  ./god.sh stop        Stop the server"
        echo "  ./god.sh status      Check if server is running"
        echo "  ./god.sh test        Run test suite"
        echo "  ./god.sh benchmark   Run benchmark suite"
        echo "  ./god.sh doctor      Run diagnostics"
        echo "  ./god.sh backup      Backup config + data"
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
