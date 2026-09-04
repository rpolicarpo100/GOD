# SUPER AI — infra real (fase 0–4 + tools)

Não é uma demo de agentes fictícios. É a espinha executável neste host, com o que **existe de verdade**.

## Auditoria (2026-09-04)

| Componente pedido | Neste host | Estado |
|---|---|---|
| Python 3.13, FastAPI, tiktoken, numpy, lxml | sim | usado |
| Git | sim | ferramenta real |
| SQLite | stdlib | estado / cache / memória / audit |
| Ollama :11434 | fechado | adapter probe, `available=false` |
| Claude / Anthropic key | ausente | adapter recusa chamar API |
| PostgreSQL, Redis, Qdrant | ausentes | **não simulados** |
| Docker, SearXNG, OmniRoute | ausentes | **não simulados** |
| Benchmarks Claude 95 / Qwen 87 | nunca medidos | `historical_score=null`, n=0 |

O `engine.py` anterior **inventava** tarefas, ratings e experiências. Foi removido. Justificação: viola a regra absoluta (não inventar capacidade nem benchmark).

## O que está implementado

- Task analyzer estruturado
- Token firewall (tiktoken cl100k_base, budgets task/session/daily/project)
- Context pack mínimo (sem dumps de conversa)
- Hash cache + normalização lexical (não é embeddings — Qdrant ausente)
- Memória SQLite (keyword, não vectorial)
- Ferramentas: calculator, fs.list/read (governor), git allowlist, json/csv/xml, regex, python sandbox
- Provider adapters que **sondam** e reportam down
- LLM last: cache → memória → tools → local → Claude → humano
- Event bus + audit log
- Dashboard vivo + consola do cérebro
- Evaluator só sobre execuções reais (tools). Sem scores de modelos.

## Implementado nesta iteração (real)

- **Qdrant embedded** (sem Docker :6333) + **HashingVectorizer 384-d** (lexical, não neural)
- **RoutingAdapter**: probe OmniRoute `:20128` + DirectAdapter fallback; endpoint OpenAI-compat `/v1`
- **Benchmark harness** com golden set; LLM cases SKIP se n=0
- **Evolution engine**: observe → hipótese → experiência com evidência → pending/adopt/reject (Governor)

Ainda ausente: SearXNG, Postgres, Redis, Docker, embeddings neurais, processo npm OmniRoute.

## Correr

```bash
cd super-ai
python3 -m unittest tests.test_core
python3 -m uvicorn server:app --host 0.0.0.0 --port 8000
```

## Princípio

Maximize useful work per token. Neste host o número correcto de chamadas LLM é **zero**, até existir um provider verificado.
