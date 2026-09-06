# RECOMENDAÇÕES CRÍTICAS — GOD

> Análise completa da codebase. 168 commits, ~15k LOC, 54 módulos.
> Data: 2026-09-06. Classificação: risco real, não teórico.

---

## 🔴 CRÍTICO — Podem causar perda de dados ou downtime

### 1. Erros silenciados (83 `except Exception: pass`)
**Problema:** 20+ locais com `except Exception: pass` silenciam erros reais.
Em produção, isto esconde bugs, corrupção de dados, e falhas de providers.
**Risco:** Um erro de escrita no SQLite é silenciado → dados perdidos sem ninguém saber.
**Fix:** Substituir por `except Exception as e: log.warning(...)` nos módulos críticos
(store, pipeline, routing, memory_vec). Manter `pass` apenas em módulos não-críticos
(events, cache L2).
**Prioridade:** P0. Cada `except: pass` em store.py ou pipeline.py é uma bomba relógio.

### 2. Thread safety no runtime — globals sem lock consistente
**Problema:** `runtime.py` tem 8 variáveis `global` mas o `_lock` nem sempre é usado.
`_last_pipeline`, `_conv_summary`, `_perf_history` são escritos sem lock em algumas paths.
Em ambiente multi-thread (SSE + handle() simultâneo), isto causa race conditions.
**Risco:** Leitura de `_last_pipeline` parcialmente escrito → crash no frontend ou dados corrompidos.
**Fix:** Usar `_lock` em TODAS as escritas a `_last_pipeline`, `_conv_summary`, `_perf_history`.
Ou trocar por `threading.local()` onde faz sentido.
**Prioridade:** P0. Já aconteceu (bug do streaming ter sido destruído pelo SSE).

### 3. SQLite connection per-thread — OK mas sem recovery
**Problema:** `store.py` usa `threading.local()` para connections, que é correcto.
Mas se uma connection é closed por timeout ou erro, `_get_conn()` tenta reconnect
sem verificar se a anterior está realmente fechada. Em WAL mode, isto pode
deixar locks pendurados.
**Risco:** Deadlock silencioso em carga alta.
**Fix:** Adicionar health check na connection antes de reusar. Implementar connection recycling
a cada N queries.
**Prioridade:** P1.

---

## 🟠 ALTO RISCO — Afectam fiabilidade em produção

### 4. Sem circuit breaker no routing
**Problema:** `routing.py` tenta providers sequencialmente (max 3 tries) mas não
tem circuit breaker. Se um provider está a retornar 500s consistentemente,
cada request desperdiça 5-30s a tentar antes de falhar.
O `ratelimit.py` protege quotas mas não falhas persistentes.
**Risco:** Latência 3x pior quando um provider está em degraded state.
**Fix:** Circuit breaker com estados CLOSED/OPEN/HALF-OPEN. Após 3 falhas consecutivas,
abrir circuito por 60s. Meia-porta: 1 request de teste.
**Prioridade:** P1. Impacto directo na experiência do utilizador.

### 5. Sem retry com backoff exponencial
**Problema:** `DirectAdapter.complete()` tenta até 3 providers mas sem delay entre retries.
Se todos estão overloaded (429), faz 3 requests imediatas → agrava o problema.
**Risco:** Thundering herd em providers com rate limits.
**Fix:** Backoff exponencial: 0.5s, 1s, 2s entre retries. Jitter ±20%.
**Prioridade:** P1.

### 6. Input validation mínimo no /api/chat
**Problema:** O endpoint `/api/chat` aceita qualquer string sem limite de tamanho.
Uma mensagem de 10MB seria processada pelo pipeline inteiro.
O `Form(...)` não tem `max_length`.
**Risco:** DoS por payload gigante. Memory spike.
**Fix:** `max_length=10000` no campo de texto. Truncar silenciosamente ou rejeitar com 413.
**Prioridade:** P1.

### 7. CORS completamente aberto
**Problema:** O server não tem CORS middleware configurado. FastAPI por default
permite qualquer origin. Em produção, qualquer site pode fazer requests à GOD.
**Risco:** CSRF, exfiltração de dados via browser.
**Fix:** `CORSMiddleware(allow_origins=["http://localhost:8000"], allow_methods=["*"])`.
**Prioridade:** P1 se exposto à rede; P2 se apenas local.

---

## 🟡 MÉDIO RISCO — Afectam qualidade e manutenibilidade

### 8. GOD Object residual em runtime.py
**Problema:** Apesar do refactor para `pipeline.py` e `shortcuts.py`, `runtime.py`
ainda tem ~650 linhas com 8 globals, 15 funções, e responsabilidades misturadas
(chat persistence, dialogue, LLM prompt, performance tracking, boot, snapshot).
**Risco:** Dificulta debugging e testes unitários.
**Fix:** Extrair `_dialogue()` e `_llm_prompt()` para `prompt.py`. Extrair
`_persist_chat()` e `_restore_chat()` para `chat_persistence.py`.
**Prioridade:** P2.

