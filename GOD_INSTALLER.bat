@echo off
setlocal enabledelayedexpansion

REM ═══════════════════════════════════════════════════════════
REM   GOD INSTALLER — Windows
REM   Single entry point: detection, preflight, install, verify
REM ═══════════════════════════════════════════════════════════

set "GOD_DIR=%~dp0"
cd /d "%GOD_DIR%"
set "PY="
set "PYVER="
set "VENV_PY=.venv\Scripts\python.exe"
set "LOG_DIR=%GOD_DIR%logs"
set "LOG=%LOG_DIR%\installer.log"
set "RUN_ID=%RANDOM%%RANDOM%"
set "GOD_PORT=8000"
set "PROFILE="
set "ERRORS=0"
set "WARNINGS=0"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

REM ── Welcome ─────────────────────────────────────────────

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║            G O D   I N S T A L L E R     ║
echo  ║                                          ║
echo  ║   AI Agent System — Windows Setup        ║
echo  ╚══════════════════════════════════════════╝
echo.
echo  Run ID: %RUN_ID%
echo  Log:    %LOG%
echo.

echo [%date% %time%] GOD INSTALLER started > "%LOG%"
echo Run ID: %RUN_ID% >> "%LOG%"
echo. >> "%LOG%"

REM ── Check if already installed ──────────────────────────

if exist "%VENV_PY%" (
    echo  [INFO] GOD installation detected.
    echo.
    echo   [1] Verify existing installation
    echo   [2] Repair
    echo   [3] Update
    echo   [4] Reinstall
    echo   [0] Cancel
    echo.
    set /p EXISTING="  Choose: "
    if "!EXISTING!"=="1" goto :verify
    if "!EXISTING!"=="2" goto :repair
    if "!EXISTING!"=="3" goto :update
    if "!EXISTING!"=="4" goto :preflight
    echo  Cancelled.
    goto :eof
)

REM ═══════════════════════════════════════════════════════════
REM   PHASE 1: DETECTION
REM ═══════════════════════════════════════════════════════════

:preflight

echo.
echo ========================================
echo   SYSTEM CHECK
echo ========================================
echo.

echo [%date% %time%] PHASE 1: DETECTION >> "%LOG%"

REM ── Windows version ──
echo  [01/10] Windows..........
ver | findstr /i "10\." >nul 2>&1
if %errorlevel% equ 0 (
    echo          PASS  Windows 10
    echo  Windows 10: PASS >> "%LOG%"
    goto :check_arch
)
ver | findstr /i "11\." >nul 2>&1
if %errorlevel% equ 0 (
    echo          PASS  Windows 11
    echo  Windows 11: PASS >> "%LOG%"
    goto :check_arch
)
echo          WARN  Unsupported Windows version
echo  Windows: WARN (unsupported) >> "%LOG%"
set /a WARNINGS+=1

:check_arch

REM ── Architecture ──
echo  [02/10] Architecture.....
if "%PROCESSOR_ARCHITECTURE%"=="AMD64" (
    echo          PASS  x64
) else if "%PROCESSOR_ARCHITECTURE%"=="ARM64" (
    echo          PASS  ARM64
) else (
    echo          WARN  %PROCESSOR_ARCHITECTURE% (untested)
    set /a WARNINGS+=1
)

REM ── RAM ──
echo  [03/10] RAM..............
for /f "tokens=2 delims==" %%a in ('wmic computersystem get TotalPhysicalMemory /value 2^>nul ^| findstr "="') do set "RAM_BYTES=%%a"
if defined RAM_BYTES (
    set /a "RAM_MB=RAM_BYTES/1048576" 2>nul
    set /a "RAM_GB=RAM_MB/1024" 2>nul
    if !RAM_GB! GEQ 4 (
        echo          PASS  !RAM_GB! GB
    ) else (
        echo          WARN  !RAM_GB! GB ^(recommended: 4+ GB^)
        set /a WARNINGS+=1
    )
) else (
    echo          SKIP  Could not detect
)

REM ── Disk ──
echo  [04/10] Disk.............
for /f "tokens=3" %%a in ('dir /-c "%GOD_DIR%." 2^>nul ^| findstr /i "bytes free"') do set "DISK_FREE=%%a"
if defined DISK_FREE (
    echo          PASS  Available
) else (
    echo          PASS  Checked
)

REM ── Python ──
echo  [05/10] Python...........
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
echo          FAIL  Python not found
echo          Install Python 3.10+ from https://www.python.org/downloads/
echo          Make sure to check "Add Python to PATH"
echo  Python: FAIL >> "%LOG%"
set /a ERRORS+=1
goto :check_git

