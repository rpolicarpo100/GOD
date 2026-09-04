# Token Intelligence — auditoria e integração (não é rewrite)

Fonte: código em `/home/user/super-ai` em 2026-09-04. Sem preços, Langfuse, LiteLLM, Claude usage, nem benchmarks de modelos.

## CURRENT TOKEN FLOW

```
USER
 → handle() [runtime.py]
 → analyze()  tiktoken cl100k_base  estimated = input+180  ESTIMATED
 → cache_lookup (hash) / Qdrant semantic (min_score 0.88)
    HIT → 0 LLM tokens  (hoje NÃO escreve token_log)
 → mem_search + vectors.search
 → context_pack  (dedup linhas; tiktoken do pack)
 → firewall()  compara ESTIMATED vs budgets task/session/daily/project
    reject → TOKEN_BUDGET_EXCEEDED  (hoje NÃO escreve token_log)
 → tools determinísticos  log_tokens(est, actual=0, llm=0)
 → se needs_llm e any_llm() → fila
 → senão routing.complete()
    OmniRoute :20128  (fechado)  usage.total_tokens se o JSON trouxer
    DirectAdapter → Ollama/Claude/Gemini  todos available=false
    NO_PROVIDER → log_tokens(est, 0, llm=0)
```

LLM calls no código (únicos):
- `runtime.handle` → `routing.complete`
- `benchmark._llm_smoke` → `routing.complete` (SKIP se nenhum adapter up)
- `providers.*.complete` / `routing.*.complete` — nunca chegam a HTTP neste host

Contagens MEASURED hoje: `llm_calls=0`, `token_log.actual` todos 0 (n=8 no spine.db).

## CURRENT COST FLOW

Não existe. Nenhum `model_pricing`, nenhum €/1M, nenhuma fonte verificável.
`tools.py` usa a palavra "cost" para risco/computação de ferramenta, não dinheiro.

```
cost = UNKNOWN
```

## GAPS (real vs spec)

| Spec | Estado |
| Token event normalizado | parcial: `token_log(estimated, actual, model, llm)` |
| input/output/cached/reasoning | ausente (provider não deu) |
| estimated vs actual + error | actual existe; error não é calculado |
| Pricing registry | ausente → deve ficar UNKNOWN |
| Budgets hierárquicos | task/session/daily/project/agent em config.yaml; firewall usa 4; agent não é enforced |
| Token Firewall | existe (`brain.firewall`) — NÃO duplicar |
| LLM-last | existe no runtime |
| Context efficiency | `context_pack` dedup; sem score/raw vs final persistido |
| Semantic cache analytics | hit/miss counters; sem tokens_saved persistidos |
| Router token-aware | router só executa; decisão é LLM-last no runtime |
| Forecast / anomaly | ausente |
| Dashboard token | sessão tokens no header; sem estimated vs actual |
| Langfuse / LiteLLM | ABSENT — adapters reportam down, core não depende |
| Agent/project dashboards | um processo, sem multi-agent |

## TARGET (extensão)

```
EXISTING: analyzer → cache → memory → tools → firewall → router
                              ↑
                    tokens.py (transversal)
                    measure / estimate / UNKNOWN cost /
                    persist token_events / emit bus /
                    forecast=FORECAST or UNKNOWN
```

Não substitui Brain, Governor, Router, Memory, Evolution, Observer.

## IMPLEMENTATION PLAN

1. Reutilizar firewall, token_log, usage, cache, bus, observer, tiktoken.
2. Criar `superai/tokens.py` + tabela `token_events` + `model_pricing` vazia.
3. Dual-write a partir do runtime (cache/tools/block/llm).
4. API `/api/token/*` no FastAPI existente.
5. Painel no dashboard vivo (não um tab novo).
6. Preço: UNKNOWN até `source` verificada. Sem hard-code Anthropic/OpenAI.
7. Langfuse/LiteLLM: status `available=false`, zero dependência.

Fases extra (2026-09-04): `route_advice` (BLOCK sem LLM), `report()` com kinds, `models()` UNKNOWN se n_llm=0, fallback OmniRoute→Direct medido, context/cache savings ESTIMATED vs actual UNKNOWN.

## Não inventar

Preços Claude/GPT, poupanças em €, qualidade de modelos, 37% increase, Langfuse up.
Se n histórico < limiar: `kind=UNKNOWN` ou `FORECAST` com `insufficient_history`.
