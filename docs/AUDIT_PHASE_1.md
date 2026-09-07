# GOD 8.0 — PHASE 1 AUDIT

**Commit:** `7d6ed61` (HEAD main)
**Date:** 2026-09-07
**Auditor:** Automated static + manual review

---

## 1. ARCHITECTURE MAP

```
┌─────────────────────────────────────────────────────┐
│                    index.html (UI)                   │
│              ~3400 lines, inline JS+CSS              │
└────────────────────┬────────────────────────────────┘
                     │ HTTP
┌────────────────────▼────────────────────────────────┐
│                 server.py (1479 lines)               │
│           FastAPI — 80+ routes, no auth layer        │
│           Most endpoints: NO authentication          │
└────┬──────┬──────┬──────┬──────┬──────┬─────────────┘
     │      │      │      │      │      │
┌────▼──┐┌──▼──┐┌──▼──┐┌──▼──┐┌──▼──┐┌──▼───────────┐
│pipeline││brain││route││queue││tools││  auth.py      │
│ 450L   ││300L ││250L ││250L ││400L ││  600L         │
└───┬────┘└──┬──┘└──┬──┘└──┬──┘└──┬──┘└──────────────┘
    │        │      │      │      │
┌───▼────────▼──────▼──────▼──────▼──────────────────┐
│              providers.py (670 lines)                │
│         14 LLM providers, OpenAI-compat             │
│         httpx client, health tracking               │
└────────────────────┬───────────────────────────────┘
                     │
┌────────────────────▼───────────────────────────────┐
│              store.py + embed.py + memory_vec.py     │
│              SQLite + Qdrant + FastEmbed             │
└─────────────────────────────────────────────────────┘
```

### Module Inventory (57 .py files)

| Module | Lines | Purpose | Risk |
|--------|-------|---------|------|
| server.py | 1479 | All API routes | HIGH — oversized, no auth on most |
| pipeline.py | 450 | Core execution pipeline | HIGH |
| brain.py | 300 | LLM orchestration | MEDIUM |
| providers.py | 670 | 14 LLM providers | MEDIUM |
| tools.py | 400 | 20+ tools (fs, git, web, python) | CRITICAL |
| auth.py | 600 | Auth + sessions + approvals | HIGH |
| sandbox.py | 260 | Path/sandbox validation | CRITICAL |
| governor.py | 100 | Resource limits | MEDIUM |
| routing.py | 250 | Provider routing | MEDIUM |
| store.py | 260 | SQLite persistence | MEDIUM |
| knowledge_auditor.py | 380 | Knowledge curation | LOW |
| idle_worker.py | 250 | Background learning | LOW |
| autonomous_learner.py | 400 | Learning engine | LOW |
| network_control.py | 200 | Network policy | MEDIUM |
| rate_limit.py | 176 | Rate limiting | MEDIUM |
| ratelimit.py | 87 | **DUPLICATE** rate limiter | LOW |
| runtime.py | 700 | Boot + daemon threads | MEDIUM |
| websearch.py | 200 | Web search | MEDIUM |
| github.py | 250 | GitHub API | MEDIUM |
| news_connector.py | 120 | News API | LOW |
| site_aggregator.py | 150 | Site management | LOW |
| health.py | 180 | Health scoring | LOW |
| config.py | 100 | Config + .env loading | MEDIUM |
| embed.py | 100 | Embeddings | LOW |
| knowledge_graph.py | 220 | Knowledge graph | LOW |
| worker.py | 60 | Remote worker | LOW |
| index.html | 3400 | UI (JS+CSS inline) | MEDIUM |

---

## 2. DEPENDENCY MAP

### Python Dependencies (requirements.txt)
```
fastapi          — web framework
uvicorn[standard] — ASGI server
pydantic         — data validation
pyyaml           — config
httpx            — HTTP client
tiktoken         — token counting
numpy            — ML
scikit-learn     — ML fallback
lxml             — XML/HTML parsing
qdrant-client    — vector DB
fastembed         — neural embeddings (optional)
onnxruntime       — neural runtime (optional)
edge-tts          — TTS (optional)
```

**Missing:** `requests` (used by cohere_rerank.py — not in requirements.txt!)

### No lock file discipline
- `requirements-lock.txt` exists but doesn't match `requirements.txt`
- No `pip-compile`, no `poetry.lock`, no `pdm.lock`
- Unpinned versions: `fastapi`, `uvicorn`, `httpx`, `numpy`, etc.

---

## 3. SECURITY BOUNDARY MAP

