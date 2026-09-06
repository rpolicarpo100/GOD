#!/bin/bash
# GOD — Command helper (Linux/Mac)

GOD_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PY="$GOD_DIR/.venv/bin/python"
GOD_PORT="${GOD_PORT:-8000}"

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
        echo "Starting GOD on port $GOD_PORT..."
        echo "Dashboard: http://localhost:$GOD_PORT"
        echo "API docs:  http://localhost:$GOD_PORT/docs"
        echo "Bind:      $BIND (localhost only)"
        echo "Auth:      Required for admin endpoints"
        echo "Press Ctrl+C to stop."
        echo ""
        $VENV_PY -m uvicorn server:app --host $BIND --port $GOD_PORT
        ;;
    start-lan)
        BIND="0.0.0.0"
        echo "⚠  WARNING: Starting GOD in LAN mode!"
        echo "⚠  This exposes GOD to your local network."
        echo "⚠  Authentication is required for admin endpoints."
        echo ""
        echo "Starting GOD on port $GOD_PORT..."
        echo "Dashboard: http://localhost:$GOD_PORT"
        echo "Bind:      $BIND (LAN accessible)"
        echo "Auth:      Required for admin endpoints"
        echo "Press Ctrl+C to stop."
        echo ""
        $VENV_PY -m uvicorn server:app --host $BIND --port $GOD_PORT
        ;;
    stop)
        echo "Stopping GOD..."
        if pgrep -f "uvicorn server:app" > /dev/null; then
            pkill -f "uvicorn server:app"
            echo "[OK] Stopped."
        else
            echo "[WARN] Not running."
        fi
        ;;
    status)
        echo "Checking GOD status..."
        if curl -s http://127.0.0.1:$GOD_PORT/api/health >/dev/null 2>&1; then
            echo "[OK] GOD is running on port $GOD_PORT."
            curl -s http://127.0.0.1:$GOD_PORT/api/health | $VENV_PY -m json.tool 2>/dev/null
            echo ""
            echo "Auth status:"
            curl -s http://127.0.0.1:$GOD_PORT/api/auth/status | $VENV_PY -m json.tool 2>/dev/null
        else
            echo "[WARN] GOD is not running. Start with: ./god.sh start"
        fi
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
        echo "  ./god.sh start       Start the server (localhost only, port 8000)"
        echo "  ./god.sh start-lan   Start the server (LAN accessible, port 8000)"
        echo "  ./god.sh stop        Stop the server"
        echo "  ./god.sh status      Check if server is running"
        echo "  ./god.sh test        Run test suite"
        echo "  ./god.sh benchmark   Run benchmark suite"
        echo "  ./god.sh doctor      Run diagnostics"
        echo "  ./god.sh help        Show this help"
        echo ""
        echo "Security:"
        echo "  Authentication required for admin endpoints."
        echo "  Create owner: POST /api/auth/setup"
        echo "  Login:        POST /api/auth/login"
        echo ""
        ;;
esac
