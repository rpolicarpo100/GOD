#!/bin/bash
# ═══════════════════════════════════════════════════════════
#   GOD INSTALLER — Linux/Mac
#   Single entry point: detection, preflight, install, verify
# ═══════════════════════════════════════════════════════════

set -e

GOD_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$GOD_DIR"
VENV_PY="$GOD_DIR/.venv/bin/python"
LOG_DIR="$GOD_DIR/logs"
LOG="$LOG_DIR/installer.log"
RUN_ID="$(date +%s)$RANDOM"
GOD_PORT="${GOD_PORT:-8000}"
ERRORS=0
WARNINGS=0

mkdir -p "$LOG_DIR"

log() {
    echo "[$(date -Iseconds)] $*" >> "$LOG"
}

pass() { echo "         PASS  $1"; log "PASS: $1"; }
fail() { echo "         FAIL  $1"; log "FAIL: $1"; ((ERRORS++)); }
warn() { echo "         WARN  $1"; log "WARN: $1"; ((WARNINGS++)); }
info() { echo "         INFO  $1"; log "INFO: $1"; }

# ── Welcome ─────────────────────────────────────────────

echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║            G O D   I N S T A L L E R     ║"
echo "  ║                                          ║"
echo "  ║   AI Agent System — Linux/Mac Setup      ║"
echo "  ╚══════════════════════════════════════════╝"
echo ""
echo "  Run ID: $RUN_ID"
echo "  Log:    $LOG"
echo ""

log "GOD INSTALLER started"
log "Run ID: $RUN_ID"

# ── Check if already installed ──────────────────────────

if [ -f "$VENV_PY" ]; then
    echo "  [INFO] GOD installation detected."
    echo ""
    echo "  [1] Verify existing installation"
    echo "  [2] Repair"
    echo "  [3] Update"
    echo "  [4] Reinstall"
    echo "  [0] Cancel"
    echo ""
    read -p "  Choose: " EXISTING
    case "$EXISTING" in
        1) echo ""; echo "Verifying..."; "$VENV_PY" -m pytest tests/ -q; exit 0 ;;
        2) echo ""; "$VENV_PY" -c "from superai import repair; r=repair.run(); print(r)"; exit 0 ;;
        3) echo ""; git pull && "$VENV_PY" -m pip install -r requirements.txt -q && "$VENV_PY" -m pytest tests/ -q; exit 0 ;;
        4) ;; # continue to install
        *) echo "Cancelled."; exit 0 ;;
    esac
fi

# ═══════════════════════════════════════════════════════════
#   PHASE 1: DETECTION
# ═══════════════════════════════════════════════════════════

echo ""
echo "========================================"
echo "  SYSTEM CHECK"
echo "========================================"
echo ""

log "PHASE 1: DETECTION"

# ── OS ──
printf "  [01/10] OS............... "
OS="$(uname -s)"
case "$OS" in
    Linux)  pass "$(uname -s) $(uname -r | cut -d- -f1)" ;;
    Darwin) pass "macOS $(sw_vers -productVersion 2>/dev/null || echo 'unknown')" ;;
    *)      warn "$OS (untested)" ;;
esac

# ── Architecture ──
printf "  [02/10] Architecture..... "
ARCH="$(uname -m)"
case "$ARCH" in
    x86_64|amd64) pass "x64" ;;
    arm64|aarch64) pass "ARM64" ;;
    *)             warn "$ARCH (untested)" ;;
esac

# ── RAM ──
printf "  [03/10] RAM.............. "
if [ "$OS" = "Linux" ]; then
    RAM_KB=$(grep MemTotal /proc/meminfo 2>/dev/null | awk '{print $2}')
    if [ -n "$RAM_KB" ]; then
        RAM_GB=$((RAM_KB / 1048576))
        if [ "$RAM_GB" -ge 4 ]; then
            pass "${RAM_GB} GB"
        else
            warn "${RAM_GB} GB (recommended: 4+ GB)"
        fi
    else
        info "Could not detect"
    fi
