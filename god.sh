#!/bin/bash
# GOD — Command helper (Linux/Mac)

GOD_DIR="$(cd "$(dirname "$0")" && pwd)"
PY="$GOD_DIR/.venv/bin/python"

if [ ! -f "$PY" ]; then
    # Fallback to system Python
    if command -v python3 &>/dev/null; then
        PY="python3"
    elif command -v python &>/dev/null; then
        PY="python"
    else
        echo "[FAIL] Python not found. Run ./setup.sh first."
        exit 1
    fi
fi

CMD="${1:-help}"

case "$CMD" in
    start)
        echo "Starting GOD on port 8000..."
        echo "Dashboard: http://localhost:8000"
        echo "API docs:  http://localhost:8000/docs"
        echo "Press Ctrl+C to stop."
        echo ""
        $PY -m uvicorn server:app --host 0.0.0.0 --port 8000
        ;;
    stop)
        echo "Stopping GOD..."
        pkill -f "uvicorn server:app" 2>/dev/null && echo "[OK] Stopped." || echo "[WARN] Not running."
        ;;
    status)
        echo "Checking GOD status..."
        if curl -s http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
            echo "[OK] GOD is running on port 8000."
            curl -s http://127.0.0.1:8000/api/health | $PY -m json.tool 2>/dev/null
        else
            echo "[WARN] GOD is not running. Start with: ./god.sh start"
        fi
        ;;
    test)
        echo "Running tests..."
        $PY -m unittest tests.test_core -v
        ;;
    benchmark)
        echo "Running benchmark..."
        $PY -c "
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
        $PY -c "
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
        echo "  ./god.sh start       Start the server (port 8000)"
        echo "  ./god.sh stop        Stop the server"
        echo "  ./god.sh status      Check if server is running"
        echo "  ./god.sh test        Run test suite"
        echo "  ./god.sh benchmark   Run benchmark suite"
        echo "  ./god.sh doctor      Run diagnostics"
        echo "  ./god.sh help        Show this help"
        echo ""
        ;;
esac
