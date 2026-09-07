# GOD — Análise Crítica de Melhorias
**Commit:** `303d4ff` | **Data:** 2026-09-07 | **Método:** Busca profunda automatizada + revisão manual

---

## LEGENDA
- 🔴 CRÍTICO — afecta estabilidade/segurança agora
- 🟠 ALTO — impacto real em produtividade/manutenção
- 🟡 MÉDIO — melhoria técnica importante
- 🟢 BAIXO — polish / nice-to-have

---

## 1. ESTATÍSTICAS DO CÓDIGO

| Métrica | Valor | Veredicto |
|---|---|---|
| Total Python | 18.476 linhas (57 ficheiros) | Aceitável |
| server.py | 1.551 linhas, **139 funções** | ⚠️ Oversized |
| index.html | 147KB (94KB JS inline) | ⚠️ Devia ser separado |
| `except: pass` | **214 ocorrências** | 🔴 MUITO |
| Threads daemon | 6 threads sem tracking | 🟠 Risco |
| Global mutable state | 30+ variáveis globais | 🟠 Fragilidade |
| httpx.Client | 6 clientes persistentes | ✅ OK |
| Profundidade máx | 36 espaços (providers.py:294) | 🟡 Nesting |

---

## 2. MELHORIAS CRÍTICAS 🔴

### M-01: 214 `except: pass` silenciosos
**Ficheiro:** Todo o repo
**Problema:** Erros são engolidos silenciosamente. Quando algo falha, não há diagnóstico.
**Exemplo:**
```python
# runtime.py — se o learner falha, ninguém sabe
try:
    from .autonomous_learner import start as learner_start
    learner_start()
except Exception:
    pass  # ← 214 destes
```
**Solução:** Logging mínimo — `log.debug("component X failed: %s", e)` em vez de `pass`. Não precisa ser todos — os mais críticos (boot, providers, auth) devem logar.

### M-02: 6 httpx.Client sem cleanup
**Ficheiro:** providers.py, websearch.py, github.py, news_connector.py, site_aggregator.py, routing.py
**Problema:** Clientes httpx persistentes nunca fechados. Em shutdown gracioso, podem deixar conexões abertas.
**Solução:** Adicionar `atexit` handler ou usar o `lifespan` do FastAPI para fechar todos no shutdown.

### M-03: Threads daemon sem tracking
**Ficheiro:** autonomous_learner, idle_worker, knowledge_auditor, observer, compute, runtime
**Problema:** 6 threads daemon que correm em background sem forma de verificar se estão vivas ou de as parar gracefulmente. Se crasham, ninguém sabe.
**Solução:** Registry central de threads com health check.

### M-04: server.py com 139 funções / 1.551 linhas
**Problema:** Um único ficheiro com todas as rotas, middleware, modelos Pydantic, startup/shutdown, e lógica de negócio. Difícil de navegar, testar e manter.
**Solução (gradual):** Separar em módulos:
- `server_routes.py` — rotas API
- `server_middleware.py` — middleware e auth
- `server_models.py` — Pydantic models
- `server.py` — só app setup + lifespan

---

## 3. MELHORIAS ALTAS 🟠

### M-05: Global mutable state (30+ variáveis)
**Ficheiro:** autonomous_learner, idle_worker, knowledge_auditor, embed, feature_flags, providers, etc.
**Problema:** Variáveis como `_running = False`, `_cycle_count = 0`, `_embed_cache = {}` são globais mutáveis. Em testes, estes valores "vazam" entre testes. Em produção, tornam o estado difícil de rastrear.
**Solução:** Classes com estado encapsulado (lazy singleton pattern).

### M-06: index.html com 94KB de JS inline
**Problema:** Todo o JS do frontend está num único `<script>` inline. Não há caching, não há minificação, não há source maps, impossível de testar unitariamente.
**Solução:** Mover JS para `static/app.js`, CSS para `static/style.css`. O server já serve `index.html` — servir ficheiros estáticos é trivial com `StaticFiles`.

### M-07: Não há graceful shutdown das threads
**Problema:** Quando o server para (Ctrl+C), as 6 threads daemon são mortas abruptamente. Se estiverem a meio de uma escrita em SQLite, podem corromper dados.
**Solução:** Sinalizar `_running = False` e dar timeout de 5s para cada thread terminar.

