# GOD — Recomendações de Inteligência e Velocidade
**Data:** 2026-09-06 | **Base:** Análise de 49 módulos, 12.947 LOC, pipeline completo

---

## 📊 Estado Actual

| Métrica | Valor | Nota |
|---------|-------|------|
| Módulos | 49 .py | SuperAI + server |
| LOC total | 12.947 | Bem estruturado |
| Testes | 162 pass / 2 fail (pre-existing cache) | 98.8% |
| Providers | 11 registados | Groq, Cerebras, Gemini, OpenRouter... |
| Latência média | ~2900ms | Pipeline completo: cache→memory→decide→llm |
| Cache | SQLite hash + Qdrant semantic | Funcional |
| Embeddings | FastEmbed BAAI/bge-small 384-dim | Neural ONNX CPU |
| Streaming | ❌ NÃO implementado | Resposta inteira de uma vez |
| Provider racing | ❌ NÃO implementado | Tenta um provider de cada vez |

---

## 🚀 VELOCIDADE — 5 Recomendações Prioritárias

### 1. ⚡ STREAMING TOKEN-A-TOKEN (Impacto: ALTO | Esforço: MÉDIO)

**Problema:** O utilizador espera 2.9s sem qualquer feedback visual. A resposta aparece toda de uma vez.

**Solução:** Implementar streaming SSE do LLM para o chat. O pipeline já usa SSE para eventos — estender para tokens.

```
Fluxo actual:
  user → POST /api/chat → pipeline (2.9s) → resposta inteira

Fluxo proposto:
  user → POST /api/chat → pipeline → token1 → token2 → token3 → ... → fim
         (cada token aparece no chat imediatamente)
```

**Onde mudar:**
- `superai/providers.py` — adicionar `stream=True` nos pedidos HTTP, iterar SSE lines
- `superai/routing.py` — propagar streaming callback
- `superai/pipeline.py:_stage_llm` — usar callback em vez de esperar resposta completa
- `server.py` — endpoint `/api/chat` pode usar SSE ou chunked response
- `index.html` — receber chunks e append ao último message `.m.brain`

**Estimativa:** Reduz latência percebida de 2900ms para ~200ms (primeiro token).

---

### 2. 🏎️ PROVIDER RACING (Impacto: ALTO | Esforço: BAIXO)

**Problema:** O routing tenta providers sequencialmente (OmniRoute → Direct). Se Groq demora3s, espera3s antes de tentar Cerebras.

**Solução:** Disparar pedidos em paralelo a2-3 providers, usar o que responder primeiro.

```python
# Actual (routing.py):
res = adapter.complete(prompt, ...)  # bloqueia até resposta

# Proposto:
import concurrent.futures
with ThreadPoolExecutor(max_workers=3) as pool:
    futures = {pool.submit(p.complete, prompt, ...): p for p in top_providers}
    for future in concurrent.futures.as_completed(futures, timeout=5):
        result = future.result()
        if result["status"] == "success":
            return result  # primeiro a responder ganha
```

**Onde mudar:**
- `superai/routing.py` — função `complete()` com racing
- `superai/providers.py` — `health_all()` já tem latência de cada provider; usar para ordenar

**Estimativa:** Reduz latência em30-50% quando há múltiplos providers disponíveis.

---

### 3. 📦 CACHE SEMÂNTICO MAIS AGRESSIVO (Impacto: MÉDIO | Esforço: BAIXO)

**Problema:** O cache semântico só activa com `min_score=0.88` (muito conservador). Perguntas similares como "como estás" vs "como vais" não fazem hit.

**Solução:** Baixar threshold para0.82 e adicionar cache de respostas frequentes por tipo.

```python
# Actual (pipeline.py:214):
sem = vectors.search("cache", text, k=1, min_score=0.88, god_id=gid)

# Proposto:
sem = vectors.search("cache", text, k=1, min_score=0.82, god_id=gid)
```

