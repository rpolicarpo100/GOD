# Chaves e processos que FALTAM — só o que o código lê

Medido 2026-09-04 neste host. Sem inventar providers.

Chaves **não vão para o git**. Neste host estão em `.env` (gitignored). Probe 2026-09-04: Groq, Cerebras, Gemini, OpenRouter, Inference.net, Z.ai, Claude **HTTP 200**. Ollama local continua down.

## Bloqueia LLM (F6) — ela fica OFFLINE sem isto

| Variável / processo | Onde o código lê | Estado |
|---|---|---|
| `ANTHROPIC_API_KEY` ou `CLAUDE_API_KEY` | `providers.ClaudeAdapter` | **AUSENTE** — adapter recusa chamar a API |
| `GOOGLE_API_KEY` ou `GEMINI_API_KEY` | `providers.GeminiAdapter` | **AUSENTE** |
| Ollama processo `:11434` | `providers.OllamaAdapter` | **porta fechada** — não é API key |
| OmniRoute processo `:20128` | `routing` probe | **porta fechada** — não é API key |

Basta **um** LLM verificado (Ollama a correr **ou** uma key) para sair de OFFLINE.

## Opcional — o core não depende

| Variável | Onde | Estado |
|---|---|---|
| `SUPERAI_WORKER_TOKEN` | `server.py` auth workers | vazio = auth desligada (ok neste sandbox) |
| `SUPERAI_QDRANT` | `memory_vec` | vazio = Qdrant **embedded** local (ok) |
| `SUPERAI_API` / `SUPERAI_WORKER_ID` | `worker.py` remoto | só se houver outro host |
| Langfuse / LiteLLM | `tokens.adapters_status` | módulos **ausentes** — não instalar à força |
| `model_pricing.source` | `tokens.pricing` | tabela vazia → **cost=UNKNOWN** |

## Integrações pedidas — não estão no produto até haver workspace/repo

| Item | Estado MEASURED |
|---|---|
| GitHub deploy key | **OK neste host** (`ssh` → `rpolicarpo100/GOD`) |
| GitHub PAT | API repo deu 404 com o PAT antigo — **não reutilizar no git** |
| Plane `X-API-Key` | `GET /api/v1/users/me/` 200; **sem workspace_slug** no código → adapter **não** ligado |
| OpenAI / Groq / etc. | **não existem no código** — não pedir keys que ela não lê |

## Não são keys (não fingir)

Docker, Postgres, Redis, SearXNG, Qdrant `:6333`, preços Anthropic/OpenAI hard-coded.

## O que obter a seguir (ordem)

1. **Uma** key LLM (Claude **ou** Gemini) **ou** Ollama noutro host com RAM — este tem ~2 GB, modelos locais grandes **não cabem**.
2. Plane: `PLANE_WORKSPACE_SLUG` + project id, **depois** adapter.
3. (Opcional) `SUPERAI_WORKER_TOKEN` se a GOD ficar exposta na rede.
