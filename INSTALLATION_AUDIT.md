# GOD — Installation Audit

Data: 2026-09-06
Commit: 51f6601 (main)
Auditor: Automated

---

## CURRENT INSTALLATION

### Linux/Mac: `setup.sh`
1. Check python3 exists
2. Check version ≥ 3.10
3. Create `.venv`
4. Upgrade pip
5. `pip install -r requirements.txt`
6. Verify 7 core modules import
7. Check project structure (8 files)
8. Create data dirs: sandbox, projects, gods, voice, auth, qdrant
9. Check .env exists
10. Run `pytest tests/ -q`

### Windows: `setup.bat`
Same flow, uses `python`/`python3` fallback.
Uses `unittest` (NOT pytest) — diverges from Linux.
Hardcodes `"OK (88/89, 1 env-dependent)"` — stale, real count is 252.

### Issues Found
- `setup.bat` uses `unittest` while `setup.sh` uses `pytest` — inconsistent
- `setup.bat` hardcodes test count "88/89" — stale
- `setup.bat` hardcodes `"Tests: OK (88/89, 1 env-dependent)"` in final output
- No version pinning in `requirements.txt` — `pip install latest` on every run
- No `requirements-lock.txt` for reproducibility
- No `data/auth` dir creation in `setup.bat` (only in `setup.sh`)
- No `data/qdrant` dir creation in `setup.bat` (only in `setup.sh`)

---

## CURRENT STARTUP

### `god.sh start` / `god.bat start`
```
uvicorn server:app --host 127.0.0.1 --port 8000
```

On startup, `server.py` lifespan:
1. `compute.start_local_worker()` — starts in-process worker
2. `tq.heartbeat(compute.LOCAL_ID)` — heartbeat
3. `aios.boot()` — OS kernel init
4. `auth.init()` — load auth from JSON files
5. `_ensure_flags()` — enable 8 critical feature flags

### Issues Found
- Port 8000 is hardcoded — no config, no env var
- No port conflict detection before start
- No PID file — stop must guess process
- No `--reload` option for dev mode
- LAN mode (`start-lan`) binds `0.0.0.0` — security concern if firewall off

---

## CURRENT SHUTDOWN

### `god.sh stop`
```bash
pkill -f "uvicorn server:app"
```
Safe — only kills matching process.

### `god.bat stop`
```bat
taskkill /f /im python.exe /fi "WINDOWTITLE eq *uvicorn*"
taskkill /f /im python3.exe /fi "WINDOWTITLE eq *uvicorn*"
```

