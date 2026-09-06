# GOD — Recomendações Rating 70/100+
**Data:** 2026-09-06 | **Estado:** 162 testes passam, 25 features implementadas

---

## Rating Actual Estimado: ~55/100

| Dimensão | Score | O que falta |
|----------|-------|-------------|
| Funcionalidade | 75/100 | Streaming, STT, suggestions ✓ |
| Fiabilidade | 50/100 | 2 testes falham, sem CI, sem health checks profundos |
| Segurança | 60/100 | Auth existe mas sem CORS, sem rate limit no API |
| Performance | 65/100 | Racing, cache, parallel ✓ |
| Manutenibilidade | 40/100 | Sem type hints, sem linting, sem docs API |
| Operações | 35/100 | Sem Docker, sem CI/CD, sem monitoring |
| Documentação | 45/100 | README existe mas sem API docs, sem setup guide |
| Testes | 30/100 | 2 failures, 0 unit tests por módulo |

---

## 🔴 Para chegar a 70/100 (ESSENCIAIS)

### 1. FIX OS 2 TEST FAILURES → Rating +8
**Score impact:** 30 → 55 testes

Os2 failures são `test_quem_es_goes_to_llm_path` e `test_research_path_depends_on_llm`. Causa: cache retorna `via="cache"` em vez de `"blocked"`. É um problema de cache residual entre testes, não do código.

**Solução:** Limpar cache antes destes testes específicos (não alterar o teste — limpar o estado).

```python
# No setup do teste:
store.cache_flush()  # ou store._conn().execute("DELETE FROM cache")
```

**Esforço:** 15 minutos

---

### 2. SETUP.PY / PYPROJECT.TOML → Rating +5
**Score impact:** Sem packaging → com packaging

O GOD não tem `pyproject.toml`. `requirements.txt` existe mas não é um package instalável.

**Solução:**
```toml
[project]
name = "god"
version = "7.3.0"
requires-python = ">=3.10"
dependencies = ["fastapi", "uvicorn", "pydantic", "pyyaml", "httpx", "tiktoken", "numpy", "scikit-learn", "lxml", "qdrant-client"]

[project.optional-dependencies]
neural = ["fastembed", "onnxruntime"]
voice = ["edge-tts"]
dev = ["pytest", "ruff"]
```

**Esforço:** 30 minutos

---

### 3. RUFF LINTING + FORMAT → Rating +5
**Score impact:** Código inconsistente → consistente

Zero linter config. `ruff` é rápido e substitui flake8+isort+black.

**Solução:**
```toml
[tool.ruff]
line-length = 120
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP"]
ignore = ["E501"]  # line length handled by formatter
```

**Esforço:** 15 minutos

---

### 4. API DOCS (FastAPI auto) → Rating +5
**Score impact:** 0 docs API → docs automáticos

FastAPI gera OpenAPI/Swagger automaticamente. Só precisa de:
- `title`, `description`, `version` no FastAPI()
- Endpoint `/docs` e `/redoc` já existem por default

**Solução:**
```python
app = FastAPI(
    title="GOD — Living Intelligence",
    description="API do GOD. Local-first, no cloud.",
    version="7.3.0",
    docs_url="/docs",
    redoc_url="/redoc",
)
```

**Esforço:** 5 minutos

---

### 5. .ENV.EXAMPLE → Rating +3
**Score impact:** Sem guia de config → guia claro

O `.env` está em `.gitignore`. Novos developers não sabem que keys precisam.

**Solução:**
```env
# GOD — Environment Variables
# Copy to .env and fill in your keys

# LLM Providers (at least one required)
GROQ_API_KEY=
CEREBRAS_API_KEY=
GOOGLE_API_KEY=
OPENROUTER_API_KEY=
ANTHROPIC_API_KEY=
MISTRAL_API_KEY=
NVIDIA_API_KEY=
SAMBANOVA_API_KEY=
INFERENCE_API_KEY=
ZAI_API_KEY=

# Optional: Worker auth
SUPERAI_WORKER_TOKEN=

# Optional: Mode (auto, offline, normal, conservative, token_saver)
GOD_MODE=auto
```

