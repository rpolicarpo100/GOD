# GOD

Inteligência viva. Feminino. **Não** é uma demo de agentes fictícios.

GitHub: [rpolicarpo100/GOD](https://github.com/rpolicarpo100/GOD) · Roadmap: [ROADMAP.md](ROADMAP.md)

## Instalação (3 passos)

```bash
# 1. Clone
git clone git@github.com:rpolicarpo100/GOD.git
cd GOD

# 2. Setup (Linux/Mac)
chmod +x setup.sh god.sh
./setup.sh

# 2. Setup (Windows)
setup.bat

# 3. Start
./god.sh start          # Linux/Mac
god.bat start           # Windows
```

Depois abre: **http://localhost:8000**

## API Keys

Cria um ficheiro `.env` na raiz:

```env
# Gratuitos (recomendados)
GROQ_API_KEY=gsk_...
CEREBRAS_API_KEY=csk-...
GOOGLE_API_KEY=AI...
OPENROUTER_API_KEY=sk-or-...
NVIDIA_API_KEY=nvapi-...
SAMBANOVA_API_KEY=...
MISTRAL_API_KEY=...

# Opcionais
ZAI_API_KEY=...
INFERENCE_API_KEY=sk-inference-...

# Pago (HARDCORE MODE)
ANTHROPIC_API_KEY=sk-ant-...
```

Sem `.env`, GOD corre em modo OFFLINE (tools only, sem LLM).

## O que faz

| Feature | Estado | Descrição |
|---------|--------|-----------|
| **Chat** | ✅ | LLM com 10 providers (Groq, Cerebras, Gemini, OpenRouter, NVIDIA, SambaNova, Mistral, Z.ai, Inference.net, Claude) |
| **Voice (TTS)** | ✅ | Microsoft Edge TTS, 9 idiomas (PT, EN, ES, FR, DE) |
| **Web Search** | ✅ | DuckDuckGo + SearXNG |
| **Semantic Cache** | ✅ | FastEmbed neural — paráfrases match cached results |
| **Cost Routing** | ✅ | Free tier primeiro, fallback automático |
| **Token Intelligence** | ✅ | Pricing CALCULATED, rate limiting por provider |
| **Missions** | ✅ | Objectivos persistentes em SQLite |
| **Task Graph** | ✅ | Dependências + paralelismo (inflight=2) |
| **Validator** | ✅ | 12 check types |
| **Third Eye** | ✅ | Pipeline criticism (10 checks) |
| **Evolution** | ✅ | Auto-evolve LOW/MEDIUM risk experiments |
| **Governor** | ✅ | Security limits, strict mode |
| **GOD Profiles** | ✅ | Perfis especializados com capabilities subset |
| **Runtime Protection** | ✅ | GOD Object anti-pattern detection |
| **Feature Flags** | ✅ | 10 flags, risk-classified |
| **Health & Readiness** | ✅ | Liveness + readiness + diagnostics |
| **Rate Limiting** | ✅ | Per-provider quota protection |

## Providers (10/11)

| Tier | Provider | Custo | Modelos |
|------|----------|-------|---------|
| **PRIMARY** | Groq | $0 | qwen3.8, allam-2-7b |
| **PRIMARY** | Cerebras | $0 | qwen-3.8-27b, gemma-4-31b |
| **PRIMARY** | Claude | $0.003/1K | claude-opus-5, claude-sonnet-5 |
| **SECONDARY** | Gemini | $0 | gemini-2.5-flash, gemini-2.5-pro |
| **SECONDARY** | OpenRouter | $0 | openai/gpt-6-astra |
| **SECONDARY** | NVIDIA NIM | $0 | DeepSeek, Llama, Nemotron (81 models) |
| **SECONDARY** | Mistral | $0 | codestral-2508 |
| **SECONDARY** | Z.ai | $0 | glm-4.5 |
| **SECONDARY** | Inference.net | $0 | claude-fable-5 |
| **BRAINSTORMING** | SambaNova | $0 | DeepSeek-V3.1, Llama-3.3-70B |

## Comandos

```bash
./god.sh start       # Iniciar servidor
./god.sh stop        # Parar servidor
./god.sh status      # Verificar estado
./god.sh test        # Correr testes
./god.sh benchmark   # Correr benchmark
./god.sh doctor      # Diagnósticos
```

## Testes

```bash
python -m pytest tests/ -q
# 252/252 PASS
```

## API Endpoints

```
POST /api/chat                    # Chat
POST /api/system/voice/speak      # TTS
POST /api/system/websearch        # Pesquisa web
GET  /api/system/state            # Estado do sistema
GET  /api/system/capabilities     # Capacidades
GET  /api/system/flags            # Feature flags
GET  /api/system/experiments      # Evolution experiments
GET  /api/system/ratelimit        # Rate limiting
GET  /api/health                  # Health check
GET  /api/metrics                 # Métricas
GET  /docs                        # Swagger UI
```

## Arquitectura

```
User → handle() → analyze(exec_mode) → cache → plan → decide
  ├── FAST: tools direct
  ├── NORMAL: inline LLM
  └── DEEP: queue → worker → LLM
```

Governor → security limits. Third Eye → pipeline criticism. Validator → result checks.
Evolution → observe/propose/auto-apply. Rate limiting → quota protection.

## Estrutura

```
superai/
  runtime.py      # handle() — entry point
  pipeline.py     # cache/mem/llm stages
  brain.py        # analyze/cache/evaluate
  routing.py      # provider routing + rate limiting
  providers.py    # 10 adapters
  evolution.py    # observe/propose/auto_evolve
  tokens.py       # pricing/cost/budget
  voice.py        # TTS (edge-tts)
  websearch.py    # DuckDuckGo + SearXNG
  ratelimit.py    # per-provider rate limiting
  feature_flags.py # 10 flags, risk-classified
  ...
```

## License

Private. Não distribuir.
