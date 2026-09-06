# HEALTH SYSTEM — Análise e Melhorias Críticas

## Estado Atual (2026-09-07)

### Problema Fundamental
O sistema de health está **mal desenhado para o modo de operação actual**:

| Componente | Problema | Impacto |
|---|---|---|
| `gateway:omniroute` | Sempre down — não precisamos dele | -12.5% |
| `worker:control-local` | Sempre dead — single-process mode | alerta |
| 3 alerts | Contam contra o score | -componentes |
| `providers` | Só OK se pelo menos 1 provider responder | Crítico |

### Score com FULL .ENV: 38% (3/8)
- ✅ providers (3/11 available)
- ✅ gateway:direct  
- ✅ qdrant
- ❌ gateway:omniroute (não necessário)
- ⚠️ worker:dead (não necessário em single-process)
- ⚠️ 3 alerts

### Score sem .ENV: 12% (1/8)
- ❌ providers (0/11)
- ❌ gateway:direct (depende de providers)
- ✅ qdrant
- ❌ gateway:omniroute

## Propostas Críticas

### 1. Classificar componentes por importância (PESOS)
Nem todos os componentes são iguais. O sistema deve ter pesos:

| Componente | Peso | Justificação |
|---|---|---|
| `providers` | 40% | Sem providers = sem LLM = GOD não funciona |
| `gateway:direct` | 20% | Rota para providers |
| `qdrant` | 15% | Vector memory — importante mas opcional |
| `sqlite` | 15% | Store — essencial |
| `omniroute` | 0% | OPCIONAL — não está em uso |
| `worker` | 5% | OPCIONAL em single-process |
| `alerts` | 5% | Informativo, não funcional |

### 2. Health Score ponderado (não percentagem simples)
Em vez de `n_ok / n_total`, usar weighted score:
```
score = sum(component.weight for component in components if component.ok)
```
- Sem .ENV: ~20% (qdrant + sqlite = 30%)
- Com .ENV: ~80% (providers + direct + qdrant + sqlite = 90%)

### 3. Componentes opcionais não devem contar contra
- `omniroute` — marcar como `optional: true` → não conta
- `worker` em single-process — marcar como `optional: true`
- Alerts — informativos, não funcional

### 4. Adicionar componentes que faltam
- `embeddings` — FastEmbed ou HashingVectorizer
- `cache_l1` — L1 hash cache
- `cache_l2` — L2 semantic cache
- `learner` — Autonomous learner running
- `news_connector` — News API connectivity
- `web_search` — DuckDuckGo availability

### 5. Health endpoint deve mostrar "actionable" info
Em vez de só "down", mostrar O QUE fazer:
```
❌ providers — Adiciona GROQ_API_KEY ao .env
❌ omniroute — Instala OmniRoute ou ignora (opcional)
✅ qdrant — OK
```

## Implementação Prioritária

| Prioridade | Item | Effort | Impacto |
|---|---|---|---|
| P0 | Pesos por componente | 30min | Score realista |
| P0 | Componentes opcionais | 15min | Remove false negatives |
| P1 | Adicionar componentes faltantes | 1h | Visibilidade completa |
| P1 | Actionable messages | 30min | UX do admin |
| P2 | Health history (últimas 24h) | 2h | Trending |