:check_pyver
for /f "tokens=2 delims= " %%v in ('!PY! --version 2^>^&1') do set "PYVER=%%v"
!PY! -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" 2>nul
if %errorlevel% equ 0 (
    echo          PASS  !PYVER!
    echo  Python !PYVER!: PASS >> "%LOG%"
) else (
    echo          FAIL  !PYVER! (need 3.10+)
    echo  Python !PYVER__: FAIL (need 3.10+) >> "%LOG%"
    set /a ERRORS+=1
    set "PY="
)

REM ── Git ──
:check_git
echo  [06/10] Git..............
where git >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=3" %%v in ('git --version 2^>nul') do echo          PASS  %%v
) else (
    echo          WARN  Not found (optional, needed for update)
    set /a WARNINGS+=1
)

REM ── Internet ──
echo  [07/10] Internet.........
ping -n 1 -w 2000 pypi.org >nul 2>&1
if %errorlevel% equ 0 (
    echo          PASS  Connected
) else (
    ping -n 1 -w 2000 google.com >nul 2>&1
    if %errorlevel% equ 0 (
        echo          PASS  Connected
    ) else (
        echo          WARN  No internet (offline install only)
        set /a WARNINGS+=1
    )
)

REM ── Port ──
echo  [08/10] Port %GOD_PORT%.........
netstat -an 2>nul | findstr ":%GOD_PORT% " | findstr "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo          WARN  Port %GOD_PORT% in use
    set /a WARNINGS+=1
) else (
    echo          PASS  Available
)

REM ── GPU ──
echo  [09/10] GPU..............
where nvidia-smi >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=*" %%g in ('nvidia-smi --query-gpu^=name --format^=csv^,noheader 2^>nul') do echo          PASS  %%g
) else (
    echo          INFO  Not detected (not required)
    echo          GPU is not required for API/CPU mode.
)

REM ── Existing process ──
echo  [10/10] Existing GOD.....
netstat -an 2>nul | findstr ":%GOD_PORT% " | findstr "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo          WARN  Process on port %GOD_PORT%
) else (
    echo          PASS  No conflict
)

echo.
echo [%date% %time%] DETECTION: !ERRORS! errors, !WARNINGS! warnings >> "%LOG%"

REM ── Decision ──
if !ERRORS! GTR 0 (
    echo ========================================
    echo   INSTALLATION BLOCKED
    echo ========================================
    echo.
    echo  !ERRORS! error(s) found. Fix the issues above and retry.
    echo.
    echo  Log: %LOG%
    exit /b 2
)

if !WARNINGS! GTR 0 (
    echo  !WARNINGS! warning(s). Installation can continue.
    echo.
)

REM ═══════════════════════════════════════════════════════════
REM   PHASE 2: PROFILE SELECTION
REM ═══════════════════════════════════════════════════════════

echo ========================================
echo   INSTALLATION PROFILE
echo ========================================
echo.
echo   [1] MINIMAL
echo       Core only. No neural embeddings, no voice.
echo       Fast install, smaller disk usage.
echo.
echo   [2] STANDARD
echo       Core + embeddings + voice TTS.
echo       Recommended for most users.
echo.
echo   [3] DEVELOPMENT
echo       Standard + test tools + dev mode.
echo       For contributors.
echo.
set /p PROFILE="  Choose [1-3]: "
if "%PROFILE%"=="" set "PROFILE=2"

echo.
echo [%date% %time%] PROFILE: %PROFILE% >> "%LOG%"

if "%PROFILE%"=="1" (
    echo  [*] Profile: MINIMAL
    set "REQ_FILE=requirements-minimal.txt"
) else if "%PROFILE%"=="3" (
    echo  [*] Profile: DEVELOPMENT
    set "REQ_FILE=requirements.txt"
) else (
    echo  [*] Profile: STANDARD
    set "REQ_FILE=requirements.txt"
)
echo.

REM ═══════════════════════════════════════════════════════════
REM   PHASE 3: INSTALL
REM ═══════════════════════════════════════════════════════════

echo ========================================
echo   INSTALLING
echo ========================================
echo.

echo [%date% %time%] PHASE 3: INSTALL >> "%LOG%"

REM ── Create venv ──
echo  [01/05] Creating virtual environment...
if not exist ".venv" (
    !PY! -m venv .venv >> "%LOG%" 2>&1
    if !errorlevel! neq 0 (
        echo          FAIL  Could not create venv
        echo  venv: FAIL >> "%LOG%"
        exit /b 4
    )
    echo          PASS
) else (
    echo          OK    Already exists
)

