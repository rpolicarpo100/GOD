@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

REM ═══════════════════════════════════════════════════
REM   GOD — Windows Command Helper
REM ═══════════════════════════════════════════════════

set "GOD_DIR=%~dp0"
set "PY=.venv\Scripts\python.exe"
if "%GOD_PORT%"=="" set "GOD_PORT=8000"
set "PID_FILE=%GOD_DIR%data\god.pid"
set "LOG_DIR=%GOD_DIR%logs"

REM ── Dispatcher ──────────────────────────────────────

set "CMD=%~1"
if "%CMD%"=="" goto :help
if "%CMD%"=="start" goto :start
if "%CMD%"=="start-lan" goto :start-lan
if "%CMD%"=="restart" goto :restart
if "%CMD%"=="stop" goto :stop
if "%CMD%"=="status" goto :status
if "%CMD%"=="test" goto :test
if "%CMD%"=="doctor" goto :doctor
if "%CMD%"=="repair" goto :repair
if "%CMD%"=="benchmark" goto :benchmark
if "%CMD%"=="backup" goto :backup
if "%CMD%"=="config" goto :config
if "%CMD%"=="dev" goto :dev
if "%CMD%"=="update" goto :update
if "%CMD%"=="uninstall" goto :uninstall
if "%CMD%"=="gpu" goto :gpu
if "%CMD%"=="help" goto :help
echo [FAIL] Unknown command: %CMD%
goto :help

REM ═══════════════════════════════════════════════════
REM   COMMANDS
REM ═══════════════════════════════════════════════════

:start
if not exist "%PY%" (
    echo [FAIL] Virtual environment not found. Run setup.bat first.
    exit /b 1
)
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
timeout /t 3 /nobreak >nul 2>&1
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
    exit /b 1
)
goto :eof

:start-lan
if not exist "%PY%" (
    echo [FAIL] Virtual environment not found. Run setup.bat first.
    exit /b 1
)
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
start /B "GOD" "%PY%" -m uvicorn server:app --host 0.0.0.0 --port %GOD_PORT% > "%LOG_DIR%\god.log" 2>&1
timeout /t 3 /nobreak >nul 2>&1
set "GOD_PID="
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":%GOD_PORT% " ^| findstr "LISTENING"') do (
    set "GOD_PID=%%a"
)
if defined GOD_PID (
    echo !GOD_PID!>"%PID_FILE%"
    echo [OK] GOD started (PID !GOD_PID!, port %GOD_PORT%, LAN mode).
) else (
    echo [FAIL] GOD failed to start. Check: type %LOG_DIR%\god.log
    exit /b 1
)
goto :eof


:restart
echo Restarting GOD...
call :stop 2>nul
timeout /t 2 /nobreak >nul 2>&1
call :start
goto :eof

:stop
echo Stopping GOD...
set "STOPPED=0"
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
echo GOD Status
echo ────────────────────────────────
if exist "%PID_FILE%" (
    set /p GOD_PID=<"%PID_FILE%"
    if defined GOD_PID (
        tasklist /FI "PID eq !GOD_PID!" 2>nul | findstr "!GOD_PID!" >nul 2>&1
        if !errorlevel! equ 0 (
            echo   Process:   alive (PID !GOD_PID!)
        ) else (
            echo   Process:   dead (stale PID file)
            del "%PID_FILE%" 2>nul
        )
    )
) else (
    echo   Process:   no PID file
)
netstat -an 2>nul | findstr ":%GOD_PORT% " | findstr "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo   Server:    running (port %GOD_PORT%)
) else (
    echo   Server:    not responding
)
for /f "tokens=*" %%c in ('cd /d "%GOD_DIR%" 2^>nul ^& git rev-parse --short HEAD 2^>nul') do echo   Commit:    %%c
if exist "%GOD_DIR%data\spine.db" echo   Database:  exists
if exist "%GOD_DIR%data\auth\users.json" echo   Auth:      configured
echo ────────────────────────────────
echo   Dashboard: http://localhost:%GOD_PORT%
echo.
goto :eof

:test
if not exist "%PY%" (
    echo [FAIL] Virtual environment not found. Run setup.bat first.
    exit /b 1
)
echo Running tests...
"%PY%" -m pytest tests/ -v
goto :eof

