@echo off
echo === FIX GIT PACK LOCK ===
echo.

echo 1. Killing all git processes...
taskkill /F /IM git.exe 2>nul
taskkill /F /IM python.exe 2>nul
timeout /t 2 /nobreak >nul

echo 2. Cleaning stale git locks...
cd /d D:\APPS\GOD
del /f /q .git\objects\pack\*.idx 2>nul
del /f /q .git\objects\pack\*.pack 2>nul
del /f /q .git\index.lock 2>nul
del /f /q .git\config.lock 2>nul

echo 3. Fetching fresh...
git fetch origin main

echo 4. Resetting to latest...
git reset --hard origin/main

echo.
echo === DONE ===
echo Check: git log --oneline -5
pause