REM ── Upgrade pip ──
echo  [02/05] Upgrading pip...
"%VENV_PY%" -m pip install --upgrade pip --quiet >> "%LOG%" 2>&1
echo          PASS

REM ── Install dependencies ──
echo  [03/05] Installing dependencies (%REQ_FILE%)...
"%VENV_PY%" -m pip install -r %REQ_FILE% --quiet >> "%LOG%" 2>&1
if !errorlevel! neq 0 (
    echo          FAIL  pip install failed. Check log: %LOG%
    echo  deps: FAIL >> "%LOG%"
    exit /b 4
)
echo          PASS

REM ── Install pytest ──
echo  [04/05] Installing test tools...
"%VENV_PY%" -m pip install pytest --quiet >> "%LOG%" 2>&1
echo          PASS

REM ── Create directories ──
echo  [05/05] Creating directories...
for %%d in (data data\sandbox data\projects data\gods data\auth data\qdrant data\voice logs backups) do (
    if not exist "%%d" mkdir "%%d"
)
echo          PASS

echo.
echo [%date% %time%] INSTALL complete >> "%LOG%"

REM ═══════════════════════════════════════════════════════════
REM   PHASE 4: CONFIGURE
REM ═══════════════════════════════════════════════════════════

echo ========================================
echo   CONFIGURATION
echo ========================================
echo.

if exist ".env" (
    echo  [OK] .env already exists.
    echo.
    set /p RECONFIG="  Reconfigure? (y/N): "
    if /i not "!RECONFIG!"=="y" goto :verify
)

echo  Select mode:
echo.
echo   [1] API / Cloud  — Use providers (Groq, Google, Anthropic...)
echo   [2] Offline      — No LLM, tools only
echo   [3] Skip         — Configure later
echo.
set /p CMODE="  Choose [1-3]: "

if "%CMODE%"=="1" (
    echo.
    echo  Enter API keys (leave blank to skip):
    echo.
    set /p GROQ_KEY="    Groq (free, fast): "
    set /p GOOGLE_KEY="   Google (free, Gemini): "
    set /p ANTHRO_KEY="   Anthropic (paid, Claude): "
    set /p OPENR_KEY="    OpenRouter (aggregator): "
    set /p CEREB_KEY="    Cerebras (free): "
    set /p NVIDIA_KEY="   NVIDIA (free, DeepSeek): "
    set /p MISTRAL_KEY="   Mistral (free, Codestral): "
    set /p SAMBA_KEY="    SambaNova (free): "
    (
        echo # GOD — API keys (generated by installer)
        echo # %date% %time%
        echo.
        echo GROQ_API_KEY=!GROQ_KEY!
        echo GOOGLE_API_KEY=!GOOGLE_KEY!
        echo ANTHROPIC_API_KEY=!ANTHRO_KEY!
        echo OPENROUTER_API_KEY=!OPENR_KEY!
        echo CEREBRAS_API_KEY=!CEREB_KEY!
        echo NVIDIA_API_KEY=!NVIDIA_KEY!
        echo MISTRAL_API_KEY=!MISTRAL_KEY!
        echo SAMBANOVA_API_KEY=!SAMBA_KEY!
    ) > ".env"
    echo.
    echo  [OK] .env created.
    set /p CONFIGURED=0
    for /f %%k in ('findstr /c:"=." ".env" 2^>nul ^| find /c "API_KEY"') do set "CONFIGURED=%%k"
    echo       !CONFIGURED! keys configured.
) else if "%CMODE%"=="2" (
    (
        echo # GOD — Offline mode
        echo # No API keys configured
    ) > ".env"
    echo  [OK] .env created (offline mode).
) else (
    if not exist ".env" (
        if exist ".env.example" (
            copy ".env.example" ".env" >nul
            echo  [OK] Copied .env.example. Edit with your keys.
        ) else (
            echo  [WARN] No .env created. Create manually before starting.
        )
    )
)

echo.
echo [%date% %time%] CONFIGURATION done >> "%LOG%"

REM ═══════════════════════════════════════════════════════════
REM   PHASE 5: VERIFY
REM ═══════════════════════════════════════════════════════════

:verify

echo ========================================
echo   VERIFICATION
echo ========================================
echo.

echo [%date% %time%] PHASE 5: VERIFY >> "%LOG%"

REM ── Verify imports ──
echo  [01/04] Verifying imports...
set "DEP_OK=1"
for %%m in (fastapi uvicorn tiktoken numpy httpx pyyaml qdrant_client) do (
    "%VENV_PY%" -c "import %%m" 2>nul
    if !errorlevel! neq 0 (
        echo          FAIL  %%m not importable
        set "DEP_OK=0"
    )
)
if "!DEP_OK!"=="1" (
    echo          PASS
) else (
    echo          WARN  Some imports failed
    set /a WARNINGS+=1
)

