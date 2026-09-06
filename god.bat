@echo off
setlocal enabledelayedexpansion

set "GOD_DIR=%~dp0"
set "PY=.venv\Scripts\python.exe"
if "%GOD_PORT%"=="" set "GOD_PORT=8000"
set "PID_FILE=%GOD_DIR%data\god.pid"
set "LOG_DIR=%GOD_DIR%logs"

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
if "%CMD%"=="backup" goto :backup
if "%CMD%"=="help" goto :help

echo [FAIL] Unknown command: %CMD%
goto :help

:start
REM Check port conflict
netstat -an 2>nul | findstr ":%GOD_PORT% " | findstr "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo [FAIL] Port %GOD_PORT% is already in use.
    echo        Stop the existing process or set GOD_PORT=^<other^>.
    exit /b 1
)
REM Check PID file
if exist "%PID_FILE%" (
    set /p OLD_PID=<"%PID_FILE%"
    if defined OLD_PID (
        tasklist /FI "PID eq !OLD_PID!" 2>nul | findstr "!OLD_PID!" >nul 2>&1
        if !errorlevel! equ 0 (
            echo [FAIL] GOD is already running (PID !OLD_PID!).
            echo        Stop first: god stop
            exit /b 1
        )
    )
    del "%PID_FILE%" 2>nul
)
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
echo Starting GOD on port %GOD_PORT%...
echo Dashboard: http://localhost:%GOD_PORT%
echo API docs:  http://localhost:%GOD_PORT%/docs
echo Bind:      127.0.0.1 (localhost only)
echo Logs:      %LOG_DIR%\
echo.
start /B "GOD" "%PY%" -m uvicorn server:app --host 127.0.0.1 --port %GOD_PORT% > "%LOG_DIR%\god.log" 2>&1
REM Wait briefly for startup
timeout /t 2 /nobreak >nul 2>&1
REM Find the PID
set "GOD_PID="
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":%GOD_PORT% " ^| findstr "LISTENING"') do (
    set "GOD_PID=%%a"
)
if defined GOD_PID (
    echo !GOD_PID!>"%PID_FILE%"
    echo [OK] GOD started (PID !GOD_PID!, port %GOD_PORT%).
    echo      Dashboard: http://localhost:%GOD_PORT%
    echo      Logs:      type %LOG_DIR%\god.log
    echo      Stop:      god stop
) else (
    echo [FAIL] GOD failed to start. Check logs:
    echo        type %LOG_DIR%\god.log
)
goto :eof

:start-lan
netstat -an 2>nul | findstr ":%GOD_PORT% " | findstr "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo [FAIL] Port %GOD_PORT% is already in use.
    exit /b 1
)
if exist "%PID_FILE%" (
    set /p OLD_PID=<"%PID_FILE%"
    if defined OLD_PID (
        tasklist /FI "PID eq !OLD_PID!" 2>nul | findstr "!OLD_PID!" >nul 2>&1
        if !errorlevel! equ 0 (
            echo [FAIL] GOD is already running (PID !OLD_PID!).
            echo        Stop first: god stop
            exit /b 1
        )
    )
    del "%PID_FILE%" 2>nul
)
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
echo.
echo *** WARNING: Starting GOD in LAN mode! ***
echo *** This exposes GOD to your local network. ***
echo.
echo Starting GOD on port %GOD_PORT%...
echo Dashboard: http://localhost:%GOD_PORT%
echo Bind:      0.0.0.0 (LAN accessible)
echo Logs:      %LOG_DIR%\
echo.
start /B "GOD" "%PY%" -m uvicorn server:app --host 0.0.0.0 --port %GOD_PORT% > "%LOG_DIR%\god.log" 2>&1
timeout /t 2 /nobreak >nul 2>&1
set "GOD_PID="
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":%GOD_PORT% " ^| findstr "LISTENING"') do (
    set "GOD_PID=%%a"
)
if defined GOD_PID (
    echo !GOD_PID!>"%PID_FILE%"
    echo [OK] GOD started (PID !GOD_PID!, port %GOD_PORT%, LAN mode).
) else (
    echo [FAIL] GOD failed to start. Check: type %LOG_DIR%\god.log
)
goto :eof