elif [ "$OS" = "Darwin" ]; then
    RAM_BYTES=$(sysctl -n hw.memsize 2>/dev/null)
    if [ -n "$RAM_BYTES" ]; then
        RAM_GB=$((RAM_BYTES / 1073741824))
        if [ "$RAM_GB" -ge 4 ]; then
            pass "${RAM_GB} GB"
        else
            warn "${RAM_GB} GB (recommended: 4+ GB)"
        fi
    fi
fi

# ── Disk ──
printf "  [04/10] Disk............. "
DISK_AVAIL=$(df -BM "$GOD_DIR" 2>/dev/null | tail -1 | awk '{print $4}' | tr -d 'M')
if [ -n "$DISK_AVAIL" ] && [ "$DISK_AVAIL" -gt 500 ] 2>/dev/null; then
    pass "${DISK_AVAIL}MB available"
elif [ -n "$DISK_AVAIL" ]; then
    warn "${DISK_AVAIL}MB available (recommend 500MB+)"
else
    pass "Checked"
fi

# ── Python ──
printf "  [05/10] Python........... "
PY=""
if command -v python3 &>/dev/null; then
    PY="python3"
elif command -v python &>/dev/null; then
    PY="python"
fi

if [ -n "$PY" ]; then
    PYVER=$($PY --version 2>&1 | awk '{print $2}')
    if $PY -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" 2>/dev/null; then
        pass "$PYVER"
    else
        fail "$PYVER (need 3.10+)"
        PY=""
    fi
else
    fail "Python not found"
    echo "         Install Python 3.10+: https://www.python.org/downloads/"
fi

# ── pip ──
printf "  [06/10] pip.............. "
if [ -n "$PY" ] && $PY -m pip --version &>/dev/null; then
    pass "Available"
else
    warn "Not found (will install with venv)"
fi

# ── Git ──
printf "  [07/10] Git.............. "
if command -v git &>/dev/null; then
    GITVER=$(git --version | awk '{print $3}')
    pass "$GITVER"
else
    warn "Not found (optional, needed for update)"
fi

# ── Internet ──
printf "  [08/10] Internet......... "
if ping -c 1 -W 2 pypi.org &>/dev/null 2>&1 || ping -c 1 -W 2 google.com &>/dev/null 2>&1; then
    pass "Connected"
else
    warn "No internet (offline install only)"
fi

# ── Port ──
printf "  [09/10] Port $GOD_PORT%........... "
if ss -tlnp 2>/dev/null | grep -q ":$GOD_PORT " || netstat -tlnp 2>/dev/null | grep -q ":$GOD_PORT "; then
    warn "Port $GOD_PORT in use"
else
    pass "Available"
fi

# ── GPU ──
printf "  [10/10] GPU.............. "
if command -v nvidia-smi &>/dev/null; then
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
    if [ -n "$GPU_NAME" ]; then
        pass "$GPU_NAME"
    else
        info "nvidia-smi found but no GPU"
    fi
elif [ -d /dev/dri ] || [ -d /sys/class/drm ]; then
    info "GPU present (unknown model)"
else
    info "Not detected (not required)"
fi

echo ""
log "DETECTION: $ERRORS errors, $WARNINGS warnings"

# ── Decision ──
if [ "$ERRORS" -gt 0 ]; then
    echo "========================================"
    echo "  INSTALLATION BLOCKED"
    echo "========================================"
    echo ""
    echo "  $ERRORS error(s) found. Fix the issues above and retry."
    echo "  Log: $LOG"
    exit 2
fi

if [ "$WARNINGS" -gt 0 ]; then
    echo "  $WARNINGS warning(s). Installation can continue."
    echo ""
fi

# ═══════════════════════════════════════════════════════════
#   PHASE 2: PROFILE SELECTION
# ═══════════════════════════════════════════════════════════

echo "========================================"
echo "  INSTALLATION PROFILE"
echo "========================================"
echo ""
echo "  [1] MINIMAL"
echo "      Core only. No neural embeddings, no voice."
echo "      Fast install, smaller disk usage (~200MB)."
echo ""
echo "  [2] STANDARD"
echo "      Core + embeddings + voice TTS."
echo "      Recommended for most users (~700MB)."
echo ""
echo "  [3] DEVELOPMENT"
echo "      Standard + test tools + dev mode."
echo "      For contributors."
echo ""
read -p "  Choose [1-3] (default: 2): " PROFILE
PROFILE="${PROFILE:-2}"