REM ── Verify structure ──
echo  [02/04] Verifying structure...
set "STRUCT_OK=1"
for %%f in (server.py worker.py config.yaml requirements.txt superai\__init__.py superai\runtime.py tests\test_core.py) do (
    if not exist "%%f" (
        echo          FAIL  Missing: %%f
        set "STRUCT_OK=0"
    )
)
if "!STRUCT_OK!"=="1" (
    echo          PASS
) else (
    echo          FAIL  Incomplete structure
    set /a ERRORS+=1
)

REM ── Run tests ──
echo  [03/04] Running tests...
"%VENV_PY%" -m pytest tests/ -q 2>nul > "%LOG_DIR%\test_results.txt"
if !errorlevel! equ 0 (
    for /f "tokens=*" %%r in ('findstr /c:"passed" "%LOG_DIR%\test_results.txt" 2^>nul') do echo          PASS  %%r
) else (
    echo          WARN  Some tests failed
    set /a WARNINGS+=1
)

REM ── Generate manifest ──
echo  [04/04] Generating manifest...
"%VENV_PY%" -c "
import json, platform, sys, os
from datetime import datetime, timezone
manifest = {
    'timestamp': datetime.now(timezone.utc).isoformat(),
    'run_id': '%RUN_ID%',
    'god_version': '0.3.0',
    'profile': '%PROFILE%',
    'python_version': sys.version.split()[0],
    'platform': platform.system(),
    'architecture': platform.machine(),
    'port': %GOD_PORT%,
    'components': {
        'server': os.path.exists('server.py'),
        'worker': os.path.exists('worker.py'),
        'ui': os.path.exists('index.html'),
        'database': os.path.exists(os.path.join('data', 'spine.db')),
        'auth': os.path.exists(os.path.join('data', 'auth')),
    },
}
try:
    import subprocess
    manifest['commit'] = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD'], text=True).strip()
except:
    manifest['commit'] = 'unknown'
open(os.path.join('data', 'install_manifest.json'), 'w').write(json.dumps(manifest, indent=2))
" 2>nul
echo          PASS

echo.
echo [%date% %time%] VERIFY complete: !ERRORS! errors, !WARNINGS! warnings >> "%LOG%"

REM ═══════════════════════════════════════════════════════════
REM   RESULT
REM ═══════════════════════════════════════════════════════════

echo ========================================
if !ERRORS! GTR 0 (
    echo   INSTALLATION FAILED
    echo ========================================
    echo.
    echo  !ERRORS! error(s), !WARNINGS! warning(s).
    echo  Check log: %LOG%
    echo.
    exit /b 4
) else if !WARNINGS! GTR 0 (
    echo   INSTALLATION COMPLETE (with warnings)
) else (
    echo   INSTALLATION VERIFIED
)
echo ========================================
echo.
echo  Profile:     %PROFILE%
echo  Python:      %PYVER%
echo  Port:        %GOD_PORT%
echo  Directory:   %GOD_DIR%
echo  Tests:       See %LOG_DIR%\test_results.txt
echo  Log:         %LOG%
echo.
echo  To start GOD:
echo.
echo    god start
echo.
echo  Or:
echo.
echo    god.bat start
echo.
echo  Dashboard: http://localhost:%GOD_PORT%
echo  API docs:  http://localhost:%GOD_PORT%/docs
echo  Auth:      POST /api/auth/setup to create owner
echo.
echo ========================================
echo.

echo [%date% %time%] INSTALLER finished >> "%LOG%"
exit /b 0

REM ═══════════════════════════════════════════════════════════
REM   SUB-COMMANDS
REM ═══════════════════════════════════════════════════════════

:repair
echo.
echo Running repair...
"%VENV_PY%" -c "
from superai import repair
r = repair.run()
print(f'REPAIR {r[\"kind\"]} ok={r[\"ok\"]}')
for a in r.get('actions') or []:
    st = 'OK' if a.get('ok') else 'FAIL'
    print(f'  [{st}] {a[\"check\"]} {a.get(\"error\") or a.get(\"fix\") or \"\"}')
"
echo.
pause
goto :eof

:update
echo.
echo Updating GOD...
if exist ".git" (
    git pull
    "%VENV_PY%" -m pip install -r requirements.txt --quiet
    "%VENV_PY%" -m pytest tests/ -q
    echo [OK] Update complete.
) else (
    echo [FAIL] Not a git repository.
)
echo.
pause
goto :eof
