# GOD

Inteligência viva. Feminino. **Não** é uma demo de agentes fictícios.

GitHub: [rpolicarpo100/GOD](https://github.com/rpolicarpo100/GOD) · Roadmap: [ROADMAP.md](ROADMAP.md)

---

## Quick Start (3 passos)

```bash
# 1. Clone
git clone git@github.com:rpolicarpo100/GOD.git
cd GOD

# 2. Setup
# Linux/Mac:
chmod +x god-installer.sh && ./god-installer.sh
# Windows:
GOD_INSTALLER.bat

# 3. Start
./god.sh start          # Linux/Mac
god.bat start           # Windows
```

Depois abre: **http://localhost:8000**

---

## Comandos

| Comando | Descrição |
|---------|-----------|
| `start` | Iniciar servidor (localhost) |
| `start-lan` | Iniciar servidor (LAN) |
| `dev` | Modo desenvolvimento (auto-reload) |
| `stop` | Parar servidor (graceful) |
| `status` | Estado: process, server, commit, DB |
| `test` | Correr testes (252 unit + 43 install) |
| `benchmark` | Correr benchmark |
| `doctor` | 12 diagnósticos |
| `repair` | 11 verificações com auto-fix |
| `backup` | Backup selectivo + rotação |
| `update` | Pull + deps + testes (rollback se falhar) |
| `uninstall` | Remover GOD (4 opções, preserva dados) |
| `config` | Assistente de configuração interactiva |
| `gpu` | Detectar GPU |

```bash
# Porta customizada
GOD_PORT=9000 ./god.sh start
```

---

## API Keys

O instalador pergunta interactivamente. Ou cria `.env` manualmente:

```env
# Gratuitos (recomendados)
GROQ_API_KEY=gsk_...
CEREBRAS_API_KEY=csk-...
GOOGLE_API_KEY=AI...
OPENROUTER_API_KEY=sk-or-...
NVIDIA_API_KEY=nvapi-...
SAMBANOVA_API_KEY=...
MISTRAL_API_KEY=...

# Pago
ANTHROPIC_API_KEY=sk-ant-...
```

Sem `.env`, GOD corre em modo OFFLINE (tools only, sem LLM).

---

## O que faz

| Feature | Estado | Descrição |
|---------|--------|-----------|
| **Chat** | ✅ | LLM com 10 providers |
| **Voice (TTS)** | ✅ | Edge TTS, 9 idiomas |
| **Web Search** | ✅ | DuckDuckGo + SearXNG |
| **Semantic Cache** | ✅ | FastEmbed neural |
| **Cost Routing** | ✅ | Free tier primeiro, fallback automático |
| **Token Intelligence** | ✅ | Pricing CALCULATED, rate limiting |
| **Missions** | ✅ | Objectivos persistentes |
| **Task Graph** | ✅ | Dependências + paralelismo |
| **Validator** | ✅ | 12 check types |
| **Third Eye** | ✅ | Pipeline criticism (10 checks) |
| **Evolution** | ✅ | Auto-evolve LOW/MEDIUM risk |
| **Governor** | ✅ | Security limits, strict mode |
| **GOD Profiles** | ✅ | Perfis especializados |
| **Runtime Protection** | ✅ | GOD Object anti-pattern detection |
| **Feature Flags** | ✅ | 10 flags, risk-classified |
| **Auth RBAC** | ✅ | Users, sessions, audit, approvals, overrides |
| **Health** | ✅ | Liveness + readiness + diagnostics |

---

## Providers (10/11)

| Tier | Provider | Custo | Modelos |
|------|----------|-------|---------|
| **PRIMARY** | Groq | $0 | qwen3.8, allam-2-7b |
| **PRIMARY** | Cerebras | $0 | qwen-3.8-27b, gemma-4-31b |
| **PRIMARY** | Claude | $0.003/1K | claude-opus-5, claude-sonnet-5 |
| **SECONDARY** | Gemini | $0 | gemini-2.5-flash, gemini-2.5-pro |
| **SECONDARY** | OpenRouter | $0 | openai/gpt-6-astra |
| **SECONDARY** | NVIDIA NIM | $0 | DeepSeek, Llama, Nemotron |
| **SECONDARY** | Mistral | $0 | codestral-2508 |
| **SECONDARY** | Z.ai | $0 | glm-4.5 |
| **SECONDARY** | Inference.net | $0 | claude-fable-5 |
| **BRAINSTORMING** | SambaNova | $0 | DeepSeek-V3.1, Llama-3.3-70B |

---

## Testes

```bash
python -m pytest tests/ -q
# 252 unit + 43 install = 295 PASS
# 46 E2E (skip se server offline)
```

---

## API Endpoints (90)

```
POST /api/chat                      Chat
POST /api/system/voice/speak        TTS
POST /api/system/websearch          Web search
GET  /api/health                    Health check
GET  /api/state                     System state
GET  /api/system/state              Full state
GET  /api/system/capabilities       Capabilities
GET  /api/system/flags              Feature flags
GET  /api/system/experiments        Evolution
GET  /api/system/protection         Runtime protection
GET  /api/auth/status               Auth status
POST /api/auth/setup                Create owner
POST /api/auth/login                Login
GET  /v1/models                     OpenAI compat
POST /v1/chat/completions           OpenAI compat
GET  /docs                          Swagger UI
```

---

## Arquitectura

```
User → handle() → analyze(exec_mode) → cache → plan → decide
  ├── FAST: tools direct
  ├── NORMAL: inline LLM
  └── DEEP: queue → worker → LLM
```

```
server.py (FastAPI, 90 endpoints, lifespan)
  └── superai/ (48 modules)
       ├── runtime.py      handle() — entry point
       ├── pipeline.py     cache/mem/llm stages
       ├── brain.py        analyze/cache/evaluate
       ├── routing.py      provider routing
       ├── providers.py    10 adapters
       ├── evolution.py    observe/propose/auto_evolve
       ├── tokens.py       pricing/cost/budget
       ├── auth.py         RBAC, sessions, audit
       ├── repair.py       diagnostics + auto-fix
       └── health.py       liveness + readiness
```

---

## Estrutura de Ficheiros

```
GOD/
├── GOD_INSTALLER.bat   Windows installer
├── god-installer.sh    Linux/Mac installer
├── god.bat             Windows command helper
├── god.sh              Linux/Mac command helper
├── setup.bat           Windows setup (legacy)
├── setup.sh            Linux/Mac setup (legacy)
├── server.py           FastAPI server (90 endpoints)
├── worker.py           Background worker
├── config.yaml         Runtime configuration
├── .env                API keys (gitignored)
├── .env.example        Template
├── requirements.txt    Dependencies (loose)
├── requirements-lock.txt  Dependencies (pinned)
├── requirements-minimal.txt  Minimal (no fastembed)
├── index.html          Dashboard UI
├── tests/
│   ├── test_core.py         164 unit tests
│   ├── test_security.py     44 security tests
│   ├── test_security_p2.py  44 P2 security tests
│   ├── test_install.py      43 install tests
│   └── test_e2e.py          46 E2E tests
├── superai/            48 Python modules
└── data/
    ├── spine.db        SQLite (17 tables)
    ├── auth/           Users, sessions, audit
    ├── gods/           GOD profiles
    ├── qdrant/         Vector DB
    ├── sandbox/        Temp code execution
    ├── projects/       Generated sites
    └── voice/          TTS audio cache
```

---

## Requirements

- Python ≥ 3.10
- Git
- Internet (for API providers)
- No GPU required
- No Docker required
- No Node.js required

---

## License

Private. Não distribuir.