### M-08: Profundidade de nesting excessiva
**Ficheiro:** autonomous_learner (32), runtime_protection (37), routing (32)
**Problema:** Funções com 6+ níveis de indentação são difíceis de ler e manter.
**Solução:** Extrair helper functions com early returns.

---

## 4. MELHORIAS MÉDIAS 🟡

### M-09: Magic numbers espalhados
**Exemplo:** `timeout=15.0`, `max_tokens=150`, `limit=5`, `[:5000]`, `[:3000]` — todos hardcoded.
**Solução:** Constantes nomeadas no topo do módulo ou em `config.py`.

### M-10: Cache de embeddings sem eviction strategy
**Ficheiro:** embed.py — LRU cache de 1024 entradas
**Problema:** O cache cresce até1024 mas nunca encolhe. Em máquinas com pouca RAM, pode ser problemático.
**Solução:** Adicionar `cache_stats()` ao health check e permitir configuração via env var.

### M-11: Knowledge auditor sem protecção contra loops
**Ficheiro:** knowledge_auditor.py — `_run_audit_cycle` corre a cada120s
**Problema:** Se o `store.mem_search("")` retornar muitos resultados, o ciclo pode demorar mais que120s e acumular.
**Solução:** Lock ou timestamp check — não correr se o ciclo anterior ainda não terminou.

### M-12: Idle worker pesquisa tópicos hardcoded
**Ficheiro:** idle_worker.py
**Problema:** Se não há tracked topics nem queries recentes, usa `["inteligência artificial 2026", "python machine learning", ...]` hardcoded.
**Solução:** Buscar trending topics do site aggregator ou do cache de memória fina.

### M-13: Store.py — sem connection pooling
**Ficheiro:** store.py — `_get_conn()` cria nova conexão SQLite por chamada
**Problema:** SQLite é leve, mas criar conexão por operação é desperdício.
**Solução:** Connection com `check_same_thread=False` reutilizada (já é parcialmente feito com `_conn`).

### M-14: CORS muito permissivo
**Ficheiro:** server.py — `allow_origins=["http://localhost:*", "http://127.0.0.1:*"]`
**Problema:** Wildcard port não funciona como esperado no CORSMiddleware do FastAPI. Mas `allow_methods=["*"]` e `allow_headers=["*"]` são demasiado permissivos.
**Solução:** Listar métodos e headers explícitos.

---

## 5. MELHORIAS BAIXAS 🟢

### M-15: Version hardcoded
**Ficheiro:** server.py — `version="7.4.0"`
**Solução:** Extrair de `pyproject.toml` ou git tag.

### M-16: Sem `.editorconfig` ou `ruff.toml`
**Problema:** Indentação mista (2, 4, 8 espaços), linhas longas sem limite.
**Solução:** Adicionar `ruff.toml` com regras mínimas.

### M-17: Testes sem fixtures reutilizáveis
**Problema:** Cada teste cria o seu próprio `auth.create_owner()`. Fixtures partilhadas reduziriam duplicação.
**Solução:** Expandir `conftest.py` com fixtures de auth, store, etc.

---

## 6. QUICK WINS (implementáveis agora)

| # | Melhoria | Esforço | Impacto |
|---|---|---|---|
| M-01 | Log em vez de `except: pass` (20 mais críticos) | 30min | 🔴 Alto |
| M-07 | Graceful shutdown das threads | 20min | 🟠 Alto |
| M-02 | httpx cleanup no shutdown | 10min | 🟡 Médio |
| M-13 | Evitar criação excessiva de conexões SQLite | 15min | 🟡 Médio |
| M-06 | Mover JS para ficheiro separado | 45min | 🟠 Alto |
| M-14 | CORS explícito | 10min | 🟡 Médio |

---

## 7. NÃO RECOMENDADO (complexidade sem benefício)

- ❌ Kubernetes / microservices — GOD é local-first
- ❌ Redis — SQLite é suficiente
- ❌ Migrar para TypeScript — JS funciona, não vale o esforço
- ❌ ORM (SQLAlchemy) — queries são simples, ORM é overkill
- ❌ GraphQL — REST é suficiente para este caso
