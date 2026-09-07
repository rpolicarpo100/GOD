# GOD — Recomendações de Velocidade: Todas as Camadas
**Data:** 2026-09-07 | **Método:** Pesquisa profunda + análise do código actual

---

## ESTADO ACTUAL — Mapa de Latência

```
USER INPUT
    │
    ▼ ← ~0ms (rede local)
┌─────────────────────────┐
│ server.py /api/chat     │ ← run_in_executor (sync→thread)
│ chat_stream SSE         │   chunk_size=6, sleep=15ms
└────────┬────────────────┘
         │
    ▼────▼─────
┌─────────────┐
│ runtime.py  │ ← analyze() regex + embeddings
│ handle()    │   _llm_prompt() + _dialogue()
└────┬────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│ pipeline.run_pipeline()                                 │
│                                                         │
│  ┌──────────┐  ┌──────────┐                             │
│  │ Stage 2  │  │ Stage 3  │  ← PARALELO (ThreadPool)    │
│  │ CACHE    │  │ MEMORY   │                             │
│  │ ~1-5ms   │  │ ~5-50ms  │                             │
│  └──────────┘  └──────────┘                             │
│       │              │                                   │
│       ▼              ▼                                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ Stage 4  │→ │ Stage 5  │→ │ Stage 6  │              │
│  │ FIREWALL │  │ PLAN     │  │ TOOLS/LLM│              │
│  │ ~1ms     │  │ ~1ms     │  │ 500-5000ms│              │
│  └──────────┘  └──────────┘  └──────────┘              │
│                                     │                   │
│                                     ▼                   │
│                              ┌──────────┐               │
│                              │ ThirdEye │               │
│                              │ ~5-20ms  │               │
│                              └──────────┘               │
└─────────────────────────────────────────────────────────┘
```

**Gargalos identificados:**
1. **LLM call (500-5000ms)** — 90%+ do tempo total
2. **Embedding computation (10-50ms)** — FastEmbed ONNX
3. **Memory search (5-50ms)** — SQLite + Qdrant
4. **SSE streaming ( artificial delay)** — chunk_size=6, sleep=15ms
5. **Pipeline overhead (5-30ms)** — stages, analysis, scoring

---

## CAMADA 1: SERVIDOR E SERVING (server.py)

### S-01: ORJSON Response Class — +4-13% throughput
**Impacto:** 🟡 Médio | **Esforço:** 5min | **Risco:** Baixo

O server.py usa `json.dumps` padrão. O `orjson` é 4-13x mais rápido para serialização.

```python
# Adicionar ao server.py
from fastapi.responses import ORJSONResponse

# No endpoint /api/chat e /api/chat/stream, usar:
@app.post("/api/chat", response_class=ORJSONResponse)
```

### S-02: SSE Streaming Real — percebido 3-5x mais rápido
**Impacto:** 🟠 Alto | **Esforço:** 30min | **Risco:** Médio

O SSE actual corre `handle()` inteiro em `run_in_executor`, espera que termine, DEPOIS envia chunks de6 chars com `sleep(15ms)`. Isto é falso streaming — o utilizador espera o tempo total + tempo de "streaming".

**Solução:** Stream tokens do LLM em tempo real via SSE:
- Modificar `routing.complete()` para suportar streaming
- Enviar tokens ao frontend à medida que chegam
- TTFT (Time To First Token) < 500ms vs actuais 2-5s

### S-03: GZip Middleware — +30-50% em payloads grandes
**Impacto:** 🟡 Médio | **Esforço:** 2min | **Risco:** Baixo

```python
from fastapi.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=500)
```

### S-04: Async Chat Endpoint — evitar thread pool overhead
**Impacto:** 🟡 Médio | **Esforço:** 1h | **Risco:** Médio

O `chat_stream` usa `run_in_executor` para chamar `handle()` síncrono. Se convertermos o pipeline para async (pelo menos os I/O parts), eliminamos o overhead do thread pool.

---

## CAMADA 2: PIPELINE (pipeline.py)

### P-01: Cache + Memory em paralelo — já feito ✅
O `concurrent.futures.ThreadPoolExecutor` já corre cache e memory em paralelo.

### P-02: Embeddings batch para memory search
**Impacto:** 🟠 Alto | **Esforço:** 30min | **Risco:** Baixo

Actualmente, cada vector search faz `embed(query)` separadamente. Com `embed_batch()`, podemos fazer uma chamada só para todas as queries do pipeline.

### P-03: Pipeline stage timing — já feito ✅
O `_mark()` já mede cada stage.

### P-04: Evitar re-análise em cache hits
**Impacto:** 🟡 Médio | **Esforço:** 15min | **Risco:** Baixo

O `brain.analyze()` corre SEMPRE, mesmo quando o cache vai dar hit. Podemos fazer cache lookup ANTES da análise para queries repetidas.

### P-05: Context pack optimization — truncar mais cedo
**Impacto:** 🟡 Médio | **Esforço:** 15min | **Risco:** Baixo

O `context_pack()` envia até5 memórias de 240 chars = 1200 chars. Para queries simples,2 memórias bastam.

---