### 9. Dependências sem version pinning
**Problema:** `requirements.txt` não tem versões fixas (`fastapi`, não `fastapi==0.115.0`).
Uma actualização breaking do FastAPI ou qdrant-client pode partir tudo sem aviso.
**Risco:** Build não-reproduzível. Deploy silenciosamente broken.
**Fix:** Gerar `requirements-lock.txt` com `pip freeze`. Usar nos deploys.
**Prioridade:** P2.

### 10. Sem graceful shutdown
**Problema:** O server não captura SIGTERM/SIGINT para cleanup.
O Observer thread, queue workers, e Qdrant client podem ser cortados a meio de uma operação.
Apenas `memory_vec.py` tem `atexit.register(self.close)`.
**Risco:** Corrupção de dados no SQLite se shutdown durante escrita WAL.
**Fix:** Signal handler que: 1) para de aceitar requests, 2) espera requests em curso,
3) fecha connections, 4) exit.
**Prioridade:** P2.

### 11. Testes sem mocking de providers
**Problema:** Os testes existentes não fazem mock dos LLM providers.
Se um provider está down, os testes de integração falham sem ser um bug do código.
**Risco:** CI instável. Testes que passam/falham por razões externas.
**Fix:** Mock `routing.complete()` em testes não-e2e. Fixture separada para e2e.
**Prioridade:** P2.

### 12. Logging inconsistente
**Problema:** O sistema usa 3 mecanismos de logging diferentes:
1. `bus.emit()` (eventos)
2. `print()` em alguns locais
3. Python `logging` (apenas server.py)
Sem correlação entre eles. Impossível tracing de um request completo.
**Risco:** Debugging em produção é às cegas.
**Fix:** Unificar em `logging` com request_id como contexto. `bus.emit()` para UI,
`logging` para ficheiro/stdout.
**Prioridade:** P2.

---

## 🟢 MELHORIAS — Aumentam robustez mas não são bloqueantes

### 13. Embedding fallback silencioso
**Problema:** `embed.py` faz fallback de FastEmbed para HashingVectorizer
sem alertar. O sistema "funciona" mas com qualidade muito inferior
(lexical vs neural). O utilizador não sabe.
**Fix:** Log WARNING na primeira ocorrência. Expor no `/api/health`.
**Prioridade:** P3.

### 14. Knowledge graph sem TTL/eviction
**Problema:** `knowledge_graph.py` acumula triples sem limite nem expiração.
Depois de meses, a memória cresce indefinidamente.
**Fix:** TTL de 30 dias para triples. Max 1000 entries. Evict LRU.
**Prioridade:** P3.

### 15. Adaptive routing sem cold-start handling
**Problema:** `adaptive_routing.py` precisa de 3 observações antes de ter efeito.
Num sistema novo ou após restart, o routing é default (sem aprendizagem).
**Fix:** Carregar scores persistidos no boot (já temos a estrutura, falta a implementação).
**Prioridade:** P3.

### 16. Streaming endpoint não tem heartbeat
**Problema:** `/api/chat/stream` faz SSE mas não envia heartbeat. Se `handle()` demora
30+ segundos, o browser/proxy pode fechar a connection por timeout.
**Fix:** Enviar `:heartbeat\n\n` a cada 15s enquanto `handle()` está a correr.
**Prioridade:** P3.

### 17. Sem métricas Prometheus
**Problema:** O `/api/metrics` retorna JSON customizado. Ferramentas de monitorização
(Grafana, Datadog) esperam formato Prometheus.
**Fix:** Adicionar `/metrics` em formato Prometheus (counter, gauge, histogram).
**Prioridade:** P3.

---

## RESUMO EXECUTIVO

| Prioridade | Items | Esforço | Impacto |
|-----------|-------|---------|---------|
| **P0** | #1 (erros silenciados), #2 (thread safety) | 2-3h | Previne bugs silentes em produção |
| **P1** | #3 (SQLite), #4 (circuit breaker), #5 (retry), #6 (input validation), #7 (CORS) | 4-6h | Fiabilidade + segurança |
| **P2** | #8 (refactor), #9 (deps), #10 (shutdown), #11 (testes), #12 (logging) | 1-2 dias | Manutenibilidade |
| **P3** | #13-17 | 1 dia | Robustez |

**A acção mais importante agora:** #1 + #2. Substituir `except: pass` por logging em
store.py e pipeline.py, e garantir que `_last_pipeline` é sempre escrito sob lock.
São 2-3 horas de trabalho que previnem os bugs mais prováveis em produção.