```
┌──────────────────────────────────────────────────┐
│ TRUST ZONE: GOD Python process                    │
│                                                   │
│  ┌──────────────┐    ┌──────────────┐            │
│  │ SQLite store  │    │ JSON files   │            │
│  │ (data/god.db) │    │ (data/auth/) │            │
│  └──────────────┘    └──────────────┘            │
│                                                   │
│  ┌──────────────────────────────────────┐        │
│  │ SUBPROCESS (tools.py)                │        │
│  │  - git commands (timeout 8s)         │        │
│  │  - python exec (timeout 8s)          │        │
│  │  - NO sandbox isolation              │        │
│  └──────────────────────────────────────┘        │
│                                                   │
│  ┌──────────────────────────────────────┐        │
│  │ NETWORK (httpx)                      │        │
│  │  - LLM providers (14)                │        │
│  │  - Web search (DuckDuckGo)           │        │
│  │  - GitHub API                        │        │
│  │  - News API                          │        │
│  │  - network_control.py exists but     │        │
│  │    NOT integrated into httpx calls   │        │
│  └──────────────────────────────────────┘        │
│                                                   │
└──────────────────────────────────────────────────┘
         │
         │ HTTP (no auth on most endpoints)
         ▼
┌──────────────────────────────────────────────────┐
│ UNTRUST ZONE: Browser / Internet                  │
│  - User input (free text)                         │
│  - LLM output (untrusted)                         │
│  - Web content (untrusted)                        │
└──────────────────────────────────────────────────┘
```

### CRITICAL FINDING: network_control.py is NOT USED
The `network_control.py` module has SSRF protection logic but **nothing in `providers.py`, `websearch.py`, `github.py`, or `tools.py` imports or uses it**. All HTTP calls go through raw `httpx` without SSRF checks.

---

## 4. EXECUTION BOUNDARY MAP

### Subprocess Execution

| Location | What | Trust Level | Isolation |
|----------|------|-------------|-----------|
| `tools.py:143` | `git` commands | TRUSTED (governor-controlled) | timeout=8s, cwd=project |
| `tools.py:224` | `python` exec | **UNTRUSTED** (LLM-generated code) | timeout=8s, capture_output |
| `system.py:22` | system info | TRUSTED | timeout=10s |
| `system.py:30` | disk info | TRUSTED | timeout=10s |

### CRITICAL: Python exec in tools.py
```python
# tools.py:216-232
proc = subprocess.run(
    [sys.executable, "-c", code],
    cwd=str(root),
    capture_output=True, text=True,
    timeout=int(gov.python_timeout()),
)
```
- **No network isolation** — LLM-generated code can make HTTP requests
- **No filesystem isolation** — can read/write within working directory
- **No resource limits** — can consume memory
- **timeout=8s** — only protection

---

## 5. STATE / PERSISTENCE MAP

| State | Format | Location | Atomic? | Locking? |
|-------|--------|----------|---------|----------|
| Users | JSON | `data/auth/users.json` | NO | NO |
| Sessions | JSON | `data/auth/sessions.json` | NO | NO |
| Approvals | JSON | `data/auth/approvals.json` | NO | NO |
| Overrides | JSON | `data/auth/overrides.json` | NO | NO |
| Audit log | JSONL | `data/auth/audit.jsonl` | NO | NO |
| Config | YAML | `config.yaml` | NO | NO |
| Gods | JSON | `data/gods/*.json` | NO | NO |
| Active god | Text | `data/gods/ACTIVE` | NO | NO |
| Main DB | SQLite | `data/god.db` | YES | YES (SQLite) |
| Vector DB | Qdrant | embedded | YES | YES |
| Feature flags | YAML | `data/feature_flags.yaml` | NO | NO |

### CRITICAL: Auth state uses non-atomic JSON writes
Sessions, users, approvals, and overrides are stored in JSON files with `write_text()` — no atomic write, no locking, no corruption recovery. Concurrent requests can corrupt these files.

---

## 6. NETWORK BOUNDARY MAP

### Outbound Connections

| Target | Module | SSRF Protected? |
|--------|--------|----------------|
| LLM Providers (14) | providers.py | **NO** |
| DuckDuckGo | websearch.py | **NO** |
| GitHub API | github.py | **NO** |
| News aggregator | news_connector.py | **NO** |
| Site aggregator | site_aggregator.py | **NO** |
| OmniRoute | routing.py | **NO** |
| Qdrant | memory_vec.py | **NO** |
| Cohere API | cohere_rerank.py | **NO** |

**network_control.py exists with SSRF logic but is NOT wired into ANY HTTP client.**

---

## 7. TEST MAP

| File | Tests | What | Status |
|------|-------|------|--------|
| test_security.py | 42 | Auth, sessions, approvals | **4 FAIL** (worker auth) |
| test_security_p2.py | 50 | P2 security features | PASS |
| test_core.py | 164 | Core functionality | PASS (4 expected failures) |
| test_e2e.py | 46 | End-to-end | PASS |
| test_phase6.py | 36 | Phase 6 features | PASS |
| test_brain.py | 15 | Brain logic | PASS |
| test_routing.py | 6 | Provider routing | PASS |
| test_observer.py | 5 | Observer | PASS |
| test_store.py | 9 | SQLite store | PASS |
| test_install.py | 43 | Installation | PASS (46 skipped) |

### Missing Tests
- No SSRF tests
- No path traversal tests for tools.py
- No subprocess isolation tests
- No concurrent write tests
- No provider failure mode tests
- No SSRF private IP tests
- No SSRF metadata endpoint tests
- No command timeout cleanup tests
- No environment secret leakage tests