**Adicional:** Cache de shortcuts — perguntas como "estado", "roadmap", "tokens" são determinísticas. Guardar resultado com TTL.

**Onde mudar:**
- `superai/pipeline.py:_stage_cache` — baixar min_score
- `superai/shortcuts.py` — cachear resultados de shortcuts

**Estimativa:** De ~5% cache hit rate para ~25% em uso normal. Respostas instantâneas (<50ms).

---

### 4. 🔧 PIPELINE PARALELO (Impacto: MÉDIO | Esforço: MÉDIO)

**Problema:** As stages do pipeline são sequenciais: cache → memory → firewall → decide → tools → llm. Memory e cache poderiam correr em paralelo.

**Solução:** Executar cache lookup e memory search em paralelo.

```python
# Actual (pipeline.py:596-601):
cache_result = _stage_cache(...)  # ~50ms
if cache_result: return cache_result
merged, ctx = _stage_memory(...)  # ~100ms

# Proposto:
import concurrent.futures
with ThreadPoolExecutor() as pool:
    cache_f = pool.submit(_stage_cache, ...)
    memory_f = pool.submit(_stage_memory, ...)
    cache_result = cache_f.result()
    merged, ctx = memory_f.result()
```

**Onde mudar:**
- `superai/pipeline.py:run_pipeline` — paralelizar stages independentes

**Estimativa:** Reduz overhead de ~150ms para ~100ms no pipeline.

---

### 5. ⏱️ PRE-COMPUTE CONTEXT (Impacto: BAIXO | Esforço: BAIXO)

**Problema:** O context_pack e dialogue lookup correm durante o pipeline, adicionando latência.

**Solução:** Pre-computar context quando o utilizador abre o chat (warm cache).

**Onde mudar:**
- `superai/brain.py:context_pack` — cache em memória com TTL de30s
- `server.py` — endpoint `/api/chat/warm` chamado no load do dashboard

---

## 🧠 INTELIGÊNCIA — 5 Recomendações Prioritárias

### 1. 🧩 CONTEXTO CONVERSACIONAL (Impacto: ALTO | Esforço: MÉDIO)

**Problema:** O GOD responde a cada mensagem isoladamente. `_dialogue(4, current=text)` só pega nas últimas4 mensagens como contexto bruto.

**Solução:** Sistema de memória conversacional com:
- **Resumo automático** a cada10 mensagens (via LLM)
- **Entidades detectadas** (nomes, projectos, preferências) guardadas em memória
- **Sumário activo** injectado no prompt como system message

```
Actual prompt:
  "Utilizador: Ola"

Proposto prompt:
  "Contexto: O utilizador chama-se [nome]. Projecto activo: GOD. 
   Última interacção: falou sobre providers offline.
   
   Utilizador: Ola"
```

**Onde mudar:**
- `superai/brain.py:_llm_prompt` — injectar contexto
- `superai/store.py` — tabela `conversation_context` com sumário
- `superai/pipeline.py:_stage_memory` — buscar contexto conversacional

---

### 2. 🎯 INTENT CLASSIFIER LOCAL (Impacto: ALTO | Esforço: MÉDIO)

**Problema:** O `analyze()` em `brain.py` usa regex para classificar intents. É frágil — "quanto custa" pode ser tool_query ou general.

**Solução:** Classificador de intents com embeddings locais (já temos FastEmbed).

```python
# Actual (brain.py:25):
def analyze(text):  # regex-based

# Proposto:
INTENT_EXAMPLES = {
    "status": ["como estás", "estado", "tudo bem"],
    "code": ["escreve código", "programa em python", "cria uma função"],
    "research": ["pesquisa", "procura", "o que é"],
    "tool": ["executa", "corre", "roda"],
}
# Embed query + exemplos → cosine similarity → intent
```

**Onde mudar:**
- `superai/brain.py:analyze` — hybrid regex + embedding classifier
- `superai/embed.py` — já tem infra necessária

---

### 3. 🔄 SELF-REFLECTION LOOP (Impacto: MÉDIO | Esforço: MÉDIO)