## CAMADA 3: SQLITE (store.py)

### DB-01: mmap_size — reduzir syscalls
**Impacto:** 🟠 Alto | **Esforço:** 2min | **Risco:** Baixo

```python
c.execute("PRAGMA mmap_size=268435456")  # 256MB memory-mapped I/O
c.execute("PRAGMA cache_size=-64000")     # 64MB page cache
c.execute("PRAGMA temp_store=MEMORY")     # Temp tables em RAM
```

### DB-02: WAL autocheckpoint tuning
**Impacto:** 🟡 Médio | **Esforço:** 2min | **Risco:** Baixo

```python
c.execute("PRAGMA wal_autocheckpoint=4000")  # Checkpoint menos frequente
```

### DB-03: Prepared statements para queries frequentes
**Impacto:** 🟡 Médio | **Esforço:** 30min | **Risco:** Baixo

O `mem_search`, `cache_get`, `cache_put` são chamados dezenas de vezes por request. Prepared statements evitam re-parse do SQL.

### DB-04: Write queue para serialização de escritas
**Impacto:** 🟡 Médio | **Esforço:** 1h | **Risco:** Médio

SQLite permite apenas1 writer simultâneo. Uma write queue serializa escritas a nível de aplicação, evitando SQLITE_BUSY.

---

## CAMADA 4: EMBEDDINGS (embed.py)

### E-01: Embedding cache já existe ✅
LRU cache de1024 entries.

### E-02: ONNX threading optimization
**Impacto:** 🟡 Médio | **Esforço:** 5min | **Risco:** Baixo

```python
# No _get_neural(), configurar ONNX threads
import onnxruntime as ort
opts = ort.SessionOptions()
opts.intra_op_num_threads = 2  # Limitar a2 threads para não competir com GIL
opts.inter_op_num_threads = 1
```

### E-03: Embedding model mais pequeno
**Impacto:** 🟡 Médio | **Esforço:** 15min | **Risco:** Baixo

`BAAI/bge-small-en-v1.5` (384-dim) já é pequeno. Alternativas:
- `BAAI/bge-base-en-v1.5` (768-dim) — melhor qualidade, mais lento
- `sentence-transformers/all-MiniLM-L6-v2` (384-dim) — comparável, mais rápido
- `nomic-ai/nomic-embed-text-v1.5` (768-dim) — melhor qualidade/preço

### E-04: Quantized embeddings
**Impacto:** 🟡 Médio | **Esforço:** 30min | **Risco:** Médio

FastEmbed suporta modelos quantizados que são2-4x mais rápidos.

---

## CAMADA 5: VECTOR SEARCH (memory_vec.py)

### V-01: Qdrant HNSW tuning
**Impacto:** 🟠 Alto | **Esforço:** 10min | **Risco:** Baixo

```python
# Na criação da collection, ajustar HNSW
self.c.create_collection(name, vectors_config=VectorParams(size=DIM, distance=Distance.COSINE),
    hnsw_config=HnswConfigDiff(m=16, ef_construct=200))
```

### V-02: Payload filtering com índice
**Impacto:** 🟡 Médio | **Esforço:** 15min | **Risco:** Baixo

O filtro `god_id` é aplicado em TODAS as queries. Criar índice melhora performance:
```python
self.c.create_payload_index("memory", "god_id", field_schema="keyword")
```

### V-03: On-disk storage para reduzir RAM
**Impacto:** 🟡 Médio | **Esforço:** 5min | **Risco:** Baixo

```python
# Para collections grandes, usar storage_config
from qdrant_client.models import OptimizersConfigDiff
self.c.update_collection("memory", optimizer_config=OptimizersConfigDiff(indexing_threshold=10000))
```

---

## CAMADA 6: LLM ROUTING (routing.py)

### L-01: Provider health cache — evitar probes repetidos
**Impacto:** 🟠 Alto | **Esforço:** 15min | **Risco:** Baixo

O `health()` de cada provider faz HTTP requests para verificar se está up. Com TTL de30s, mas cada pipeline chama `health_all()` múltiplas vezes.

**Solução:** Cache de health com TTL mais longo (60s) e invalidação por falha.

### L-02: Connection reuse já existe ✅
O `_http_client` em `providers.py` já é partilhado com connection pooling.

### L-03: HTTP/2 para providers que suportam
**Impacto:** 🟡 Médio | **Esforço:** 15min | **Risco:** Baixo

```python
_http_client = httpx.Client(http2=True, limits=...)
```

Multiplexing de requests sobre uma só conexão TCP.

### L-04: Prompt caching (provider-side)
**Impacto:** 🔴 Alto | **Esforço:** 30min | **Risco:** Baixo

Anthropic e OpenAI suportam prompt caching. O prefixo do prompt (constitution + memória) é estático entre requests. Marcar como cacheável:
- Anthropic: `cache_control={"type": "ephemeral"}` no system message
- OpenAI: caching automático para prefixes >1024 tokens

**Impacto:** 80-90% redução de TTFT em prompts longos, 50% redução de custo.

### L-05: True LLM Streaming
**Impacto:** 🔴 Alto | **Esforço:** 2h | **Risco:** Médio

