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
        echo "GOD Status"
        echo "────────────────────────────────"
        # PID
        if [ -f "$PID_FILE" ]; then
            GOD_PID=$(cat "$PID_FILE" 2>/dev/null)
            if [ -n "$GOD_PID" ] && kill -0 "$GOD_PID" 2>/dev/null; then
                echo "  Process:   alive (PID $GOD_PID)"
            else
                echo "  Process:   dead (stale PID file)"
                rm -f "$PID_FILE"
            fi
        else
            echo "  Process:   no PID file"
        fi
        # Health endpoint
        if curl -s http://127.0.0.1:$GOD_PORT/api/health >/dev/null 2>&1; then
            echo "  Server:    running (port $GOD_PORT)"
            HEALTH=$(curl -s http://127.0.0.1:$GOD_PORT/api/health 2>/dev/null)
            MODE=$(echo "$HEALTH" | $VENV_PY -c "import sys,json; print(json.load(sys.stdin).get('mode','?'))" 2>/dev/null)
            echo "  Mode:      $MODE"
        else
            echo "  Server:    not responding"
        fi
        # Version
        if [ -d "$GOD_DIR/.git" ]; then
            COMMIT=$(cd "$GOD_DIR" && git rev-parse --short HEAD 2>/dev/null)
            echo "  Commit:    $COMMIT"
        fi
        # Manifest
        if [ -f "$GOD_DIR/data/install_manifest.json" ]; then
            PROFILE=$($VENV_PY -c "import json; print(json.load(open('$GOD_DIR/data/install_manifest.json')).get('profile','?'))" 2>/dev/null)
            echo "  Profile:   $PROFILE"
        fi
        # Database
        if [ -f "$GOD_DIR/data/spine.db" ]; then
            DB_SIZE=$(du -sh "$GOD_DIR/data/spine.db" 2>/dev/null | cut -f1)
            echo "  Database:  $DB_SIZE"
        fi
        # Auth
        if [ -f "$GOD_DIR/data/auth/users.json" ]; then
            USERS=$($VENV_PY -c "import json; print(len(json.load(open('$GOD_DIR/data/auth/users.json'))))" 2>/dev/null)
            echo "  Users:     ${USERS:-0}"
        fi
        # Logs
        if [ -f "$LOG_DIR/god.log" ]; then
            LOG_SIZE=$(du -sh "$LOG_DIR/god.log" 2>/dev/null | cut -f1)
            echo "  Logs:      $LOG_SIZE"
        fi
        echo "────────────────────────────────"
        echo "  Dashboard: http://localhost:$GOD_PORT"
        echo ""
        ;;
    repair)
        echo "GOD Repair"
        echo "══════════════════════════════════"
        REPAIRED=0
        FAILED=0
        # 1. Stale PID file
        printf "  [01] Stale PID file.... "
        if [ -f "$PID_FILE" ]; then
            OLD_PID=$(cat "$PID_FILE" 2>/dev/null)
            if [ -n "$OLD_PID" ] && ! kill -0 "$OLD_PID" 2>/dev/null; then
                rm -f "$PID_FILE"
                echo "FIXED  (removed stale PID $OLD_PID)"
                ((REPAIRED++))
            else
                echo "OK"
            fi
        else
            echo "OK"
        fi
        # 2. Data directories
        printf "  [02] Data directories.. "
        MISSING=0
        for d in data data/sandbox data/projects data/gods data/auth data/qdrant data/voice logs backups; do
            if [ ! -d "$GOD_DIR/$d" ]; then
                mkdir -p "$GOD_DIR/$d"
                MISSING=1
            fi
        done
        if [ "$MISSING" = "1" ]; then
            echo "FIXED  (created missing dirs)"
            ((REPAIRED++))
        else
            echo "OK"
        fi
        # 3. Venv integrity
        printf "  [03] Venv integrity.... "
        if [ -f "$VENV_PY" ]; then
            if $VENV_PY -c "import sys" 2>/dev/null; then
                echo "OK"
            else
                echo "FAIL  (venv corrupted — run: rm -rf .venv && ./god-installer.sh)"
                ((FAILED++))
            fi
        else
            echo "WARN  (no venv — run: ./god-installer.sh)"
            ((FAILED++))
        fi
        # 4. Core dependencies
        printf "  [04] Dependencies...... "
        if [ -f "$VENV_PY" ]; then
            DEP_FAIL=0
            for mod in fastapi uvicorn tiktoken numpy httpx pyyaml; do
                $VENV_PY -c "import $mod" 2>/dev/null || DEP_FAIL=1
            done
            if [ "$DEP_FAIL" = "1" ]; then
                echo "REPAIRING..."
                $VENV_PY -m pip install -r requirements.txt --quiet 2>&1
                echo "FIXED  (reinstalled deps)"
                ((REPAIRED++))
            else
                echo "OK"
            fi
        else
            echo "SKIP  (no venv)"
        fi
        # 5. GOD master profile
        printf "  [05] GOD Profile....... "
        if [ ! -f "$GOD_DIR/data/gods/master.json" ]; then
            if [ -f "$VENV_PY" ]; then
                $VENV_PY -c "