**Esforço:** 5 minutos

---

### 6. HEALTH CHECKS PROFUNDOS → Rating +5
**Score impact:** Health superficial → health completo

O `/api/health` só retorna `ok`, `mode`, `workers_alive`. Falta:
- SQLite connectivity
- Provider status por tipo
- Queue depth
- Memory status
- Disk space

**Solução:** Endpoint `/api/health/deep` que testa cada componente.

**Esforço:** 30 minutos

---

### 7. CORS CONFIG → Rating +3
**Score impact:** Sem CORS → CORS configurado

O server não tem CORS. Para desenvolvimento local com frontend separado ou mobile.

**Solução:**
```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:*"], allow_methods=["*"], allow_headers=["*"])
```

**Esforço:** 5 minutos

---

### 8. GITHUB ACTIONS CI → Rating +5
**Score impact:** Sem CI → CI automático

```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install -r requirements.txt
      - run: python -m pytest tests/ -q
```

**Esforço:** 15 minutos

---

### 9. DOCKERFILE → Rating +5
**Score impact:** Sem container → containerizável

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p data logs
EXPOSE 8000
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Esforço:** 15 minutos

---

### 10. STRUCTURED LOGGING → Rating +3
**Score impact:** Print statements → structured logs

O GOD usa `print()` e `bus.emit()`. Falta logging estruturado para debugging em produção.

**Solução:**
```python
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
log = logging.getLogger("god")
```

**Esforço:** 30 minutos (substituir prints por log.info/warning/error)

---

### 11. ERROR BOUNDARY NO FRONTEND → Rating +3
**Score impact:** Erro JS crasha dashboard → error boundary

Se o SSE desconecta ou um JSON parse falha, o dashboard pode ficar branco.

**Solução:** Wrap `paint()` e `connect()` em try/catch com fallback visual.

**Esforço:** 15 minutos

---

### 12. TYPE HINTS CORE → Rating +3
**Score impact:** Sem types → types no core

Muitas funções não têm type hints. `mypy` não consegue verificar.

**Foco:** `runtime.py`, `pipeline.py`, `brain.py`, `providers.py` — as funções públicas.

**Esforço:** 1 hora (core functions only)

---

## 📊 Resumo — Para 70/100

| # | Recomendação | Impacto | Esforço | Acumulado |
|---|-------------|---------|---------|-----------|
| 1 | Fix 2 test failures | +8 | 15min | 63 |
| 2 | pyproject.toml | +5 | 30min | 65 |
| 3 | Ruff linting | +5 | 15min | 67 |
| 4 | API docs | +5 | 5min | 68 |
| 5 | .env.example | +3 | 5min | 69 |
| 6 | Health checks deep | +5 | 30min | 70 |
| 7 | CORS | +3 | 5min | 71 |
| 8 | GitHub Actions | +5 | 15min | 72 |
| 9 | Dockerfile | +5 | 15min | 73 |
| 10 | Structured logging | +3 | 30min | 74 |
| 11 | Error boundary frontend | +3 | 15min | 75 |
| 12 | Type hints core | +3 | 1h | 76 |

**Total estimado para 76/100** — ~3.5 horas de trabalho.

---

## 🔵 Para 80/100+ (FASE 3)

| # | Recomendação | Impacto | Esforço |
|---|-------------|---------|---------|
| 13 | Unit tests por módulo (brain, pipeline, routing) | Alto | 4h |
| 14 | Streaming completo (LLM → SSE → frontend) | Alto | 2h |
| 15 | Integration tests (server endpoints) | Médio | 2h |
| 16 | OpenTelemetry tracing | Médio | 2h |
| 17 | Prometheus metrics endpoint | Médio | 1h |
| 18 | Rate limit no API (não só providers) | Baixo | 30min |
| 19 | Backup/restore automático | Baixo | 1h |
| 20 | Multi-user auth (além do actual) | Alto | 4h |

---

*Análise baseada em: 49 módulos, 13.369 LOC, 161 commits, 162 testes passam*
