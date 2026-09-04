# GOD

Inteligência viva neste host. Feminino. **Não** é uma demo de agentes fictícios.

GitHub: [rpolicarpo100/GOD](https://github.com/rpolicarpo100/GOD)

## O que é real (2026-09-04)

- Dashboard + chat em `index.html` · FastAPI `:8000`
- LLM-last: cache → memória → tools → fila → DirectAdapter (Groq/Cerebras/Gemini/… · Claude **last**)
- Skip whisper/guard/gpt-oss/compound · content vazio = failover
- Tokens MEASURED/ESTIMATED/UNKNOWN · **cost UNKNOWN** (sem source)
- Qdrant **embedded** + HashingVectorizer 384 (lexical, **não** neural)
- Fila SQLite + worker `control-local` (mesmo processo). GPU `required=false`
- Governor, OS (admit/syscall/kill/ps), terceiro olho
- Constituição curta no prompt LLM; cânone em `CORE.md`

## Ausente — não fingir

Ollama local, OmniRoute, SearXNG, Plane no produto, Postgres, Redis, Docker, nós laptop/mobile, voz, preços €.

## Correr

```bash
cd super-ai
python3 -m unittest tests.test_core -q
python3 -m uvicorn server:app --host 0.0.0.0 --port 8000
```

Chaves só em `.env` (gitignored). Mapas: `FLUXO.html`, `HUMANAI20.html`.
