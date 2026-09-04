# PROMPT MESTRE — evoluir a GOD (HumanAI 2.0 como extensão)

Entrega isto à outra IA **tal como está**. Produto: **GOD** (ela). HumanAI 2.0 é o mapa-alvo, não um rename nem um rebuild.

---

## MISSÃO

Evolui o repositório existente `super-ai` (GitHub `rpolicarpo100/GOD`) para ficar alinhado com HumanAI 2.0 **sem reconstruir** o que já funciona.

Não adicionar funcionalidades para parecer avançado.
Não criar um segundo Core / Orchestrator / Router / Governor / Memory / Firewall.

**AUDITAR → MAPEAR → PRIORIZAR → IMPLEMENTAR O GAP REAL → TESTAR → DOCUMENTAR**

---

## REGRA ABSOLUTA

Tudo REAL e FUNCIONAL.

Não inventes APIs, endpoints, bibliotecas, preços, capacidades, resultados de testes, integrações, nós, voz, visão, telemóvel, orçamentos em €.

Se não puder ser verificado neste host: **NOT VERIFIED** / `available=false`. Nunca simules que funciona.

GPU = OPTIONAL, never REQUIRED.
Claude = modelo **last**, nunca dependência central.
OmniRoute = gateway opcional `:20128`. Se down, DirectAdapter.
Keys só em `.env` gitignored. Nunca commitas `.env`, PAT, Plane key, SSH private.

Nome: **GOD**, feminino. Não renomeies módulos Python para HumanAI.

---

## O QUE JÁ EXISTE (NÃO SUBSTITUIR)

| Spec HumanAI 2.0 | Ficheiro GOD |
|---|---|
| Orchestrator / Core | `superai/runtime.py` `handle()` |
| Intent Engine | `superai/brain.py` `analyze()` |
| Task Planner | `runtime._plan` LLM-last |
| Context Manager | `brain.context_pack` |
| AI Router | `superai/routing.py` |
| Tool Router | `superai/aios.py` + `tools.py` |
| Memory | `store.py` + `memory_vec.py` (HashingVectorizer 384, **não** neural) |
| Security | `governor.py` |
| Token Intelligence | `tokens.py` (MEASURED / ESTIMATED / FORECAST / UNKNOWN) |
| Cost | `cost=UNKNOWN` sem `source` |
| Node / queue | `queue.py` + `compute.py` control-local + `worker.py` (contrato remoto) |
| Events / olho | `events.py` `observer.py` |
| UI leve | `index.html` + FastAPI `server.py` `:8000` |
| Providers | `providers.py` local→API→Claude last; `pick_chat_model` |
| Testes | `tests/test_core.py` |

Lê `HUMANAI20.html`, `FLUXO.html`, `ROADMAP.md`, `DISTRIBUTED.md`, `CORE.md`, `KEYS.md` antes de escrever código.

---

## ARQUITECTURA ALVO (EXTENSÃO, NÃO 12 CLASSES NOVAS)

```
USER (texto; voz/imagem NOT VERIFIED)
  → interface leve (index.html)
  → handle()  [único orquestrador]
       analyze → cache → memória → firewall → _plan
         ├ tools/syscall/governor
         ├ fila + worker
         └ routing.complete (Direct; Omni se up)
  → ela fala texto LLM + rodapé MEASURED
  → cache_store / memory upsert
```

Nós: **dividir tarefas, não o modelo**.
Hoje 1 node (PC). Segundo node = processo `worker.py` noutro host com heartbeat. Laptop/Mobile = NOT VERIFIED até existirem.

---

## O QUE É PROIBIDO NESTA EVOLUÇÃO

- Criar `HumanAICore`, `IntentEngine`, `ResearchAgent`, `CodingAgent`, … — duplicam `handle`/`_plan`.
- Inventar orçamento **€50/mês** como métrica MEASURED (não há preços verificados).
- Ligar Plane sem `workspace_slug` + issues criadas pela API.
- Instalar Ollama/Docker/OmniRoute neste host ~2 GB.
- Pesquisa web sem SearXNG probed.
- Embeddings neurais fingidos (HashingVectorizer não é FastEmbed).
- Auth no frontend com keys.
- Reescrever Brain / Router / Governor / Memory / Evolution.
- Segundo uvicorn no mesmo `data/qdrant` (lock exclusivo).
- `git add .env`.

Se encontrares solução tecnicamente superior a uma fase do spec: **explica, compara, espera aprovação** antes de mudança arquitectural.

---

## FASES (SÓ AVANÇA SE A ANTERIOR ESTIVER ESTÁVEL)

**Fase 1 — Audit (já feita em HUMANAI20.html).** Não repetir como teatro. Actualizar README/config.yaml stale.

**Fase 2 — Cleanup + constituição.** Destilar `CORE.md` para `_llm_prompt` (6–8 frases). `roadmap` atalho; «quem és» → LLM. Docs honestas.

**Fase 3 — Router (já existe).** Não reescrever. Só: timeout/failover já 12s/máx 3; rodapé com adapter; sem fallback silencioso.

**Fase 4 — Memory.** Não criar 4 níveis fictícios. Documentar: cache hash = short; context_pack = working; SQL+Qdrant hashing = long lexical. Neural = NOT VERIFIED.

**Fase 5 — Tools.** Catálogo actual (calc, fs, git, parse, python). Web/Browser/Voice = NOT VERIFIED. Não adicionar tools inventadas.

**Fase 6 — Validation.** `evaluate` hoje é scores internos. Fact-check externo = NOT VERIFIED. Não criar Validation Agent.

**Fase 7–8 — Tokens / Cost.** Manter kinds. Custo € só com `source` verificável. Sem source: UNKNOWN. Budget em **tokens** já existe (`config.yaml` budgets).

**Fase 9+ Nodes.** Só quando houver um segundo host real a correr `worker.py`. Não simular laptop/mobile no dashboard.

---

## TESTES

Depois de cada alteração: `python3 -m unittest tests.test_core -q`
Não declares sucesso sem teste. Não mates uvicorn com `pkill` no mesmo bash dos testes. Um só processo na porta 8000. Qdrant: `stop_process` + `rm data/qdrant/.lock` se stale.

---

## RELATÓRIO POR FASE

Em cada entrega informa: analisado · alterado · porquê · ficheiros · dependências novas (idealmente zero) · testes · resultado · problemas · próximo passo.

Prioridade: **Verdade → Precisão → Segurança → Utilidade → Eficiência → Simplicidade.**

O objectivo é uma GOD real, não uma demonstração visual da HumanAI.
