# Chaves — o que o código lê (2026-09-04)

Chaves **só em `.env` (gitignored)**. Nunca no git. Nunca no chat.

Probe HTTP 200 neste host: Groq, Cerebras, Gemini, OpenRouter, Inference.net, Z.ai, Claude. Ollama local `:11434` **fechado**. OmniRoute `:20128` **fechado**. Cloudflare R2 = object storage, **não** LLM. HuggingFace `whoami` ≠ chat — **sem** adapter HF.

## LLM no produto (ordem: local → API → Claude last)

| Adapter | Variável | Chave neste host | Link oficial |
|---|---|---|---|
| Ollama local | processo `:11434` | **down** | [ollama.com/download](https://ollama.com/download) |
| Groq | `GROQ_API_KEY` | no `.env` · probed 200 | [console.groq.com/keys](https://console.groq.com/keys) |
| Cerebras | `CEREBRAS_API_KEY` | no `.env` · probed 200 | [cloud.cerebras.ai](https://cloud.cerebras.ai/) · [auth docs](https://inference-docs.cerebras.ai/api-reference/authentication) |
| Gemini | `GOOGLE_API_KEY` / `GEMINI_API_KEY` | no `.env` · probed 200 | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |
| OpenRouter | `OPENROUTER_API_KEY` | no `.env` · probed 200 | [openrouter.ai/keys](https://openrouter.ai/keys) |
| Inference.net | `INFERENCE_API_KEY` | no `.env` · probed 200 | [inference.net](https://inference.net) |
| Z.ai | `ZAI_API_KEY` | no `.env` · probed 200 | [z.ai](https://z.ai) |
| Claude | `ANTHROPIC_API_KEY` / `CLAUDE_API_KEY` | no `.env` · probed 200 | [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys) |

`available=True` só depois de GET `/models` 200 **e** pelo menos um id de **chat** (skip whisper/guard/embed/tts/compound/gpt-oss/:batch). Completions usam `pick_chat_model`. Resposta `content` vazio = erro (não fala CoT, não dump de pipeline).

## Não são LLM — não ligar como chat

| Item | Link | Estado |
|---|---|---|
| HuggingFace token | [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) | whoami only — sem adapter de completions |
| Cloudflare R2 | [developers.cloudflare.com/r2](https://developers.cloudflare.com/r2/) | S3 storage |
| OmniRoute npm `:20128` | [npmjs.com/package/omniroute](https://www.npmjs.com/package/omniroute) | **down** neste host (EACCES no install global) |
| Plane | [developers.plane.so](https://developers.plane.so/) · API `https://api.plane.so/` header `X-API-Key` | chave no `.env`. `users/me` 200. Workspace `GODSX` **404**. Sem board. Sem issues. |
| Langfuse / LiteLLM | — | ausentes; **não** obrigatórios |
| Preços | — | `cost=UNKNOWN` até haver `source` verificável |

## Ainda em falta neste host

- Ollama local (RAM ~2 GB — modelos grandes **não cabem**).
- OmniRoute processo.
- Plane: workspace slug **real** da URL `app.plane.so/{slug}` — `GODSX` deu 404. Project UUID se for diferente do nome.
- Tabela de preços com source.

Rodar as keys que foram coladas no chat.