---

## 8. DEPLOYMENT MAP

| Method | Status | Issues |
|--------|--------|--------|
| Docker | EXISTS | Dockerfile present, not tested this session |
| Direct Python | WORKS | User runs on Windows |
| CI/CD | EXISTS | .github/workflows/test.yml |

---

## 9. KNOWN RISKS — CRITICAL

### RISK-01: No SSRF Protection (CRITICAL)
`network_control.py` has SSRF logic but it's **dead code** — not integrated into any HTTP client. LLM-generated URLs can access internal networks.

### RISK-02: Unauthenticated Endpoints (CRITICAL)
~70 of 80+ API endpoints have **NO authentication**. Only `/api/auth/*` endpoints check auth. All `/api/chat`, `/api/web/*`, `/api/github/*`, `/api/system/*` endpoints are completely open.

### RISK-03: Code Execution Without Isolation (CRITICAL)
`tools.py:tool_python()` executes LLM-generated Python code via `subprocess.run([sys.executable, "-c", code])` with only a timeout. No sandboxing, no network isolation, no filesystem restrictions beyond working directory.

### RISK-04: Non-Atomic Auth State (HIGH)
`auth.py` stores sessions, users, approvals in JSON files with `write_text()`. Concurrent requests can corrupt files, losing sessions or user data.

### RISK-05: Duplicate Rate Limiters (MEDIUM)
`rate_limit.py` (176 lines) and `ratelimit.py` (87 lines) are two separate implementations. Which one is actually used?

### RISK-06: Dead Network Control (MEDIUM)
`network_control.py` is imported nowhere except its own tests. It provides SSRF protection that is never applied.

### RISK-07: Missing Dependency (LOW)
`cohere_rerank.py` imports `requests` but it's not in `requirements.txt`.

### RISK-08: API Key Exposure (HIGH)
`.env` loading in `config.py` sets `os.environ[k] = v` — any subprocess spawned inherits ALL env vars including API keys.

### RISK-09: Broad Process Killing Recommendation (MEDIUM)
User was instructed to run `taskkill /F /IM python.exe` which kills ALL Python processes, not just GOD.

### RISK-10: <think> Tags in HTML (FIXED)
Literal think tags in JS broke HTML parser. Fixed in commit `7d6ed61`.

---

## 10. DUPLICATED SYSTEMS

1. **Rate limiters**: `rate_limit.py` vs `ratelimit.py`
2. **Web search**: `websearch.py` vs `tools.py:tool_web_search` vs `pipeline.py` web search stage
3. **News**: `news_connector.py` vs `tools.py:tool_news_search`
4. **Memory**: `store.py` mem_* vs `memory_vec.py` vectors vs `knowledge_graph.py` triples
5. **Provider health**: `providers.py:health_all()` vs `health.py:diagnostics()` vs observer

---

## 11. SUSPICIOUS CODE

1. `server.py:266-295` — `/` endpoint serves `index.html` directly via `HTMLResponse(Path("index.html").read_text())` — no caching, no security headers
2. `server.py:324` — `/api/admin/backup` — creates a ZIP of the entire data directory — **no auth check**
3. `tools.py:216` — Python exec — LLM can run arbitrary code
4. `pipeline.py:237` — `tool_exec("fs.write", ...)` — pipeline can write files via tools
5. `auth.py:291` — `SESSIONS_FILE.write_text(json.dumps(_sessions, indent=2))` — non-atomic write
6. `providers.py:664` — `_provider_requests` tracking — potential memory leak if not cleaned

---

## 12. DEAD CODE CANDIDATES

1. `superai/ratelimit.py` — duplicate of `rate_limit.py`
2. `superai/network_control.py` — SSRF logic never used
3. `superai/cohere_rerank.py` — optional feature, `requests` not in deps
4. `superai/voice.py` — optional TTS
5. Multiple RECOMMENDATIONS_*.md files — documentation artifacts

---

## 13. INCONSISTENCIES

1. Server says "Port 8000" but auto-detect finds different port — message is misleading
2. `requirements.txt` has `fastembed` and `onnxruntime` as non-optional (no marker) but comments say "(optional)"
3. `.env.example` doesn't include all providers (DeepSeek, HuggingFace, AIMLAPI, Replicate added but not in example)
4. Test failures: 4 in test_security.py (worker auth) — known but unfixed
5. Health scoring shows 45% without .env but user sees 50% — discrepancy

---

## NEXT STEPS — PHASE 2+

1. **PHASE 2 (CRITICAL)**: Wire SSRF protection into all HTTP clients
2. **PHASE 3**: Add authentication to sensitive endpoints
3. **PHASE 4**: Atomic writes for auth state
4. **PHASE 5**: Subprocess isolation improvements
5. **PHASE 6**: Consolidate rate limiters
6. **PHASE 7**: Fix failing tests
7. **PHASE 8**: Add missing security tests
8. **PHASE 9**: Docker audit
9. **PHASE 10**: Documentation update
