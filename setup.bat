@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

echo.
echo ========================================
echo   GOD — Setup (Windows)
echo ========================================
echo.

set "GOD_DIR=%~dp0"
cd /d "%GOD_DIR%"
set "PY="
set "PYVER="
set "ERRORS=0"
set "WARNINGS=0"

echo [OK] Project directory: %GOD_DIR%
echo.

REM ── Check Python ─────────────────────────────────────

where python3 >nul 2>&1
if %errorlevel% equ 0 (
    set "PY=python3"
    goto :check_pyver
)
where python >nul 2>&1
if %errorlevel% equ 0 (
    set "PY=python"
    goto :check_pyver
)
echo [FAIL] Python not found in PATH.
echo        Install Python 3.10+ from https://www.python.org/downloads/
echo        Make sure to check "Add Python to PATH".
set /a ERRORS+=1
goto :install_status

:check_pyver
for /f "tokens=2 delims= " %%v in ('!PY! --version 2^>^&1') do set "PYVER=%%v"
echo [OK] Python: !PYVER!

!PY! -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" 2>nul
if !errorlevel! neq 0 (
    echo [FAIL] Python 3.10+ required. Found: !PYVER!
    set /a ERRORS+=1
    goto :install_status
)
echo.

REM ── Create virtual environment ───────────────────────

if not exist ".venv" (
    echo [*] Creating virtual environment...
    !PY! -m venv .venv
    if !errorlevel! neq 0 (
        echo [FAIL] Failed to create virtual environment.
        set /a ERRORS+=1
        goto :install_status
    )
    echo [OK] Virtual environment created.
) else (
    echo [OK] Virtual environment exists.
)

set "VENV_PY=.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
    echo [FAIL] Virtual environment corrupted. Remove .venv and retry.
    set /a ERRORS+=1
    goto :install_status
)
echo.

REM ── Upgrade pip ──────────────────────────────────────

echo [*] Upgrading pip...
"%VENV_PY%" -m pip install --upgrade pip --quiet 2>nul
echo [OK] pip upgraded.
echo.

REM ── Install requirements ─────────────────────────────

echo [*] Installing dependencies from requirements.txt...
"%VENV_PY%" -m pip install -r requirements.txt --quiet 2>&1
if !errorlevel! neq 0 (
    echo [FAIL] Failed to install dependencies.
    echo        Check requirements.txt and internet connection.
    set /a ERRORS+=1
    goto :install_status
)
echo [OK] Dependencies installed.
echo.

REM ── Install pytest ───────────────────────────────────

echo [*] Installing test tools...
"%VENV_PY%" -m pip install pytest --quiet 2>nul
echo [OK] Test tools ready.
echo.

REM ── Verify dependencies ──────────────────────────────

echo [*] Verifying dependencies...
set "DEP_OK=1"
for %%m in (fastapi uvicorn tiktoken numpy lxml httpx yaml sklearn qdrant_client) do (
    "%VENV_PY%" -c "import %%m" 2>nul
    if !errorlevel! neq 0 (
        echo [FAIL] Module %%m not importable.
        set "DEP_OK=0"
    )
)
if "!DEP_OK!"=="1" (
    echo [OK] All dependencies verified.
) else (
    echo [FAIL] Some dependencies failed. Run: pip install -r requirements.txt
    set /a ERRORS+=1
    goto :install_status
)
echo.

REM ── Verify project structure ─────────────────────────

echo [*] Verifying project structure...
set "STRUCT_OK=1"
for %%f in (server.py worker.py config.yaml requirements.txt superai\__init__.py superai\runtime.py superai\brain.py tests\test_core.py) do (
    if not exist "%%f" (
        echo [FAIL] Missing: %%f
        set "STRUCT_OK=0"
    )
)
if "!STRUCT_OK!"=="1" (
    echo [OK] Project structure verified.
) else (
    echo [FAIL] Project structure incomplete.
    set /a ERRORS+=1
    goto :install_status
)
echo.

REM ── Create data directories ──────────────────────────

for %%d in (data data\sandbox data\projects data\gods data\auth data\qdrant data\voice logs backups) do (
    if not exist "%%d" mkdir "%%d"
)
echo [OK] Data directories ready.
echo.

REM ── Check .env ───────────────────────────────────────

if not exist ".env" (
    echo [WARN] No .env file found.
    if exist ".env.example" (
        echo        Copy .env.example to .env and fill in your API keys:
        echo          copy .env.example .env
    ) else (
        echo        Create .env with your API keys.
    )
    echo        Without .env, GOD runs in OFFLINE mode (no LLM).
    set /a WARNINGS+=1
) else (
    echo [OK] .env file found.
)
echo.

REM ── Run tests ────────────────────────────────────────

echo [*] Running tests...
"%VENV_PY%" -m pytest tests/ -q 2>nul
if !errorlevel! equ 0 (
    echo [OK] All tests passed.
) else (
    echo [WARN] Some tests failed. Run: %VENV_PY% -m pytest tests/ -v
    set /a WARNINGS+=1
)
echo.

REM ── Check port ───────────────────────────────────────

echo [*] Checking port 8000...
netstat -an 2>nul | findstr ":8000 " | findstr "LISTENING" >nul 2>&1
if !errorlevel! equ 0 (
    echo [WARN] Port 8000 is already in use.
    set /a WARNINGS+=1
) else (
    echo [OK] Port 8000 available.
)
echo.

REM ── Installation Status ──────────────────────────────

:install_status
echo.
echo ========================================
echo   INSTALLATION STATUS
echo ========================================
echo.

if !ERRORS! GTR 0 (
    echo   RESULT: FAILED
    echo.
    echo   !ERRORS! error(s), !WARNINGS! warning(s).
    echo   Fix the issues above and run setup.bat again.
    echo.
    endlocal
    exit /b 1
)

if !WARNINGS! GTR 0 (
    echo   RESULT: OK (with warnings)
    echo.
    echo   !WARNINGS! warning(s). GOD should work but check the warnings above.
) else (
    echo   RESULT: OK
    echo.
    echo   All checks passed.
)

echo.
echo   To start GOD:
echo.
echo     god.bat start
echo.
echo   Then open: http://localhost:8000
echo.
echo   Dashboard: http://localhost:8000
echo   API docs:  http://localhost:8000/docs
echo   Auth:      POST /api/auth/setup to create owner
echo.
echo ========================================

endlocal
exit /b 0