:doctor
if not exist "%PY%" (
    echo [FAIL] Virtual environment not found. Run setup.bat first.
    exit /b 1
)
echo GOD Doctor
echo ══════════════════════════════════
set "DOC_ERR=0"
set "DOC_WARN=0"

echo   [01] Python............. 
if exist "%PY%" (
    for /f "tokens=2" %%v in ('"%PY%" --version 2^>^&1') do echo PASS  %%v
) else (
    echo FAIL  venv not found
    set /a DOC_ERR+=1
)

echo   [02] Python version..... 
"%PY%" -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" 2>nul
if !errorlevel! equ 0 (echo PASS  3.10+) else (echo FAIL  requires 3.10+ & set /a DOC_ERR+=1)

echo   [03] Dependencies...... 
"%PY%" -c "import fastapi,uvicorn,tiktoken,numpy,lxml,httpx,yaml,sklearn,qdrant_client" 2>nul
if !errorlevel! equ 0 (echo PASS) else (echo FAIL  some imports failed & set /a DOC_ERR+=1)

echo   [04] PyYAML............ 
"%PY%" -c "import yaml" 2>nul
if !errorlevel! equ 0 (echo PASS) else (echo FAIL  not installed & set /a DOC_ERR+=1)

echo   [05] Configuration..... 
if exist "%GOD_DIR%.env" (echo PASS) else (echo WARN  no .env & set /a DOC_WARN+=1)

echo   [06] Database.......... 
if exist "%GOD_DIR%data\spine.db" (echo PASS) else (echo WARN  not found & set /a DOC_WARN+=1)

echo   [07] Auth.............. 
if exist "%GOD_DIR%data\auth\users.json" (echo PASS) else (echo WARN  no users & set /a DOC_WARN+=1)

echo   [08] GOD Profile....... 
if exist "%GOD_DIR%data\gods\master.json" (echo PASS) else (echo WARN  no master & set /a DOC_WARN+=1)

echo   [09] Port %GOD_PORT%............ 
netstat -an 2>nul | findstr ":%GOD_PORT% " | findstr "LISTENING" >nul 2>&1
if !errorlevel! equ 0 (echo PASS  listening) else (echo INFO  not listening)

echo   [10] Git state......... 
for /f "tokens=*" %%c in ('cd /d "%GOD_DIR%" 2^>nul ^& git rev-parse --short HEAD 2^>nul') do (
    for /f "tokens=*" %%b in ('git branch --show-current 2^>nul') do echo PASS  %%b @ %%c
)
if !errorlevel! neq 0 (echo WARN  not a git repo & set /a DOC_WARN+=1)

echo   [11] Disk Space........ 
for /f "tokens=3" %%d in ('dir "%GOD_DIR%" 2^>nul ^| findstr /C:"bytes free"') do echo PASS  %%d bytes free
if !errorlevel! neq 0 (echo PASS)

echo ══════════════════════════════════
if !DOC_ERR! GTR 0 (
    echo   GOD DOCTOR: FAILED  [!DOC_ERR! error(s), !DOC_WARN! warning(s)]
    exit /b 1
) else if !DOC_WARN! GTR 0 (
    echo   GOD DOCTOR: DEGRADED  [!DOC_WARN! warning(s)]
) else (
    echo   GOD DOCTOR: HEALTHY
)
echo.
goto :eof
:repair
if not exist "%PY%" (
    echo [FAIL] Virtual environment not found. Run setup.bat first.
    exit /b 1
)
echo Running repair...
set "_PY_SCRIPT=%TEMP%\god_repair.py"
(
    echo from superai import repair
    echo r = repair.run^(^)
    echo print^(f'REPAIR {r["kind"]} ok={r["ok"]}'^)
    echo for a in r.get^('actions'^) or []^:
    echo     st = 'OK' if a.get^('ok'^) else 'FAIL'
    echo     print^(f'  [{st}] {a["check"]} {a.get^("error"^) or a.get^("fix"^) or ""}'^)
    echo print^(^)
    echo print^(r.get^('note'^) or ''^)
) > "%_PY_SCRIPT%"
"%PY%" "%_PY_SCRIPT%"
del "%_PY_SCRIPT%" 2>nul
goto :eof

