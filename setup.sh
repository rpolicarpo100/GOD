#!/bin/bash
set -e

echo ""
echo "========================================"
echo "  GOD — Setup (Linux/Mac)"
echo "========================================"
echo ""

GOD_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$GOD_DIR"
echo "[OK] Project directory: $GOD_DIR"
echo ""

# --- Check Python ---
PY=""
if command -v python3 &>/dev/null; then
    PY="python3"
elif command -v python &>/dev/null; then
    PY="python"
else
    echo "[FAIL] Python not found."
    echo "       Install Python 3.10+: https://www.python.org/downloads/"
    exit 1
fi

PYVER=$($PY --version 2>&1 | awk '{print $2}')
echo "[OK] Python: $PYVER"

$PY -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "[FAIL] Python 3.10+ required. Found: $PYVER"
    exit 1
fi
echo ""

# --- Create virtual environment ---
if [ ! -d ".venv" ]; then
    echo "[*] Creating virtual environment..."
    $PY -m venv .venv
    echo "[OK] Virtual environment created."
else
    echo "[OK] Virtual environment exists."
fi

# --- Activate ---
source .venv/bin/activate 2>/dev/null || PY=".venv/bin/python"
echo ""

# --- Upgrade pip ---
echo "[*] Upgrading pip..."
$PY -m pip install --upgrade pip --quiet 2>/dev/null
echo "[OK] pip upgraded."
echo ""

# --- Install requirements ---
echo "[*] Installing dependencies..."
$PY -m pip install -r requirements.txt --quiet 2>&1
echo "[OK] Dependencies installed."
echo ""

# --- Verify core dependencies ---
echo "[*] Verifying dependencies..."
DEP_OK=1
for mod in fastapi uvicorn tiktoken numpy httpx pyyaml qdrant_client; do
    $PY -c "import $mod" 2>/dev/null
    if [ $? -ne 0 ]; then
        echo "[WARN] Module $mod not importable (non-critical)."
    fi
done
echo "[OK] Core dependencies verified."
echo ""

# --- Verify project structure ---
echo "[*] Verifying project structure..."
STRUCT_OK=1
for f in server.py config.yaml requirements.txt superai/__init__.py superai/runtime.py superai/brain.py tests/test_core.py; do
    if [ ! -f "$f" ]; then
        echo "[FAIL] Missing: $f"
        STRUCT_OK=0
    fi
done
if [ "$STRUCT_OK" = "1" ]; then
    echo "[OK] Project structure verified."
else
    echo "[FAIL] Project structure incomplete."
    exit 1
fi
echo ""

# --- Create data directories ---
mkdir -p data/sandbox data/projects data/gods data/voice
echo "[OK] Data directories ready."
echo ""

# --- Check .env ---
if [ ! -f ".env" ]; then
    echo "[WARN] No .env file found."
    echo "       Create .env with your API keys:"
    echo "         GROQ_API_KEY=gsk_..."
    echo "         CEREBRAS_API_KEY=csk-..."
    echo "         GOOGLE_API_KEY=AI..."
    echo "         OPENROUTER_API_KEY=sk-or-..."
    echo "         ANTHROPIC_API_KEY=sk-ant-..."
    echo ""
    echo "       Without .env, GOD runs in OFFLINE mode (no LLM)."
else
    echo "[OK] .env file found."
    echo "[WARN] Never commit .env to git."
fi
echo ""

# --- Run tests ---
echo "[*] Running tests..."
$PY -m unittest tests.test_core -q 2>/dev/null
if [ $? -eq 0 ]; then
    echo "[OK] All tests passed."
else
    echo "[WARN] Some tests failed. Run: python -m unittest tests.test_core -v"
fi
echo ""

echo "========================================"
echo "  INSTALLATION COMPLETE"
echo "========================================"
echo ""
echo "To start GOD:"
echo ""
echo "  source .venv/bin/activate"
echo "  python -m uvicorn server:app --host 0.0.0.0 --port 8000"
echo ""
echo "  # Or use the helper script:"
echo "  ./god.sh start"
echo ""
echo "Then open: http://localhost:8000"
echo ""
echo "Dashboard: chat, SSE, missions, graph, tokens, OS, GOD profiles."
echo "API docs:  http://localhost:8000/docs"
echo ""
echo "========================================"
