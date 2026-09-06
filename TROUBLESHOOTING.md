# GOD — Troubleshooting

## Installation

### Python not found
```
[FAIL] Python not found
```
**Fix:** Install Python 3.10+ from https://www.python.org/downloads/
- Windows: Check "Add Python to PATH"
- Linux: `sudo apt install python3 python3-venv python3-pip`

### Python version too old
```
[FAIL] Python 3.10+ required. Found: 3.9.x
```
**Fix:** Install Python 3.10+ alongside existing Python.

### pip install fails
```
[FAIL] Failed to install dependencies
```
**Fix:**
1. Check internet connection: `ping pypi.org`
2. Try minimal install: `pip install -r requirements-minimal.txt`
3. If lxml fails on Windows: install Visual C++ Build Tools

### Venv corrupted
```
[FAIL] Virtual environment corrupted
```
**Fix:**
```bash
rm -rf .venv
./god-installer.sh  # or GOD_INSTALLER.bat
```

---

## Starting

### Port already in use
```
[FAIL] Port 8000 is already in use
```
**Fix:**
```bash
# Use a different port
GOD_PORT=9000 ./god.sh start

# Or stop the existing process
./god.sh stop
```

### GOD fails to start
```
[FAIL] GOD failed to start
```
**Fix:**
```bash
# Check logs
tail -20 logs/god.log

# Run doctor
./god.sh doctor

# Run repair
./god.sh repair
```

### No .env file
```
[WARN] No .env file found
```
**Fix:**
```bash
# Use the config wizard
./god.sh config

# Or copy the example
cp .env.example .env
# Edit .env with your API keys
```

---

## Running

### No LLM responses (offline mode)
GOD works in offline mode without API keys, but chat won't get LLM responses.

**Fix:** Add at least one API key to `.env`:
```bash
# Free, fast:
GROQ_API_KEY=gsk_...
```

### Tests fail after update
```
[WARN] Tests failed after update
```
**Fix:** Update automatically rolls back. If not:
```bash
git log --oneline -5  # Find working commit
git checkout <commit>
pip install -r requirements.txt
```

### Database locked
```
database is locked
```
**Fix:** Another GOD instance may be running.
```bash
./god.sh stop
./god.sh start
```

---

## GPU

### GPU not detected
```
[INFO] No NVIDIA GPU detected
```
**Normal:** GOD works without GPU in API/CPU mode.
GPU is only needed for local model inference (Ollama).

---

## Windows-specific

### taskkill kills wrong process
**Fixed:** GOD now uses PID-based process management.
Update to latest: `git pull`

### setup.bat uses wrong test runner
**Fixed:** GOD now uses pytest consistently.
Update to latest: `git pull`

### Paths with spaces
GOD handles paths with spaces. If issues:
```bat
set "GOD_DIR=C:\My Apps\GOD"
```

---

## Recovery

### Full reinstall (preserving data)
```bash
# Backup first
./god.sh backup

# Remove application
./god.sh uninstall  # Choose option 2

# Reinstall
./god-installer.sh
```

### Restore from backup
```bash
# List backups
ls backups/

# Restore manually
cp backups/YYYY-MM-DD_HH-MM-SS/.env .env
cp backups/YYYY-MM-DD_HH-MM-SS/config.yaml config.yaml
cp -r backups/YYYY-MM-DD_HH-MM-SS/data/* data/
```

---

## Getting Help

1. Run `./god.sh doctor` — 12 diagnostic checks
2. Run `./god.sh repair` — 11 auto-fix checks
3. Check `logs/god.log` — detailed server logs
4. Check `logs/installer.log` — installation logs
