# GOD — Recomendações Críticas: Poder do Cérebro
**Commit:** `fc99227` | **Data:** 2026-09-07 | **Método:** Análise profunda de brain.py, pipeline.py, routing.py, providers.py, executive.py, thirdeye.py, runtime.py

---

## MAPA DO CÉREBRO ACTUAL

```
USER INPUT
    │
    ▼
┌─────────────────────────┐
│ pipeline.plan()         │ ← regex patterns (30+ regras)
│ Deterministic routing   │   classifica: math/git/files/python/web_search/github/news/general
└────────┬────────────────┘
         │
    ▼────▼─────
┌─────────────┐
│ executive   │ ← decide(): DEEP/FAST/NORMAL + tools/llm/queue
│ .decide()   │   SEM LLM — 100% determinístico
└────┬────────┘
     │
     ▼
┌─────────────────────────────────┐
│ CACHE → MEMORY → TOOLS → LLM   │ ← pipeline em 7 estágios
│                                 │
│ LLM stage:                      │
│  1. max_tokens fixo por type    │
│  2. prompt = constitution +     │
│     memória + diálogo(4) + user │
│  3. routing.complete()          │
│     → provider racing (top 2)   │
│  4. adaptive_routing learning   │
└────────┬────────────────────────┘
         │
    ▼────▼
┌─────────────┐
│ ThirdEye    │ ← criticismo pós-execução (advisory only)
│ .criticize()│   analisa: path, latency, cache, memory, scores
└─────────────┘
```

---

## ACHADOS CRÍTICOS

### B-01: 🔴 Prompt do sistema estático e contraditório
**Ficheiro:** `runtime.py:420` (`_llm_prompt`)
**Problema:** O prompt diz "Não tens pesquisa web" mas GOD TEM pesquisa web. Diz "nem embeddings neurais" mas GOD TEM FastEmbed. Estas afirmações desactivam capacidades reais.
**Impacto:** O LLM recusa-se a usar funcionalidades que existem.
**Solução:** Gerar prompt dinamicamente baseado em capacidades disponíveis.

### B-02: 🔴 max_tokens fixo — sem adaptação à complexidade real
**Ficheiro:** `pipeline.py:589-596`
**Problema:**
```python
if task_type == "coding":
    max_tok = 2048 if cx >= 7 else 1024
elif task_type == "research":
    max_tok = 1024 if cx >= 5 else 512
else:
    max_tok = 512 if cx >= 5 else 256
```
256 tokens para perguntas gerais é MUITO pouco — cabe uma resposta de 2 parágrafos. Perguntas como "explica-me X em detalhe" recebem o mesmo budget que "que horas são".
**Impacto:** Respostas truncadas, o LLM corta no meio de frases.
**Solução:** Estimar tokens necessários baseado no tamanho da pergunta + complexidade + histórico de respostas do utilizador.

### B-03: 🔴 Diálogo limitado a 4 mensagens
**Ficheiro:** `runtime.py:436`
**Problema:** `_dialogue(4, current=text)` — o LLM só vê as últimas 4 mensagens. Qualquer referência a algo dito há 5+ mensagens é perdida.
**Impacto:** O GOD "esquece" conversas rapidamente. "Lembra-te do que disse antes" falha.
**Solução:** Usar memória semântica para recuperar mensagens relevantes do histórico completo.

### B-04: 🟠 Complexidade estimada por regex, não por LLM
**Ficheiro:** `pipeline.py:52` (`plan()`) + `brain.py:117`
**Problema:** A classificação de tipo e complexidade usa 30+ regex patterns. Se o utilizador diz "cria um script que faça X", o regex pode classificar como "general" em vez de "coding" se o padrão não casar.
**Impacto:** Classificação errada → wrong max_tokens, wrong tools, wrong routing.
**Solução:** Usar o LLM para classificar quando regex não tem confiança alta. Ou expandir os padrões significativamente.