:benchmark
if not exist "%PY%" (
    echo [FAIL] Virtual environment not found. Run setup.bat first.
    exit /b 1
)
echo Running benchmark...
set "_PY_SCRIPT=%TEMP%\god_benchmark.py"
(
    echo from superai.benchmark import run
    echo s = run^('cli'^)
    echo print^(f'BENCHMARK {s["run_id"]}  n={s["n"]}  passed={s["passed"]}  skipped={s["skipped"]}'^)
    echo for r in s.get^('rows'^) or []^:
    echo     st = 'SKIP' if r.get^('skipped'^) else ^('PASS' if r.get^('passed'^) else 'FAIL'^)
    echo     print^(f'  {st} {r["case_id"]}  score={r.get^("score"^)}  {r.get^("latency_ms"^)}ms'^)
) > "%_PY_SCRIPT%"
"%PY%" "%_PY_SCRIPT%"
del "%_PY_SCRIPT%" 2>nul
goto :eof

:backup
echo GOD Backup
echo ══════════════════════════════════
set "BACKUP_DIR=%GOD_DIR%backups\%DATE:~10,4%-%DATE:~4,2%-%DATE:~7,2%_%TIME:~0,2%-%TIME:~3,2%-%TIME:~6,2%"
set "BACKUP_DIR=%BACKUP_DIR: =0%"
mkdir "%BACKUP_DIR%" 2>nul
mkdir "%BACKUP_DIR%\data" 2>nul
echo   Target: %BACKUP_DIR%
echo.
if exist "%GOD_DIR%.env" (
    copy "%GOD_DIR%.env" "%BACKUP_DIR%\.env" >nul
    echo   .env.............. OK
) else (
    echo   .env.............. SKIP
)
if exist "%GOD_DIR%config.yaml" (
    copy "%GOD_DIR%config.yaml" "%BACKUP_DIR%\config.yaml" >nul
    echo   config.yaml....... OK
) else (
    echo   config.yaml....... SKIP
)
if exist "%GOD_DIR%data\auth" (
    xcopy "%GOD_DIR%data\auth" "%BACKUP_DIR%\data\auth\" /E /I /Q >nul 2>&1
    echo   data/auth/........ OK
)
if exist "%GOD_DIR%data\gods" (
    xcopy "%GOD_DIR%data\gods" "%BACKUP_DIR%\data\gods\" /E /I /Q >nul 2>&1
    echo   data/gods/........ OK
)
if exist "%GOD_DIR%data\spine.db" (
    copy "%GOD_DIR%data\spine.db" "%BACKUP_DIR%\data\" >nul
    echo   data/spine.db..... OK
)
echo.
echo ══════════════════════════════════
echo   Backup: %BACKUP_DIR%
echo.
goto :eof

:config
echo.
echo GOD — Configuration
echo.
if exist "%GOD_DIR%.env" (
    echo [OK] .env already exists.
    echo.
    set /p OVERWRITE="Overwrite? (y/N): "
    if /i not "!OVERWRITE!"=="y" (
        echo Cancelled.
        goto :eof
    )
)
echo Select mode:
echo.
echo   [1] API / Cloud  — Use providers
echo   [2] Offline      — No LLM, tools only
echo   [3] Manual       — I'll edit .env myself
echo.
set /p CMODE="Choose [1-3]: "
if "%CMODE%"=="1" (
    echo.
    echo Enter API keys (leave blank to skip):
    echo.
    set /p GROQ_KEY="  Groq key (free): "
    set /p GOOGLE_KEY="  Google key (free): "
    set /p ANTHRO_KEY="  Anthropic key (paid): "
    set /p OPENR_KEY="  OpenRouter key: "
    (
        echo # GOD — API keys (generated by god config)
        echo GROQ_API_KEY=!GROQ_KEY!
        echo GOOGLE_API_KEY=!GOOGLE_KEY!
        echo ANTHROPIC_API_KEY=!ANTHRO_KEY!
        echo OPENROUTER_API_KEY=!OPENR_KEY!
    ) > "%GOD_DIR%.env"
    echo.
    echo [OK] .env created.
)
if "%CMODE%"=="2" (
    echo # GOD — Offline mode>"%GOD_DIR%.env"
    echo [OK] .env created (offline mode).
)
if "%CMODE%"=="3" (
    if not exist "%GOD_DIR%.env" (
        if exist "%GOD_DIR%.env.example" (
            copy "%GOD_DIR%.env.example" "%GOD_DIR%.env" >nul
            echo [OK] Copied .env.example. Edit with your keys.
        ) else (
            echo [WARN] No .env created. Create manually.
        )
    )
)
echo.
echo Edit later: %GOD_DIR%.env
goto :eof