Actualmente o LLM call é síncrono (espera pela resposta completa). Com streaming:
- TTFT < 500ms (vs actuais 2-5s)
- Percepção de velocidade 3-5x melhor
- Tokens enviados ao frontend em tempo real

---

## CAMADA 7: BRAIN (brain.py + runtime.py)

### B-04: Regex classification — já feito ✅
Multi-match com confidence scoring.

### B-09: Semantic cache — já feito ✅
Threshold baixado para 0.65.

### B-10: Adaptive personality — já feito ✅
User style detection.

### B-11: Embedding classification cache
**Impacto:** 🟡 Médio | **Esforço:** 5min | **Risco:** Baixo

O `_classify_by_embedding` computa embeddings para os exemplos de intenção na primeira chamada. O cache `_intent_cache` já existe mas pode ser expandido para cachear classificações finais.

---

## CAMADA 8: CONHECIMENTO (thirdeye.py, memory)

### K-01: ThirdEye async — não bloquear pipeline
**Impacto:** 🟡 Médio | **Esforço:** 15min | **Risco:** Baixo

O `criticize()` corre de forma síncrona no pipeline. Pode ser movido para background thread:
```python
threading.Thread(target=criticize, args=(...), daemon=True).start()
```

### K-02: Memory write behind — async writes
**Impacto:** 🟡 Médio | **Esforço:** 30min | **Risco:** Médio

O `store.mem_put()` e `cache_store()` são chamados no hot path. Podem ser movidos para background com write-behind pattern.

---

## PRIORIZAÇÃO — TOP 10 POR IMPACTO/ESFORÇO

| # | Melhoria | Impacto | Esforço | Camada |
|---|---|---|---|---|
| **1** | DB-01: mmap_size + cache_size + temp_store | 🟠 Alto | 2min | SQLite |
| **2** | L-04: Prompt caching (Anthropic/OpenAI) | 🔴 Alto | 30min | LLM |
| **3** | S-02: True SSE streaming | 🟠 Alto | 30min | Server |
| **4** | L-05: True LLM streaming | 🔴 Alto | 2h | LLM |
| **5** | S-01: ORJSON response | 🟡 Médio | 5min | Server |
| **6** | S-03: GZip middleware | 🟡 Médio | 2min | Server |
| **7** | V-01: Qdrant HNSW tuning | 🟠 Alto | 10min | Vector |
| **8** | L-01: Provider health cache | 🟠 Alto | 15min | LLM |
| **9** | K-01: ThirdEye async | 🟡 Médio | 15min | Brain |
| **10** | P-04: Cache-before-analyze | 🟡 Médio | 15min | Pipeline |

---

## ESTIMATIVA DE IMPACTO COMBINADO

| Configuração | Latência actual | Latência optimizada | Melhoria |
|---|---|---|---|
| Cache hit (exact) | ~5ms | ~3ms (ORJSON) | 40% |
| Cache hit (semantic) | ~50ms | ~20ms (embed cache + mmap) | 60% |
| Tool execution | ~100ms | ~70ms (async thirdeye) | 30% |
| LLM call (simple) | ~2000ms | ~800ms (prompt cache + streaming) | 60% |
| LLM call (complex) | ~5000ms | ~2000ms (prompt cache + streaming) | 60% |
| **Perceived speed (streaming)** | **2-5s** | **< 500ms TTFT** | **80%+** |

---

## FERRAMENTAS EXTERNAS RECOMENDADAS

### 1. ORJSON — Serialização JSON ultrarrápida
- **O quê:** Drop-in replacement para `json` module
- **Ganho:** 4-13x mais rápido em payloads grandes
- **Instalação:** `pip install orjson`

### 2. uvloop — Event loop mais rápido
- **O quê:** Replacement para asyncio event loop (baseado em libuv)
- **Ganho:** 2-4x mais rápido que o event loop padrão
- **Instalação:** `pip install uvloop`
- **Uso:** `uvicorn server:app --loop uvloop`

### 3. HTTP/2 — Multiplexing de conexões
- **O quê:** Protocolo HTTP/2 via httpx
- **Ganho:** 2-3x em requests para o mesmo host
- **Instalação:** `pip install h2`

### 4. msgspec — Serialização alternativa
- **O quê:** Fast serialization for JSON, MessagePack, etc.
- **Ganho:** 2-10x mais rápido que pydantic para validação
- **Instalação:** `pip install msgspec`

### 5. aiosqlite — SQLite async
- **O quê:** Async wrapper para SQLite
- **Ganho:** Não bloqueia o event loop em writes
- **Instalação:** `pip install aiosqlite`

---

## REFERÊNCIAS

- FastAPI async benchmarks (2026): async 6-7x faster than sync for I/O
- SQLite production: mmap_size + cache_size + temp_store = 2-3x read speedup
- LLM prompt caching: 80-90% TTFT reduction on cached prefixes
- ORJSON: 4-13% throughput improvement in FastAPI
- Qdrant HNSW tuning: ef=128 for balanced recall/latency
- HTTP/2 multiplexing: 2-3x throughput for same-host requests