**Problema:** O GOD não avalia a qualidade da sua própria resposta. `evaluate()` dá scores mas não actua sobre eles.

**Solução:** Se o score OVERALL < 0.6, tentar novamente com prompt melhorado.

```python
# Após _stage_llm:
scores = evaluate(task, tool_results, True, toks)
if scores["OVERALL"] < 0.6 and retry_count < 1:
    # Re-prompt com instrução de melhoria
    improved_prompt = f"Melhora esta resposta (score {scores['OVERALL']}): {original_response}\n\nCritique: {critique}"
    res = routing.complete(improved_prompt, ...)
```

**Onde mudar:**
- `superai/pipeline.py:_stage_llm` — loop de reflexão
- `superai/brain.py:evaluate` — já tem scores, só falta actuar

---

### 4. 📚 KNOWLEDGE PERSISTENCE (Impacto: MÉDIO | Esforço: BAIXO)

**Problema:** O GOD esquece tudo entre sessões. `mem_put("episode", ...)` guarda mas nunca é usado para construir conhecimento.

**Solução:** Extrair facts das interacções e guardar como knowledge entries persistentes.

```python
# Após cada resposta LLM:
facts = extract_facts(text, response)  # "O utilizador prefere Python"
for fact in facts:
    store.mem_put("knowledge", sha(fact), fact)
    
# No context_pack:
knowledge = store.mem_search("knowledge", text, limit=3)
```

**Onde mudar:**
- `superai/pipeline.py:_stage_llm` — extrair facts
- `superai/brain.py:context_pack` — incluir knowledge
- `superai/store.py` — `mem_search` por similaridade

---

### 5. 🤖 PROACTIVE SUGGESTIONS (Impacto: MÉDIO | Esforço: MÉDIO)

**Problema:** O GOD só responde quando perguntado. Nunca sugere acções proactivamente.

**Solução:** Observer pattern — analisar padrões e sugerir.

```
Exemplo: Se o utilizador pergunta sobre providers3x seguidas:
  → GOD sugere: "Vi que tens problemas com providers. Quer que 
     configure o Ollama local como fallback?"

Exemplo: Se CPU > 80% por > 5min:
  → GOD sugere: "CPU alta. Quer que mude para modo ECO?"
```

**Onde mudar:**
- `superai/observer.py` — detectar padrões
- `superai/runtime.py:_broadcast` — incluir sugestões no snapshot
- `index.html` — mostrar sugestões como notificações

---

## 📋 Prioridade de Implementação

| # | Recomendação | Impacto | Esforço | Velocidade/Inteligência |
|---|-------------|---------|---------|------------------------|
| 1 | Streaming token-a-token | ⭐⭐⭐ | Médio | Velocidade |
| 2 | Provider racing | ⭐⭐⭐ | Baixo | Velocidade |
| 3 | Contexto conversacional | ⭐⭐⭐ | Médio | Inteligência |
| 4 | Intent classifier local | ⭐⭐⭐ | Médio | Inteligência |
| 5 | Cache semântico mais agressivo | ⭐⭐ | Baixo | Velocidade |
| 6 | Pipeline paralelo | ⭐⭐ | Médio | Velocidade |
| 7 | Self-reflection loop | ⭐⭐ | Médio | Inteligência |
| 8 | Knowledge persistence | ⭐⭐ | Baixo | Inteligência |
| 9 | Proactive suggestions | ⭐⭐ | Médio | Inteligência |
| 10 | Pre-compute context | ⭐ | Baixo | Velocidade |

---

## 🎯 Quick Wins (implementáveis hoje)

1. **Baixar cache min_score** de 0.88 → 0.82 (1 linha)
2. **Provider racing** com ThreadPoolExecutor (~30 linhas)
3. **Cache de shortcuts** determinísticos (~20 linhas)
4. **Warm cache** no load do dashboard (~10 linhas)

---

*Gerado automaticamente por análise de código GOD — 49 módulos, 12.947 LOC*