### B-05: 🟠 Provider racing desperdiça tokens
**Ficheiro:** `routing.py:220-248`
**Problema:** O racing manda o mesmo prompt para 2 providers em paralelo. O que perder é descartado — tokens gastos sem resultado. Para queries simples, isto duplica o custo.
**Impacto:** 2x tokens em queries que podiam ser resolvidas por 1 provider.
**Solução:** Racing só para queries complexas (DEEP mode) ou quando o provider primário tem latência > 2s.

### B-06: 🟠 ThirdEye é advisory-only — nunca corrige
**Ficheiro:** `thirdeye.py`
**Problema:** O ThirdEye analisa a pipeline DEPOIS de executar e diz "podias ter feito melhor". Mas nunca aplica a correção. As recomendações vão para o log e ficam lá.
**Impacto:** O GOD repete os mesmos erros. Aprende com feedback mas nunca o aplica.
**Solução:** Quando ThirdEye detecta um padrão repetido (ex: "cache miss 3x para o mesmo tipo de query"), forçar cache warmup ou ajustar routing.

### B-07: 🟠 Sem chain-of-thought visível
**Ficheiro:** `_llm_prompt` em `runtime.py`
**Problema:** O prompt não pede ao LLM para raciocinar passo a passo. Para perguntas complexas, o LLM tenta dar a resposta directa sem mostrar o processo.
**Impacto:** Respostas menos precisas em perguntas que requerem raciocínio multi-step.
**Solução:** Adicionar "Pensa passo a passo antes de responder" para queries com complexidade >= 5.

### B-08: 🟡 Memory retrieval sem ranking de relevância
**Ficheiro:** `pipeline.py:317` (`_stage_memory`)
**Problema:** A memória é recuperada por keyword match + vector similarity. Mas não há re-ranking — os primeiros resultados podem não ser os mais relevantes para a pergunta actual.
**Impacto:** Contexto irrelevante enviado ao LLM desperdiça tokens e confunde.
**Solução:** Usar cohere_rerank ou LLM-based re-ranking para as top-5 memórias.

### B-09: 🟡 Cache key baseada em hash exacto
**Ficheiro:** `brain.py:228`
**Problema:** `cache_lookup` usa SHA do texto normalizado. "Qual é a capital de Portugal?" e "capital de Portugal" geram chaves diferentes.
**Impacto:** Cache miss em perguntas semanticamente equivalentes.
**Solução:** Usar vector similarity para cache lookup (já existe `semantic_cache.py` mas precisa de mais dados).

### B-10: 🟡 Sem personalidade adaptativa
**Ficheiro:** `_llm_prompt` em `runtime.py`
**Problema:** A personalidade é fixa: "Fala no feminino. Inteligência profissional, analítica." Não adapta ao estilo do utilizador.
**Impacto:** GOD sempre responde da mesma forma, independentemente de quem fala.
**Solução:** Detectar o estilo do utilizador (formal/informal, técnico/leigo) e adaptar o prompt.

---

## QUICK WINS DO CÉREBRO

| # | Melhoria | Esforço | Impacto |
|---|---|---|---|
| **B-01** | Remover "não tens web/embeddings" do prompt | 5min | 🔴 Alto — desbloqueia capacidades |
| **B-02** | Aumentar max_tokens base (256→512) | 5min | 🔴 Alto — respostas completas |
| **B-03** | Diálogo 4→8 mensagens | 5min | 🟠 Alto — melhor contexto |
| **B-07** | "Pensa passo a passo" para complexidade >= 5 | 5min | 🟠 Alto — melhor raciocínio |
| **B-05** | Racing só para DEEP mode | 15min | 🟡 Médio — poupa tokens |

---

## MELHORIAS ESTRUTURAIS (MAIOR ESFORço)

| # | Melhoria | Esforço | Impacto |
|---|---|---|---|
| **B-04** | LLM classification fallback | 2h | 🔴 Alto — routing correcto |
| **B-06** | ThirdEye auto-correction | 3h | 🟠 Alto — aprendizagem real |
| **B-08** | Re-ranking de memória | 2h | 🟠 Alto — contexto relevante |
| **B-03** | Semantic dialogue retrieval | 4h | 🔴 Alto — memória de longo prazo |
| **B-10** | Personalidade adaptativa | 2h | 🟡 Médio — UX |