from superai import gods
gods.ensure()
print('OK' if gods.get('master') else 'FAIL')
" 2>/dev/null
                echo "FIXED  (created master profile)"
                ((REPAIRED++))
            else
                echo "SKIP"
            fi
        else
            echo "OK"
        fi
        # 6. SQLite integrity
        printf "  [06] SQLite integrity.. "
        if [ -f "$GOD_DIR/data/spine.db" ]; then
            if command -v sqlite3 &>/dev/null; then
                INTEGRITY=$(sqlite3 "$GOD_DIR/data/spine.db" "PRAGMA integrity_check;" 2>/dev/null)
                if [ "$INTEGRITY" = "ok" ]; then
                    echo "OK"
                else
                    echo "FAIL  (database corrupted)"
                    ((FAILED++))
                fi
            else
                echo "OK  (file exists, sqlite3 not available for check)"
            fi
        else
            echo "OK  (will be created on first start)"
        fi
        # 7. WAL cleanup
        printf "  [07] WAL files......... "
        WAL_CLEANED=0
        for wal in "$GOD_DIR/data/spine.db-wal" "$GOD_DIR/data/spine.db-shm"; do
            if [ -f "$wal" ]; then
                SIZE=$(stat -c%s "$wal" 2>/dev/null || stat -f%z "$wal" 2>/dev/null || echo 0)
                if [ "$SIZE" -gt 10485760 ] 2>/dev/null; then
                    rm -f "$wal"
                    WAL_CLEANED=1
                fi
            fi
        done
        if [ "$WAL_CLEANED" = "1" ]; then
            echo "FIXED  (removed oversized WAL)"
            ((REPAIRED++))
        else
            echo "OK"
        fi
        # 8. Audit log rotation
        printf "  [08] Audit log......... "
        if [ -f "$GOD_DIR/data/auth/audit.jsonl" ]; then
            SIZE=$(stat -c%s "$GOD_DIR/data/auth/audit.jsonl" 2>/dev/null || stat -f%z "$GOD_DIR/data/auth/audit.jsonl" 2>/dev/null || echo 0)
            if [ "$SIZE" -gt 2097152 ] 2>/dev/null; then
                LINES=$(wc -l < "$GOD_DIR/data/auth/audit.jsonl" 2>/dev/null)
                if [ "$LINES" -gt 5000 ] 2>/dev/null; then
                    tail -2000 "$GOD_DIR/data/auth/audit.jsonl" > "$GOD_DIR/data/auth/audit.jsonl.tmp"
                    mv "$GOD_DIR/data/auth/audit.jsonl.tmp" "$GOD_DIR/data/auth/audit.jsonl"
                    echo "FIXED  (rotated $LINES → 2000 lines)"
                    ((REPAIRED++))
                else
                    echo "OK"
                fi
            else
                echo "OK"
            fi
        else
            echo "OK  (not found)"
        fi
        # 9. Stale lock files
        printf "  [09] Lock files........ "
        LOCK_CLEANED=0
        for lock in "$GOD_DIR/data/qdrant"/*.lock; do
            if [ -f "$lock" ]; then
                # Check if the PID in the lock file is alive
                LOCK_PID=$(cat "$lock" 2>/dev/null | head -1)
                if [ -n "$LOCK_PID" ] && ! kill -0 "$LOCK_PID" 2>/dev/null; then
                    rm -f "$lock"
                    LOCK_CLEANED=1
                fi
            fi
        done
        if [ "$LOCK_CLEANED" = "1" ]; then
            echo "FIXED  (removed stale locks)"
            ((REPAIRED++))
        else
            echo "OK"
        fi
        # 10. Disk space
        printf "  [10] Disk space........ "
        DISK_AVAIL=$(df -BM "$GOD_DIR" 2>/dev/null | tail -1 | awk '{print $4}' | tr -d 'M')
        if [ -n "$DISK_AVAIL" ] && [ "$DISK_AVAIL" -lt 100 ] 2>/dev/null; then
            echo "WARN  (${DISK_AVAIL}MB free — consider cleanup)"
            ((FAILED++))
        else
            echo "OK  (${DISK_AVAIL:-?}MB free)"
        fi
        # 11. Backend repair (compute, queue, qdrant, gods)
        printf "  [11] Backend repair.... "
        if [ -f "$VENV_PY" ]; then
            REPAIR_OUT=$($VENV_PY -c "
from superai import repair
r = repair.run()
ok = r.get('ok', False)
actions = r.get('actions', [])
fixed = sum(1 for a in actions if a.get('ok'))
total = len(actions)
print(f'{fixed}/{total} ok')
" 2>/dev/null)
            if [ -n "$REPAIR_OUT" ]; then
                echo "PASS  ($REPAIR_OUT)"
            else
                echo "SKIP  (backend unavailable)"
            fi
        else
            echo "SKIP  (no venv)"
        fi
        echo "══════════════════════════════════"
        echo "  Repaired: $REPAIRED | Failed: $FAILED"
        if [ "$FAILED" -gt 0 ]; then
            echo "  Some issues require manual intervention."
        elif [ "$REPAIRED" -gt 0 ]; then
            echo "  All fixable issues repaired."
        else
            echo "  No issues found."
        fi
        echo ""
        ;;

    backup)
        BACKUP_TS=$(date +%Y-%m-%d_%H-%M-%S)
        BACKUP_DIR="$GOD_DIR/backups/$BACKUP_TS"
        mkdir -p "$BACKUP_DIR"
        echo "GOD Backup"
        echo "══════════════════════════════════"
        echo "  Target: $BACKUP_DIR"
        echo ""
        TOTAL_SIZE=0
        # Backup config
        printf "  .env.............. "
        if [ -f "$GOD_DIR/.env" ]; then
            cp "$GOD_DIR/.env" "$BACKUP_DIR/.env"
            echo "OK"
        else
            echo "SKIP (not found)"
        fi
        printf "  config.yaml....... "
        if [ -f "$GOD_DIR/config.yaml" ]; then
            cp "$GOD_DIR/config.yaml" "$BACKUP_DIR/config.yaml"
            echo "OK"
        else
            echo "SKIP"
        fi
        # Backup auth
        printf "  data/auth/........ "
        if [ -d "$GOD_DIR/data/auth" ]; then
            mkdir -p "$BACKUP_DIR/data/auth"
            cp -r "$GOD_DIR/data/auth"/* "$BACKUP_DIR/data/auth/" 2>/dev/null
            AUTH_SIZE=$(du -sh "$BACKUP_DIR/data/auth" 2>/dev/null | cut -f1)
            echo "OK  ($AUTH_SIZE)"
        else
            echo "SKIP"
        fi
        # Backup gods
        printf "  data/gods/........ "
        if [ -d "$GOD_DIR/data/gods" ]; then
            mkdir -p "$BACKUP_DIR/data/gods"
            cp -r "$GOD_DIR/data/gods"/* "$BACKUP_DIR/data/gods/" 2>/dev/null
            echo "OK"
        else
            echo "SKIP"
        fi
        # Backup database
        printf "  data/spine.db..... "
        if [ -f "$GOD_DIR/data/spine.db" ]; then
            cp "$GOD_DIR/data/spine.db" "$BACKUP_DIR/data/"
            DB_SIZE=$(du -sh "$GOD_DIR/data/spine.db" 2>/dev/null | cut -f1)
            echo "OK  ($DB_SIZE)"
        else
            echo "SKIP"
        fi
        # Backup manifest
        printf "  manifest.json..... "
        cat > "$BACKUP_DIR/manifest.json" << EOF
{
  "timestamp": "$(date -Iseconds)",
  "commit": "$(cd "$GOD_DIR" && git rev-parse --short HEAD 2>/dev/null || echo 'unknown')",
  "port": $GOD_PORT,
  "python": "$($VENV_PY --version 2>&1 | awk '{print $2}' 2>/dev/null || echo 'unknown')",
  "backup_type": "manual",
  "contents": [".env", "config.yaml", "data/auth", "data/gods", "data/spine.db"]
}
EOF
        echo "OK"
        echo ""
        BACKUP_SIZE=$(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1)
        echo "══════════════════════════════════"
        echo "  Backup: $BACKUP_SIZE"
        echo "  Path:   $BACKUP_DIR"
        # Rotation: keep last 10 backups
        BACKUP_COUNT=$(ls -d "$GOD_DIR/backups"/*/ 2>/dev/null | wc -l)
        if [ "$BACKUP_COUNT" -gt 10 ]; then
            REMOVE_COUNT=$((BACKUP_COUNT - 10))
            ls -d "$GOD_DIR/backups"/*/ 2>/dev/null | head -n "$REMOVE_COUNT" | while read OLD; do
                rm -rf "$OLD"
            done
            echo "  Rotated: removed $REMOVE_COUNT old backup(s)"
        fi
        echo ""
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
        echo "GOD Doctor — Diagnostics"
        echo "══════════════════════════════════"
        ERRORS=0
        WARNS=0
        # 1. Python
        printf "  [01] Python............. "
        if [ -f "$VENV_PY" ]; then
            PYVER=$($VENV_PY --version 2>&1 | awk '{print $2}')
            echo "PASS  $PYVER"
        else
            echo "FAIL  venv not found"
            ((ERRORS++))
        fi
        # 2. Dependencies
        printf "  [02] Dependencies...... "
        DEP_FAIL=0
        for mod in fastapi uvicorn tiktoken numpy httpx pyyaml qdrant_client; do
            $VENV_PY -c "import $mod" 2>/dev/null || DEP_FAIL=1
        done
        if [ "$DEP_FAIL" = "0" ]; then
            echo "PASS"
        else
            echo "WARN  some imports failed"
            ((WARNS++))
        fi
        # 3. Config
        printf "  [03] Configuration..... "
        if [ -f "$GOD_DIR/.env" ]; then
            KEYS=$(grep -c "_API_KEY=." "$GOD_DIR/.env" 2>/dev/null || echo 0)
            echo "PASS  ($KEYS keys configured)"
        else
            echo "WARN  no .env file (offline mode)"
            ((WARNS++))
        fi
        # 4. Database
        printf "  [04] Database.......... "
        if [ -f "$GOD_DIR/data/spine.db" ]; then
            DB_SIZE=$(du -sh "$GOD_DIR/data/spine.db" 2>/dev/null | cut -f1)
            echo "PASS  ($DB_SIZE)"
        else
            echo "WARN  not found (will be created)"
            ((WARNS++))
        fi
        # 5. Auth
        printf "  [05] Auth.............. "
        if [ -f "$GOD_DIR/data/auth/users.json" ]; then
            echo "PASS"
        else
            echo "WARN  no users (setup via /api/auth/setup)"
            ((WARNS++))
        fi
        # 6. GOD profile
        printf "  [06] GOD Profile....... "
        if [ -f "$GOD_DIR/data/gods/master.json" ]; then
            echo "PASS  (master)"
        else
            echo "WARN  no master profile (will be created)"
            ((WARNS++))
        fi
        # 7. Server process
        printf "  [07] Server Process.... "
        if [ -f "$PID_FILE" ]; then
            GOD_PID=$(cat "$PID_FILE" 2>/dev/null)
            if [ -n "$GOD_PID" ] && kill -0 "$GOD_PID" 2>/dev/null; then
                echo "PASS  (PID $GOD_PID)"
            else
                echo "WARN  stale PID file"
                ((WARNS++))
            fi
        else
            echo "INFO  not running"
        fi
        # 8. Port
        printf "  [08] Port $GOD_PORT............. "
        if ss -tlnp 2>/dev/null | grep -q ":$GOD_PORT " || netstat -tlnp 2>/dev/null | grep -q ":$GOD_PORT "; then
            echo "PASS  (listening)"
        else
            echo "INFO  not listening"
        fi
        # 9. Disk
        printf "  [09] Disk Space........ "
        DISK_AVAIL=$(df -BM "$GOD_DIR" 2>/dev/null | tail -1 | awk '{print $4}' | tr -d 'M')
        if [ -n "$DISK_AVAIL" ] && [ "$DISK_AVAIL" -gt 100 ] 2>/dev/null; then
            echo "PASS  (${DISK_AVAIL}MB free)"
        else
            echo "WARN  low disk space"
            ((WARNS++))
        fi
        # 10. Audit log
        printf "  [10] Audit Log......... "
        if [ -f "$GOD_DIR/data/auth/audit.jsonl" ]; then
            LINES=$(wc -l < "$GOD_DIR/data/auth/audit.jsonl" 2>/dev/null)
            SIZE=$(du -sh "$GOD_DIR/data/auth/audit.jsonl" 2>/dev/null | cut -f1)
            echo "PASS  ($LINES entries, $SIZE)"
        else
            echo "INFO  not found"
        fi
        # 11. Qdrant
        printf "  [11] Vector DB......... "
        if [ -d "$GOD_DIR/data/qdrant" ]; then
            echo "PASS"
        else
            echo "WARN  data/qdrant not found"
            ((WARNS++))
        fi
        # 12. Logs directory
        printf "  [12] Logs.............. "
        if [ -d "$LOG_DIR" ]; then
            LOG_COUNT=$(find "$LOG_DIR" -name "*.log" 2>/dev/null | wc -l)
            echo "PASS  ($LOG_COUNT log files)"
        else
            echo "INFO  no logs directory"
        fi
        echo "══════════════════════════════════"
        if [ "$ERRORS" -gt 0 ]; then
            echo "  Result: $ERRORS error(s), $WARNS warning(s)"
            echo "  Run: ./god.sh repair"
        elif [ "$WARNS" -gt 0 ]; then
            echo "  Result: $WARNS warning(s), 0 errors"
        else
            echo "  Result: ALL CHECKS PASSED"
        fi
        echo ""
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
        echo "GOD Update"
        echo "══════════════════════════════════"
        # Check git
        if [ ! -d "$GOD_DIR/.git" ]; then
            echo "  [FAIL] Not a git repository."
            echo "         Manual update required."
            exit 1
        fi
        # Current state
        OLD_COMMIT=$(cd "$GOD_DIR" && git rev-parse --short HEAD 2>/dev/null)
        echo "  Current: $OLD_COMMIT"
        # Fetch
        printf "  Fetching... "
        cd "$GOD_DIR" && git fetch 2>/dev/null
        echo "OK"
        # Check for updates
        LOCAL=$(cd "$GOD_DIR" && git rev-parse HEAD 2>/dev/null)
        REMOTE=$(cd "$GOD_DIR" && git rev-parse @{u} 2>/dev/null)
        if [ "$LOCAL" = "$REMOTE" ]; then
            echo "  Status:  Already up to date."
            echo ""
            # Still update deps
            printf "  Dependencies... "
            $VENV_PY -m pip install -r requirements.txt --quiet 2>&1
            echo "OK"
            echo ""
            echo "══════════════════════════════════"
            echo "  No updates available."
            echo ""
            exit 0
        fi
        # Show what changed
        echo ""
        echo "  Changes available:"
        cd "$GOD_DIR" && git log --oneline "$LOCAL..$REMOTE" 2>/dev/null | head -10
        echo ""
        # Check for local changes
        CHANGES=$(cd "$GOD_DIR" && git status --porcelain 2>/dev/null | wc -l)
        if [ "$CHANGES" -gt 0 ]; then
            echo "  [WARN] $CHANGES local file(s) modified:"
            cd "$GOD_DIR" && git status --short | head -10
            echo ""
            read -p "  Continue? Local changes will be preserved (stash). (y/N) " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                echo "  Cancelled."
                exit 0
            fi
            # Stash local changes
            printf "  Stashing local changes... "
            cd "$GOD_DIR" && git stash push -m "god-update-$(date +%s)" 2>/dev/null
            echo "OK"
        fi
        # Pre-update backup
        printf "  Pre-update backup... "
        $0 backup 2>/dev/null | tail -1
        # Pull
        printf "  Pulling updates... "
        cd "$GOD_DIR" && git pull 2>&1 | tail -1
        NEW_COMMIT=$(cd "$GOD_DIR" && git rev-parse --short HEAD 2>/dev/null)
        # Update deps
        printf "  Dependencies... "
        $VENV_PY -m pip install -r requirements.txt --quiet 2>&1
        echo "OK"
        # Run tests
        printf "  Tests... "
        TEST_OUT=$($VENV_PY -m pytest tests/ -q 2>/dev/null)
        TEST_RC=$?
        if [ "$TEST_RC" -eq 0 ]; then
            echo "PASS  ($TEST_OUT | tail -1)"
        else
            echo "FAIL"
            echo ""
            echo "  [WARN] Tests failed after update."
            echo "  Rolling back to $OLD_COMMIT..."
            cd "$GOD_DIR" && git checkout "$OLD_COMMIT" 2>/dev/null
            $VENV_PY -m pip install -r requirements.txt --quiet 2>&1
            echo "  Rolled back to $OLD_COMMIT."
            echo "  Check log and fix manually."
            exit 5
        fi
        echo ""
        echo "══════════════════════════════════"
        echo "  Updated: $OLD_COMMIT → $NEW_COMMIT"
        echo "  Tests:   PASS"
        if [ "$CHANGES" -gt 0 ]; then
            echo "  Local:   stashed (run: git stash pop)"
        fi
        echo ""
        ;;
    uninstall)
        echo ""
        echo "GOD — Uninstall"
        echo "══════════════════════════════════"
        echo ""
        # Show what exists
        echo "  Current installation:"
        [ -d "$GOD_DIR/.venv" ]          && echo "    .venv/           $(du -sh "$GOD_DIR/.venv" 2>/dev/null | cut -f1)"
        [ -d "$GOD_DIR/data" ]           && echo "    data/            $(du -sh "$GOD_DIR/data" 2>/dev/null | cut -f1)"
        [ -d "$GOD_DIR/data/qdrant" ]    && echo "      data/qdrant/   $(du -sh "$GOD_DIR/data/qdrant" 2>/dev/null | cut -f1)"
        [ -d "$GOD_DIR/data/sandbox" ]   && echo "      data/sandbox/  $(du -sh "$GOD_DIR/data/sandbox" 2>/dev/null | cut -f1)"
        [ -f "$GOD_DIR/data/spine.db" ]  && echo "      data/spine.db  $(du -sh "$GOD_DIR/data/spine.db" 2>/dev/null | cut -f1)"
        [ -d "$GOD_DIR/data/auth" ]      && echo "      data/auth/     $(du -sh "$GOD_DIR/data/auth" 2>/dev/null | cut -f1)"
        [ -d "$GOD_DIR/data/gods" ]      && echo "      data/gods/     $(du -sh "$GOD_DIR/data/gods" 2>/dev/null | cut -f1)"
        [ -d "$GOD_DIR/logs" ]           && echo "    logs/            $(du -sh "$GOD_DIR/logs" 2>/dev/null | cut -f1)"
        [ -d "$GOD_DIR/backups" ]        && echo "    backups/         $(du -sh "$GOD_DIR/backups" 2>/dev/null | cut -f1)"
        [ -f "$GOD_DIR/.env" ]           && echo "    .env             (API keys)"
        [ -f "$GOD_DIR/config.yaml" ]    && echo "    config.yaml"
        echo ""
        echo "  Options:"
        echo ""
        echo "  [1] Remove application only"
        echo "      Keeps: data/, .env, config.yaml, backups/"
        echo "      Remove: .venv/, __pycache__/, god.pid"
        echo ""
        echo "  [2] Remove application + cache"
        echo "      Keeps: data/spine.db, data/auth/, data/gods/, .env, config.yaml"
        echo "      Remove: .venv/, data/qdrant/, data/sandbox/, __pycache__/"
        echo ""
        echo "  [3] Remove application + cache + logs"
        echo "      Keeps: data/spine.db, data/auth/, data/gods/, .env"
        echo "      Remove: .venv/, data/qdrant/, data/sandbox/, logs/"
        echo ""
        echo "  [4] Backup then remove everything"
        echo "      Creates backup first, then removes all GOD files."
        echo ""
        echo "  [0] Cancel"
        echo ""
        read -p "  Choose: " CHOICE
        case "$CHOICE" in
            1)
                echo ""
                $0 stop 2>/dev/null || true
                REMOVED=0
                printf "  Removing .venv/... "
                if [ -d "$GOD_DIR/.venv" ]; then
                    rm -rf "$GOD_DIR/.venv"
                    echo "OK"
                    ((REMOVED++))
                else
                    echo "SKIP (not found)"
                fi
                printf "  Removing PID file... "
                rm -f "$GOD_DIR/data/god.pid"
                echo "OK"
                printf "  Removing __pycache__/... "
                find "$GOD_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
                echo "OK"
                echo ""
                echo "══════════════════════════════════"
                echo "  Application removed."
                echo "  Data preserved in: $GOD_DIR"
                echo "  To fully remove:   rm -rf $GOD_DIR"
                echo ""
                ;;
            2)
                echo ""
                $0 stop 2>/dev/null || true
                printf "  Removing .venv/... "
                rm -rf "$GOD_DIR/.venv" && echo "OK" || echo "SKIP"
                printf "  Removing data/qdrant/... "
                rm -rf "$GOD_DIR/data/qdrant" && echo "OK" || echo "SKIP"
                printf "  Removing data/sandbox/... "
                rm -rf "$GOD_DIR/data/sandbox" && echo "OK" || echo "SKIP"
                printf "  Removing __pycache__/... "
                find "$GOD_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
                echo "OK"
                rm -f "$GOD_DIR/data/god.pid"
                echo ""
                echo "══════════════════════════════════"
                echo "  Application + cache removed."
                echo "  Preserved: data/spine.db, data/auth/, data/gods/, .env"
                echo ""
                ;;
            3)
                echo ""
                $0 stop 2>/dev/null || true
                printf "  Removing .venv/... "
                rm -rf "$GOD_DIR/.venv" && echo "OK" || echo "SKIP"
                printf "  Removing data/qdrant/... "
                rm -rf "$GOD_DIR/data/qdrant" && echo "OK" || echo "SKIP"
                printf "  Removing data/sandbox/... "
                rm -rf "$GOD_DIR/data/sandbox" && echo "OK" || echo "SKIP"
                printf "  Removing logs/... "
                rm -rf "$GOD_DIR/logs" && echo "OK" || echo "SKIP"
                printf "  Removing __pycache__/... "
                find "$GOD_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
                echo "OK"
                rm -f "$GOD_DIR/data/god.pid"
                echo ""
                echo "══════════════════════════════════"
                echo "  Removed application + cache + logs."
                echo "  Preserved: data/spine.db, data/auth/, data/gods/, .env"
                echo ""
                ;;
            4)
                echo ""
                $0 backup
                echo ""
                read -p "  Remove everything? Type DELETE to confirm: " CONFIRM
                if [ "$CONFIRM" = "DELETE" ]; then
                    $0 stop 2>/dev/null || true
                    rm -rf "$GOD_DIR/.venv"
                    rm -rf "$GOD_DIR/data"
                    rm -rf "$GOD_DIR/logs"
                    rm -f "$GOD_DIR/.env"
                    rm -f "$GOD_DIR/config.yaml"
                    rm -f "$GOD_DIR/data/god.pid"
                    echo ""
                    echo "══════════════════════════════════"
                    echo "  Everything removed."
                    echo "  Backup preserved in: $GOD_DIR/backups/"
                    echo ""
                else
                    echo "  Cancelled. Backup preserved."
                fi
                ;;
            *)
                echo "  Cancelled."
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
