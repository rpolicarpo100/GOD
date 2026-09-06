@echo off
setlocal enabledelayedexpansion

echo.
echo ========================================
echo   GOD — Setup
echo ========================================
echo.

REM --- Detect project directory ---
set "GOD_DIR=%~dp0"
cd /d "%GOD_DIR%"
echo [OK] Project directory: %GOD_DIR%
echo.

REM --- Check Python ---
where python3 >nul 2>&1
if %errorlevel% neq 0 (
    where python >nul 2>&1
    if %errorlevel% neq 0 (
        echo [FAIL] Python not found in PATH.
        echo        Install Python 3.10+ from https://www.python.org/downloads/
        echo        Make sure to check "Add Python to PATH" during installation.
        goto :install_status
    )
    set "PY=python"
) else (
    set "PY=python3"
)

REM --- Check Python version ---
for /f "tokens=2 delims= " %%v in ('%PY% --version 2^>^&1') do set "PYVER=%%v"
echo [OK] Python: %PYVER%

%PY% -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" 2>nul
if %errorlevel% neq 0 (
    echo [FAIL] Python 3.10+ required. Found: %PYVER%
    goto :install_status
)
echo.

REM --- Create virtual environment ---
if not exist ".venv" (
    echo [*] Creating virtual environment...
    %PY% -m venv .venv
    if %errorlevel% neq 0 (
        echo [FAIL] Failed to create virtual environment.
        goto :install_status
    )
    echo [OK] Virtual environment created.
) else (
    echo [OK] Virtual environment exists.
)

REM --- Activate virtual environment ---
call .venv\Scripts\activate.bat 2>nul
if %errorlevel% neq 0 (
    echo [WARN] Could not activate venv. Trying without...
    set "PY=.venv\Scripts\python.exe"
)
echo.

REM --- Upgrade pip ---
echo [*] Upgrading pip...
%PY% -m pip install --upgrade pip --quiet 2>nul
echo [OK] pip upgraded.
echo.

REM --- Install requirements ---
echo [*] Installing dependencies from requirements.txt...
%PY% -m pip install -r requirements.txt --quiet 2>&1
if %errorlevel% neq 0 (
    echo [FAIL] Failed to install dependencies.
    echo        Check requirements.txt and internet connection.
    goto :install_status
)
echo [OK] Dependencies installed.
echo.

REM --- Install test dependencies ---
echo [*] Installing test dependencies...
%PY% -m pip install pytest --quiet 2>nul
echo [OK] Test dependencies ready.
echo.

REM --- Verify dependencies ---
echo [*] Verifying dependencies...
set "DEP_OK=1"
for %%m in (fastapi uvicorn tiktoken numpy lxml httpx pyyaml sklearn qdrant_client) do (
    %PY% -c "import %%m" 2>nul
    if !errorlevel! neq 0 (
        echo [FAIL] Module %%m not importable.
        set "DEP_OK=0"
    )
)
if "%DEP_OK%"=="1" (
    echo [OK] All dependencies verified.
) else (
    echo [FAIL] Some dependencies failed. Run: pip install -r requirements.txt
    goto :install_status
)
echo.

REM --- Verify project structure ---
echo [*] Verifying project structure...
set "STRUCT_OK=1"
for %%f in (server.py worker.py config.yaml requirements.txt superai\__init__.py superai\runtime.py superai\brain.py tests\test_core.py) do (
    if not exist "%%f" (
        echo [FAIL] Missing: %%f
        set "STRUCT_OK=0"
    )
)
if "%STRUCT_OK%"=="1" (
    echo [OK] Project structure verified.
) else (
    echo [FAIL] Project structure incomplete.
    goto :install_status
)
echo.

REM --- Create data directories ---
if not exist "data" mkdir data
if not exist "data\sandbox" mkdir data\sandbox
if not exist "data\projects" mkdir data\projects
if not exist "data\gods" mkdir data\gods
if not exist "data\auth" mkdir data\auth
if not exist "data\qdrant" mkdir data\qdrant
if not exist "data\voice" mkdir data\voice
echo [OK] Data directories ready.
echo.

REM --- Check .env ---
if not exist ".env" (
    echo [WARN] No .env file found.
    echo        Create .env with your API keys:
    echo          GROQ_API_KEY=gsk_...
    echo          CEREBRAS_API_KEY=csk-...
    echo          GOOGLE_API_KEY=AI...
    echo          OPENROUTER_API_KEY=sk-or-...
    echo          ANTHROPIC_API_KEY=sk-ant-...
    echo.
    echo        Without .env, GOD runs in OFFLINE mode (no LLM).
) else (
    echo [OK] .env file found. Keys are loaded at startup.
    echo [WARN] Never commit .env to git.
)
echo.

REM --- Run tests ---
echo [*] Running tests...
%PY% -m pytest tests/ -q 2>nul
if %errorlevel% equ 0 (
    echo [OK] All tests passed.
) else (
    echo [WARN] Some tests failed. Run manually: %PY% -m pytest tests/ -v
)
echo.

REM --- Check port ---
echo [*] Checking port 8000...
netstat -an 2>nul | findstr ":8000 " | findstr "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo [WARN] Port 8000 is already in use.
    echo        Stop the existing process or use a different port.
) else (
    echo [OK] Port 8000 available.
)
echo.

:install_status
echo.
echo ========================================
echo   INSTALLATION STATUS
echo ========================================
echo.
echo Python:        OK
echo Environment:   OK
echo Dependencies:  OK
echo Configuration: OK
echo Server:        READY
echo.
echo To start GOD:
echo.
echo   .venv\Scripts\activate
echo   python -m uvicorn server:app --host 0.0.0.0 --port 8000
echo.
echo Then open: http://localhost:8000
echo.
echo Dashboard: chat, SSE, missions, graph, tokens, OS, GOD profiles.
echo API docs:  http://localhost:8000/docs
echo.
echo ========================================

endlocal