:dev
if not exist "%PY%" (
    echo [FAIL] Virtual environment not found. Run setup.bat first.
    exit /b 1
)
netstat -an 2>nul | findstr ":%GOD_PORT% " | findstr "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo [FAIL] Port %GOD_PORT% is already in use.
    exit /b 1
)
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
echo Starting GOD in DEV mode (auto-reload) on port %GOD_PORT%...
echo.
"%PY%" -m uvicorn server:app --host 127.0.0.1 --port %GOD_PORT% --reload
goto :eof

:update
if not exist "%PY%" (
    echo [FAIL] Virtual environment not found. Run setup.bat first.
    exit /b 1
)
echo Updating GOD...
if exist "%GOD_DIR%.git" (
    git pull
    "%PY%" -m pip install -r requirements.txt --quiet 2>&1
    "%PY%" -m pytest tests/ -q 2>nul
    echo [OK] Update complete.
) else (
    echo [FAIL] Not a git repository.
)
goto :eof

:uninstall
echo.
echo GOD — Uninstall
echo ══════════════════════════════════
echo.
echo   [1] Remove application only (keep data)
echo   [2] Remove application + cache
echo   [3] Remove everything (requires DELETE confirmation)
echo   [0] Cancel
echo.
set /p UCHOICE="  Choose: "
if "!UCHOICE!"=="1" (
    call :stop 2>nul
    rmdir /s /q "%GOD_DIR%.venv" 2>nul
    del "%PID_FILE%" 2>nul
    echo.
    echo   Application removed. Data preserved.
    echo.
)
if "!UCHOICE!"=="2" (
    call :stop 2>nul
    rmdir /s /q "%GOD_DIR%.venv" 2>nul
    rmdir /s /q "%GOD_DIR%data\qdrant" 2>nul
    rmdir /s /q "%GOD_DIR%data\sandbox" 2>nul
    del "%PID_FILE%" 2>nul
    echo.
    echo   Application + cache removed. Data preserved.
    echo.
)
if "!UCHOICE!"=="3" (
    echo.
    echo WARNING: This permanently removes ALL GOD files.
    set /p CONFIRM="  Type DELETE to confirm: "
    if "!CONFIRM!"=="DELETE" (
        call :stop 2>nul
        rmdir /s /q "%GOD_DIR%.venv" 2>nul
        rmdir /s /q "%GOD_DIR%data" 2>nul
        rmdir /s /q "%GOD_DIR%logs" 2>nul
        del "%GOD_DIR%.env" 2>nul
        echo.
        echo   Everything removed.
        echo.
    ) else (
        echo   Cancelled.
    )
)
goto :eof

:gpu
echo GPU Detection
echo.
where nvidia-smi >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] NVIDIA GPU detected:
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>nul
) else (
    echo [INFO] No NVIDIA GPU detected.
    echo        GOD works without GPU in API/CPU mode.
)
echo.
goto :eof

:help
echo.
echo GOD — Commands
echo.
echo   god start       Start the server (localhost only, port %GOD_PORT%)
echo   god start-lan   Start the server (LAN accessible, port %GOD_PORT%)
echo   god restart     Restart the server (stop + start)
echo   god dev         Start in dev mode (auto-reload)
echo   god stop        Stop the server
echo   god status      Check if server is running
echo   god test        Run test suite
echo   god doctor      Run diagnostics
echo   god repair      Run repair checks
echo   god benchmark   Run benchmark suite
echo   god backup      Backup config + data
echo   god config      Configure API keys
echo   god update      Pull updates + deps + tests
echo   god uninstall   Remove GOD
echo   god gpu         Detect GPU
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