:stop
echo Stopping GOD...
set "STOPPED=0"
REM Try PID file first
if exist "%PID_FILE%" (
    set /p GOD_PID=<"%PID_FILE%"
    if defined GOD_PID (
        tasklist /FI "PID eq !GOD_PID!" 2>nul | findstr "!GOD_PID!" >nul 2>&1
        if !errorlevel! equ 0 (
            taskkill /PID !GOD_PID! /F >nul 2>&1
            set "STOPPED=1"
            echo [OK] Stopped (PID !GOD_PID!).
        )
    )
    del "%PID_FILE%" 2>nul
)
REM Fallback: find by port
if "!STOPPED!"=="0" (
    set "GOD_PID="
    for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":%GOD_PORT% " ^| findstr "LISTENING"') do (
        set "GOD_PID=%%a"
    )
    if defined GOD_PID (
        taskkill /PID !GOD_PID! /F >nul 2>&1
        echo [OK] Stopped (PID !GOD_PID!).
    ) else (
        echo [WARN] Not running on port %GOD_PORT%.
    )
)
goto :eof

:status
echo Checking GOD status...
if exist "%PID_FILE%" (
    set /p GOD_PID=<"%PID_FILE%"
    if defined GOD_PID (
        tasklist /FI "PID eq !GOD_PID!" 2>nul | findstr "!GOD_PID!" >nul 2>&1
        if !errorlevel! equ 0 (
            echo [OK] Process alive (PID !GOD_PID!).
        ) else (
            echo [WARN] PID file exists but process not found.
            del "%PID_FILE%" 2>nul
        )
    )
)
netstat -an 2>nul | findstr ":%GOD_PORT% " | findstr "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] GOD is running on port %GOD_PORT%.
    echo Dashboard: http://localhost:%GOD_PORT%
    "%PY%" -c "import httpx; r=httpx.get('http://127.0.0.1:%GOD_PORT%/api/health',timeout=5); print(r.json())" 2>nul
    echo.
    echo Auth status:
    "%PY%" -c "import httpx; r=httpx.get('http://127.0.0.1:%GOD_PORT%/api/auth/status',timeout=5); print(r.json())" 2>nul
) else (
    echo [WARN] GOD is not responding on port %GOD_PORT%.
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

:backup
set "BACKUP_DIR=%GOD_DIR%backups\%DATE:~10,4%-%DATE:~4,2%-%DATE:~7,2%_%TIME:~0,2%-%TIME:~3,2%-%TIME:~6,2%"
set "BACKUP_DIR=%BACKUP_DIR: =0%"
mkdir "%BACKUP_DIR%" 2>nul
echo Creating backup: %BACKUP_DIR%
if exist "%GOD_DIR%.env" (
    copy "%GOD_DIR%.env" "%BACKUP_DIR%\.env" >nul
    echo   [OK] .env
)
if exist "%GOD_DIR%config.yaml" (
    copy "%GOD_DIR%config.yaml" "%BACKUP_DIR%\config.yaml" >nul
    echo   [OK] config.yaml
)
if exist "%GOD_DIR%data" (
    xcopy "%GOD_DIR%data" "%BACKUP_DIR%\data\" /E /I /Q >nul 2>&1
    echo   [OK] data/
)
echo.
echo [OK] Backup complete: %BACKUP_DIR%
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
echo   god backup      Backup config + data
echo   god help        Show this help
echo.
echo Environment:
echo   set GOD_PORT=9000 ^& god start   Use custom port
echo.
echo Security:
echo   Authentication required for admin endpoints.
echo   Create owner: POST /api/auth/setup
echo   Login:        POST /api/auth/login
echo.

endlocal