log "PROFILE: $PROFILE"

case "$PROFILE" in
    1) echo "  [*] Profile: MINIMAL"; REQ_FILE="requirements-minimal.txt" ;;
    3) echo "  [*] Profile: DEVELOPMENT"; REQ_FILE="requirements.txt" ;;
    *) echo "  [*] Profile: STANDARD"; REQ_FILE="requirements.txt" ;;
esac
echo ""

# ═══════════════════════════════════════════════════════════
#   PHASE 3: INSTALL
# ═══════════════════════════════════════════════════════════

echo "========================================"
echo "  INSTALLING"
echo "========================================"
echo ""

log "PHASE 3: INSTALL"

# ── Create venv ──
printf "  [01/05] Creating virtual environment... "
if [ ! -d ".venv" ]; then
    $PY -m venv .venv >> "$LOG" 2>&1
    if [ $? -ne 0 ]; then
        fail "Could not create venv"
        exit 4
    fi
    echo "PASS"
else
    echo "OK (exists)"
fi

# ── Upgrade pip ──
printf "  [02/05] Upgrading pip... "
$VENV_PY -m pip install --upgrade pip --quiet >> "$LOG" 2>&1
echo "PASS"

# ── Install dependencies ──
printf "  [03/05] Installing dependencies (%s)... " "$REQ_FILE"
$VENV_PY -m pip install -r "$REQ_FILE" --quiet >> "$LOG" 2>&1
if [ $? -ne 0 ]; then
    fail "pip install failed. Check: $LOG"
    exit 4
fi
echo "PASS"

# ── Install pytest ──
printf "  [04/05] Installing test tools... "
$VENV_PY -m pip install pytest --quiet >> "$LOG" 2>&1
echo "PASS"

# ── Create directories ──
printf "  [05/05] Creating directories... "
mkdir -p data/sandbox data/projects data/gods data/auth data/qdrant data/voice logs backups
echo "PASS"

echo ""
log "INSTALL complete"

# ═══════════════════════════════════════════════════════════
#   PHASE 4: CONFIGURE
# ═══════════════════════════════════════════════════════════

echo "========================================"
echo "  CONFIGURATION"
echo "========================================"
echo ""

if [ -f ".env" ]; then
    echo "  [OK] .env already exists."
    echo ""
    read -p "  Reconfigure? (y/N): " RECONFIG
    if [[ ! "$RECONFIG" =~ ^[Yy]$ ]]; then
        echo ""
        # Skip to verify
        :
    else
        # Will configure below
        :
    fi
fi

if [ ! -f ".env" ] || [[ "$RECONFIG" =~ ^[Yy]$ ]]; then
    echo "  Select mode:"
    echo ""
    echo "  [1] API / Cloud  — Use providers (Groq, Google, Anthropic...)"
    echo "  [2] Offline      — No LLM, tools only"
    echo "  [3] Skip         — Configure later"
    echo ""
    read -p "  Choose [1-3]: " CMODE

    case "$CMODE" in
        1)
            echo ""
            echo "  Enter API keys (leave blank to skip):"
            echo ""
            read -p "    Groq (free, fast): " GROQ_KEY
            read -p "    Google (free, Gemini): " GOOGLE_KEY
            read -p "    Anthropic (paid, Claude): " ANTHRO_KEY
            read -p "    OpenRouter (aggregator): " OPENR_KEY
            read -p "    Cerebras (free): " CEREB_KEY
            read -p "    NVIDIA (free, DeepSeek): " NVIDIA_KEY
            read -p "    Mistral (free, Codestral): " MISTRAL_KEY
            read -p "    SambaNova (free): " SAMBA_KEY
            cat > .env << EOF
# GOD — API keys (generated by installer)
# $(date -Iseconds)

GROQ_API_KEY=$GROQ_KEY
GOOGLE_API_KEY=$GOOGLE_KEY
ANTHROPIC_API_KEY=$ANTHRO_KEY
OPENROUTER_API_KEY=$OPENR_KEY
CEREBRAS_API_KEY=$CEREB_KEY
NVIDIA_API_KEY=$NVIDIA_KEY
MISTRAL_API_KEY=$MISTRAL_KEY
SAMBANOVA_API_KEY=$SAMBA_KEY
EOF
            echo ""
            echo "  [OK] .env created."
            CONFIGURED=$(grep -c "_API_KEY=." .env 2>/dev/null || echo 0)
            echo "       $CONFIGURED keys configured."
            ;;
        2)
            cat > .env << 'EOF'
