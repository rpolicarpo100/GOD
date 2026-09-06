@echo off
setlocal enabledelayedexpansion

set "GOD_DIR=%~dp0"
set "PY=.venv\Scripts\python.exe"
if "%GOD_PORT%"=="" set "GOD_PORT=8000"

if not exist "%PY%" (
    echo [FAIL] Virtual environment not found. Run setup.bat first.
    exit /b 1
)

set "CMD=%~1"
if "%CMD%"=="" goto :help

if "%CMD%"=="start" goto :start
if "%CMD%"=="start-lan" goto :start-lan
if "%CMD%"=="stop" goto :stop
if "%CMD%"=="status" goto :status
if "%CMD%"=="test" goto :test
if "%CMD%"=="doctor" goto :doctor
if "%CMD%"=="repair" goto :repair
if "%CMD%"=="benchmark" goto :benchmark
if "%CMD%"=="help" goto :help

echo [FAIL] Unknown command: %CMD%
goto :help

:start
echo Starting GOD on port %GOD_PORT%...
echo Dashboard: http://localhost:%GOD_PORT%
echo API docs:  http://localhost:%GOD_PORT%/docs
echo Bind:      127.0.0.1 (localhost only)
echo Auth:      Required for admin endpoints
echo Press Ctrl+C to stop.
echo.
"%PY%" -m uvicorn server:app --host 127.0.0.1 --port %GOD_PORT%
goto :eof

:start-lan
echo.
echo *** WARNING: Starting GOD in LAN mode! ***
echo *** This exposes GOD to your local network. ***
echo *** Authentication required for admin endpoints. ***
echo.
echo Starting GOD on port %GOD_PORT%...
echo Dashboard: http://localhost:%GOD_PORT%
echo Bind:      0.0.0.0 (LAN accessible)
echo Auth:      Required for admin endpoints
echo Press Ctrl+C to stop.
echo.
"%PY%" -m uvicorn server:app --host 0.0.0.0 --port %GOD_PORT%
goto :eof

:stop
echo Stopping GOD...
REM Find PID listening on port %GOD_PORT% — only kill that specific process
set "GOD_PID="
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":%GOD_PORT% " ^| findstr "LISTENING"') do (
    set "GOD_PID=%%a"
)
if defined GOD_PID (
    echo [OK] Found GOD process PID: %GOD_PID%
    taskkill /PID %GOD_PID% /F >nul 2>&1
    if !errorlevel! equ 0 (
        echo [OK] GOD stopped.
    ) else (
        echo [FAIL] Could not stop PID %GOD_PID%. Try: taskkill /PID %GOD_PID% /F
    )
) else (
    echo [WARN] GOD is not running on port %GOD_PORT%.
)
goto :eof

:status
echo Checking GOD status...
netstat -an 2>nul | findstr ":%GOD_PORT% " | findstr "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] GOD is running on port %GOD_PORT%.
    echo Dashboard: http://localhost:%GOD_PORT%
    "%PY%" -c "import httpx; r=httpx.get('http://127.0.0.1:8000/api/health',timeout=5); print(r.json())" 2>nul
    echo.
    echo Auth status:
    "%PY%" -c "import httpx; r=httpx.get('http://127.0.0.1:8000/api/auth/status',timeout=5); print(r.json())" 2>nul
) else (
    echo [WARN] GOD is not running on port %GOD_PORT%.
    echo        Start with: god start
)
goto :eof

:test
echo Running tests...
"%PY%" -m pytest tests/ -v
goto :eof

:doctor
echo Running diagnostics...
"%PY%" -c "
from superai import repair
r = repair.run()
print(f'REPAIR {r[\"kind\"]} ok={r[\"ok\"]}')
for a in r.get('actions') or []:
    st = 'OK' if a.get('ok') else 'FAIL'
    print(f'  [{st}] {a[\"check\"]} {a.get(\"error\") or a.get(\"fix\") or \"\"}')
print()
print(r.get('note') or '')
"
goto :eof

:repair
echo Running repair...
"%PY%" -c "
from superai import repair
r = repair.run()
print(f'REPAIR ok={r[\"ok\"]}')
for a in r.get('actions') or []:
    st = 'OK' if a.get('ok') else 'FAIL'
    print(f'  [{st}] {a[\"check\"]} {a.get(\"error\") or a.get(\"fix\") or \"\"}')
"
goto :eof

:benchmark
echo Running benchmark...
"%PY%" -c "
from superai.benchmark import run
s = run('cli')
print(f'BENCHMARK {s[\"run_id\"]}  n={s[\"n\"]}  passed={s[\"passed\"]}  skipped={s[\"skipped\"]}')
for r in s.get('rows') or []:
    st = 'SKIP' if r.get('skipped') else ('PASS' if r.get('passed') else 'FAIL')
    print(f'  {st} {r[\"case_id\"]}  score={r.get(\"score\")}  {r.get(\"latency_ms\")}ms')
"
goto :eof

:help
echo.
echo GOD — Commands
echo.
echo   god start       Start the server (localhost only, port %GOD_PORT%)
echo   god start-lan   Start the server (LAN accessible, port %GOD_PORT%)
echo   god stop        Stop the server
echo   god status      Check if server is running
echo   god test        Run test suite
echo   god doctor      Run diagnostics
echo   god repair      Run repair checks
echo   god benchmark   Run benchmark suite
echo   god help        Show this help
echo.
echo Security:
echo   Authentication required for admin endpoints.
echo   Create owner: POST /api/auth/setup
echo   Login:        POST /api/auth/login
echo.

endlocal