**P0 — CRITICAL**: Uses `/f /im python.exe` which can kill ANY Python process, not just GOD. The `/fi "WINDOWTITLE eq *uvicorn*"` filter is unreliable on Windows (many terminals don't set WINDOWTITLE).

---

## CURRENT DEPENDENCIES

### Python (requirements.txt)
```
fastapi          — web framework
uvicorn[standard] — ASGI server
pydantic         — data models
pyyaml           — config parsing
httpx            — HTTP client
tiktoken         — token counting (OpenAI)
numpy            — math
scikit-learn     — ML (embeddings fallback)
lxml             — XML parsing
qdrant-client    — vector DB (embedded mode)
fastembed        — neural embeddings
onnxruntime      — inference (fastembed dep)
edge-tts         — TTS (optional)
```

### External Requirements
- Python ≥ 3.10
- Git (for update/clone)
- Internet (for API providers, pip install)
- No Docker required
- No Node.js required
- No GPU required (works in CPU/API mode)

### Issues Found
- No version pinning — any version can be installed
- `fastembed` + `onnxruntime` are heavy (~500MB) — installed even in MINIMAL mode
- `lxml` requires C compiler on some Windows setups — potential install failure
- No `requirements-minimal.txt` for lightweight installs
- `qdrant-client` pulls in Rust binary — can fail on some Windows configs

---

## CURRENT CONFIGURATION

### `.env` — API Keys
11 API keys configured:
- Groq, Cerebras, Anthropic, OpenRouter, Inference.net, Z.ai, Google, NVIDIA, Mistral, SambaNova, Cohere

### `config.yaml` — Runtime Config
- Budgets (agent, daily, project, session, task)
- Cost tracking
- Feature flags (10 flags)
- Governor settings (ECO/NORMAL/PERFORMANCE)
- PC node info
- Thresholds

### Issues Found
- No `.env.example` in repo — new users don't know which keys to set
- No interactive config wizard
- No validation of API key format at startup
- `config.yaml` has live data (feature_flags_meta) — mixed config/state

---

## CURRENT DATA LOCATIONS

| Path | Content | Size |
|------|---------|------|
| `data/spine.db` | SQLite: 17 tables (events, tasks, cache, memory, etc.) | 7.2 MB |
| `data/auth/users.json` | User accounts (hashed passwords) | 772 B |
| `data/auth/sessions.json` | Active sessions | 154 KB |
| `data/auth/audit.jsonl` | Audit log | 661 KB |
| `data/auth/approvals.json` | Pending approvals | 94 KB |
| `data/auth/overrides.json` | Governor overrides | 78 KB |
| `data/gods/master.json` | Active GOD profile | ~2 KB |
| `data/projects/` | Generated sites | varies |
| `data/qdrant/` | Vector DB storage | varies |
| `data/sandbox/` | Temp code execution | varies |
| `data/voice/` | TTS audio cache | varies |
| `.env` | API keys (gitignored) | ~2 KB |
| `config.yaml` | Runtime config | ~3 KB |

### Issues Found
- No backup mechanism
- No migration system for schema changes
- `data/spine.db-wal` and `data/spine.db-shm` in repo (SQLite WAL mode artifacts)
- Auth files grow unbounded (audit.jsonl = 661KB and growing)
- No log rotation for audit.jsonl

---

## CURRENT TEST SYSTEM

| File | Tests | Status |
|------|-------|--------|
| `tests/test_core.py` | 164 | PASS |
| `tests/test_security.py` | 44 | PASS |
| `tests/test_security_p2.py` | 44 | PASS |
| **Total** | **252** | **252/252 PASS** |

### Issues Found
- `setup.bat` runs `unittest` not `pytest` — wrong command
- `setup.bat` shows "88/89" — stale count
- No E2E test (start server → send request → verify response)
- No installation test
- No Windows-specific test

---

## CURRENT PROBLEMS

### P0 — Bloqueia instalação/utilização

| # | Problem | Impact |
|---|---------|--------|
| 1 | `god.bat stop` uses `taskkill /f /im python.exe` — kills ALL Python processes | Data loss, other apps killed |
| 2 | `setup.bat` uses `unittest` not `pytest` — tests won't run correctly | Install verification fails |
| 3 | No `.env.example` — new users don't know what to configure | Can't configure providers |

### P1 — Problema sério

| # | Problem | Impact |
|---|---------|--------|
| 4 | Port 8000 hardcoded — no env var, no config | Can't run multiple instances |
| 5 | No version pinning in requirements.txt | Non-reproducible installs |
| 6 | `setup.bat` hardcodes "88/89 tests" — stale | Misleading install output |
| 7 | `setup.bat` missing `data/auth` and `data/qdrant` dir creation | Auth/qdrant may fail |
| 8 | `fastembed` + `onnxruntime` installed always (~500MB) | Slow install, not needed for API mode |

### P2 — Problema moderado

| # | Problem | Impact |
|---|---------|--------|
| 9 | No PID file — stop must guess process | Unreliable stop |
| 10 | No port conflict detection | Start fails silently |
| 11 | No log directory or log rotation | Disk fills up |
| 12 | No `requirements-minimal.txt` | Can't do lightweight install |
| 13 | No backup mechanism | Data loss risk |
| 14 | No installation manifest | Doctor can't verify install |
| 15 | `config.yaml` mixes config and runtime state | Hard to reset cleanly |

### P3 — Melhoria

| # | Problem | Impact |
|---|---------|--------|
| 16 | No interactive config wizard | Manual .env editing |
| 17 | No E2E test | Can't verify full flow |
| 18 | No GPU detection | Misleading for GPU users |
| 19 | No `--dev` mode with auto-reload | Slow dev iteration |
| 20 | No `GOD_UPDATE` mechanism | Manual git pull |
| 21 | No `GOD_BACKUP` mechanism | Manual copy |
| 22 | No `GOD_UNINSTALL` mechanism | Manual cleanup |
| 23 | No installation manifest.json | Can't track what's installed |
| 24 | LAN mode has no firewall check | Security risk |
| 25 | Audit log grows unbounded | Disk usage |

---

## SUMMARY

| Category | Count |
|----------|-------|
| P0 — Critical | 3 |
| P1 — Serious | 5 |
| P2 — Moderate | 7 |
| P3 — Improvement | 10 |
| **Total** | **25** |

### Good
- Clean architecture (server.py + worker.py + superai/)
- Comprehensive API (90 endpoints)
- Good test coverage (252 tests, 0 failures)
- Auth system with RBAC, sessions, audit
- Feature flags, evolution, observability
- SQLite embedded (no external DB)
- Qdrant embedded (no external vector DB)
- Works without GPU
- Works in offline/API mode

### Needs Work
- Windows installer is fragile (stop kills all Python, wrong test runner)
- No reproducibility (no version pinning)
- No backup/update/uninstall mechanisms
- No installation verification (manifest, doctor)
- No E2E testing
- Heavy default install (fastembed + onnxruntime)

---

## NEXT: PHASE B — Implementation

Ready to implement: Detection, Preflight, Installer

Target: `GOD_INSTALLER.bat` — single entry point for Windows installation.