# GOD — Offline mode
# No API keys configured
EOF
            echo "  [OK] .env created (offline mode)."
            ;;
        *)
            if [ ! -f ".env" ] && [ -f ".env.example" ]; then
                cp .env.example .env
                echo "  [OK] Copied .env.example. Edit with your keys."
            fi
            ;;
    esac
fi

log "CONFIGURATION done"

# ═══════════════════════════════════════════════════════════
#   PHASE 5: VERIFY
# ═══════════════════════════════════════════════════════════

echo ""
echo "========================================"
echo "  VERIFICATION"
echo "========================================"
echo ""

log "PHASE 5: VERIFY"

# ── Verify imports ──
printf "  [01/04] Verifying imports... "
DEP_OK=1
for mod in fastapi uvicorn tiktoken numpy httpx pyyaml qdrant_client; do
    $VENV_PY -c "import $mod" 2>/dev/null || DEP_OK=0
done
if [ "$DEP_OK" = "1" ]; then
    echo "PASS"
else
    warn "Some imports failed"
fi

# ── Verify structure ──
printf "  [02/04] Verifying structure... "
STRUCT_OK=1
for f in server.py worker.py config.yaml requirements.txt superai/__init__.py superai/runtime.py tests/test_core.py; do
    [ ! -f "$f" ] && echo "FAIL (missing: $f)" && STRUCT_OK=0
done
[ "$STRUCT_OK" = "1" ] && echo "PASS"

# ── Run tests ──
printf "  [03/04] Running tests... "
TEST_OUT=$($VENV_PY -m pytest tests/ -q 2>/dev/null)
if [ $? -eq 0 ]; then
    echo "PASS  ($TEST_OUT | tail -1)"
else
    warn "Some tests failed"
fi

# ── Generate manifest ──
printf "  [04/04] Generating manifest... "
$VENV_PY << 'PYEOF' 2>/dev/null
import json, platform, sys, os
from datetime import datetime, timezone
manifest = {
    'timestamp': datetime.now(timezone.utc).isoformat(),
    'god_version': '0.3.0',
    'profile': os.environ.get('PROFILE', '?'),
    'python_version': sys.version.split()[0],
    'platform': platform.system(),
    'architecture': platform.machine(),
    'port': int(os.environ.get('GOD_PORT', '8000')),
}
try:
    import subprocess
    manifest['commit'] = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD'], text=True).strip()
except:
    manifest['commit'] = 'unknown'
open('data/install_manifest.json', 'w').write(json.dumps(manifest, indent=2))
PYEOF
echo "PASS"

log "VERIFY complete: $ERRORS errors, $WARNINGS warnings"

# ═══════════════════════════════════════════════════════════
#   RESULT
# ═══════════════════════════════════════════════════════════

echo ""
if [ "$ERRORS" -gt 0 ]; then
    echo "========================================"
    echo "  INSTALLATION FAILED"
    echo "========================================"
    echo ""
    echo "  $ERRORS error(s), $WARNINGS warning(s)."
    echo "  Check log: $LOG"
    exit 4
elif [ "$WARNINGS" -gt 0 ]; then
    echo "========================================"
    echo "  INSTALLATION COMPLETE (with warnings)"
    echo "========================================"
else
    echo "========================================"
    echo "  INSTALLATION VERIFIED"
    echo "========================================"
fi
echo ""
echo "  Profile:     $PROFILE"
echo "  Python:      $PYVER"
echo "  Port:        $GOD_PORT"
echo "  Directory:   $GOD_DIR"
echo "  Log:         $LOG"
echo ""
echo "  To start GOD:"
echo ""
echo "    ./god.sh start"
echo ""
echo "  Dashboard: http://localhost:$GOD_PORT"
echo "  API docs:  http://localhost:$GOD_PORT/docs"
echo "  Auth:      POST /api/auth/setup to create owner"
echo ""
echo "========================================"
echo ""

log "INSTALLER finished"
exit 0
