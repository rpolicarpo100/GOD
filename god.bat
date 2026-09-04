@echo off
setlocal enabledelayedexpansion

set "GOD_DIR=%~dp0"
set "PY=.venv\Scripts\python.exe"

if not exist "%PY%" (
    echo [FAIL] Virtual environment not found. Run setup.bat first.
    exit /b 1
)

set "CMD=%~1"
if "%CMD%"=="" goto :help

if "%CMD%"=="start" goto :start
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
echo Starting GOD on port 8000...
echo Dashboard: http://localhost:8000
echo API docs:  http://localhost:8000/docs
echo Press Ctrl+C to stop.
echo.
"%PY%" -m uvicorn server:app --host 0.0.0.0 --port 8000
goto :eof

:stop
echo Stopping GOD...
taskkill /f /im python.exe /fi "WINDOWTITLE eq *uvicorn*" 2>nul
taskkill /f /im python3.exe /fi "WINDOWTITLE eq *uvicorn*" 2>nul
echo [OK] Stop signal sent.
goto :eof

:status
echo Checking GOD status...
netstat -an 2>nul | findstr ":8000 " | findstr "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] GOD is running on port 8000.
    echo Dashboard: http://localhost:8000
    "%PY%" -c "import httpx; r=httpx.get('http://127.0.0.1:8000/api/health',timeout=5); print(r.json())" 2>nul
) else (
    echo [WARN] GOD is not running on port 8000.
    echo        Start with: god start
)
goto :eof

:test
echo Running tests...
"%PY%" -m unittest tests.test_core -v
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
echo   god start       Start the server (port 8000)
echo   god stop        Stop the server
echo   god status      Check if server is running
echo   god test        Run test suite
echo   god doctor      Run diagnostics
echo   god repair      Run repair checks
echo   god benchmark   Run benchmark suite
echo   god help        Show this help
echo.

endlocal
