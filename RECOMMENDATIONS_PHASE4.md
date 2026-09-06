# GOD — Recomendações Fase 4: Rating 76-90/100
**Data:** 2026-09-06 | **Estado:** 164 testes, 0 falhas, 43 features, ~70/100

---

## 🏆 Para 76/100 — PROFISSIONALISMO

### 1. BACKUP/RESTORE AUTOMÁTICO
**Impacto:** ⭐⭐⭐ | **Esforço:** 30min

A BD SQLite é o coração do GOD. Se corromper, perde tudo.
- `/api/admin/backup` → exporta `data/god.db` como download
- Backup automático a cada 6h para `data/backups/`
- Retenção: últimos 7 backups

### 2. GRACEFUL SHUTDOWN
**Impacto:** ⭐⭐ | **Esforço:** 15min

Ctrl+C no servidor mata tudo sem limpar estado.
- SIGTERM handler → flush cache, persist chat, close connections
- Log "GOD shutting down gracefully"

### 3. GLOBAL ERROR HANDLER
**Impacto:** ⭐⭐ | **Esforço:** 15min

Exceptions não apanhadas retornam stack trace ao utilizador.
- `@app.exception_handler(Exception)` → JSON genérico em produção, detalhe em dev
- Log do erro completo

### 4. PROVIDER STATUS NO HEADER
**Impacto:** ⭐⭐ | **Esforço:** 20min

O badge mostra "Healthy" mas não diz qual provider está up.
- Badge "Groq ✓" ou "Cerebras ✓" no header
- Tooltip com todos os providers e status

### 5. CONVERSATION SEARCH (SERVER-SIDE)
**Impacto:** ⭐⭐ | **Esforço:** 30min

Chat search só filtra no client. Passado fica perdido.
- `/api/chat/search?q=termo` → pesquisa em `_chat` + memória SQLite
- Devolve resultados com contexto

### 6. CONFIG VIA API
**Impacto:** ⭐⭐ | **Esforço:** 15min

`/api/config` GET/PUT já existe implicitamente via `set_params`. Falta:
- GET `/api/config` → retorna config actual (sem secrets)
- PATCH `/api/config` → aplica alterações com validação

---

## 🚀 Para 80/100 — ESCALABILIDADE

### 7. UNIT TESTS POR MÓDULO
**Impacto:** ⭐⭐⭐⭐ | **Esforço:** 4h

49 módulos, todos os testes no monolito `test_core.py`.
- `tests/test_brain.py` — analyze(), _classify_by_embedding(), firewall()
- `tests/test_pipeline.py` — cada stage isoladamente
- `tests/test_routing.py` — provider racing, fallback
- `tests/test_shortcuts.py` — cada shortcut handler
- `tests/test_store.py` — cache, memory, tasks CRUD
- `tests/test_observer.py` — alerts, suggestions

### 8. INTEGRATION TESTS
**Impacto:** ⭐⭐⭐ | **Esforço:** 2h

Nenhum teste cobre os endpoints HTTP.
- `tests/test_api.py` — testa /api/state, /api/chat, /api/health via httpx
- Usar `TestClient` do FastAPI

### 9. ASYNC PIPELINE
**Impacto:** ⭐⭐⭐ | **Esforço:** 3h

O pipeline é síncrono — bloqueia a thread durante LLM call.
- Converter `run_pipeline` para `async`
- `await routing.complete()` — libera event loop
- Permite múltiplos chats simultâneos

### 10. CONNECTION POOLING
**Impacto:** ⭐⭐ | **Esforço:** 30min

Cada request ao provider cria uma nova conexão HTTP.
- `httpx.Client()` com pool de 10 conexões por adapter
- Reutilizar TCP connections — menos latência

### 11. WEBSOCKET BI-DIRECTIONAL
**Impacto:** ⭐⭐ | **Esforço:** 2h

SSE é unidirecital. WebSocket permite:
- Streaming bidirecional
- Typing indicators em tempo real
- Cancelamento de requests em curso
- Ping/pong para detectar disconnects

### 12. LATENCY SPARKLINE POR PROVIDER
**Impacto:** ⭐⭐ | **Esforço:** 30min

Intelligence page mostra providers mas sem histórico.
- Mini sparkline SVG por provider nos últimos 20 pedidos
- Cor: verde < 1s, amarelo < 3s, vermelho > 3s

---

## 🧠 Para 85/100 — INTELIGÊNCIA

### 13. CONVERSATION SUMMARIZATION (LLM)
**Impacto:** ⭐⭐⭐ | **Esforço:** 2h

O sumário conversacional actual usa keyword extraction. Pode ser mais inteligente.
- A cada 20 mensagens, pedir ao LLM para resumir
- Guardar sumário em memória como knowledge entry
- Injectar no prompt como "Contexto da conversa"

### 14. SMART MODEL SELECTION
**Impacto:** ⭐⭐⭐ | **Esforço:** 2h

O multi-model strategy actual só ajusta tokens. Falta:
- Escolher provider baseado em: latência histórica, custo, qualidade
- Track quality_score por provider por tipo de tarefa
- Preferir provider com melhor score para o tipo

### 15. TOOL USE VIA LLM
**Impacto:** ⭐⭐⭐ | **Esforço:** 4h

O GOD tem ferramentas mas o LLM não as invoca directamente.
- Function calling / tool_use nativo (Groq, OpenRouter, Claude suportam)
- LLM decide que ferramenta usar em vez do pipeline determinístico
- Ex: "lista os ficheiros" → LLM chama `fs.list` directamente

### 16. RAG (Retrieval Augmented Generation)
**Impacto:** ⭐⭐⭐ | **Esforço:** 3h

A memória é usada para context pack mas não de forma inteligente.
- Embed todos os episódios + knowledge
- Antes de cada LLM call, buscar top-5 mais relevantes via vector search
- Injectar como "Contexto relevante" no prompt

### 17. FOLLOW-UP DETECTION
**Impacto:** ⭐⭐ | **Esforço:** 1h

"e o CSS?" devia perceber que é continuação da conversa anterior.
- Detectar anáforas (isto, isso, e o X, continua)
- Resolução via contexto conversacional (já temos _build_conversation_summary)

---

## 🎨 Para 90/100 — EXPERIÊNCIA

### 18. DRAG-DROP FILE UPLOAD
**Impacto:** ⭐⭐ | **Esforço:** 1h

O upload existe mas é via botão. Drag-drop é mais natural.
- Event listeners dragover/drop no chat
- Preview do ficheiro antes de enviar
- Suporte paste de imagens (clipboard)

### 19. CONVERSATION THREADS
**Impacto:** ⭐⭐ | **Esforço:** 2h

Uma conversa linear é limitada. Threads permitem:
- Branch em qualquer mensagem
- Explorar hipóteses sem perder contexto
- Visualização em árvore

### 20. MODEL SELECTOR NO UI
**Impacto:** ⭐⭐ | **Esforço:** 1h

O utilizador não pode escolher qual LLM usar.
- Dropdown no chat: "Auto", "Groq/qwen", "Cerebras/llama", "Claude"
- Default: Auto (pipeline decide)
- Persistir preferência

### 21. CHAT TEMPLATES
**Impacto:** ⭐⭐ | **Esforço:** 30min

Quick buttons existem (Estado, Roadmap, etc). Expandir:
- "Analisa este código" → abre file picker
- "Escreve testes" → pede para seleccionar módulo
- "Refactoriza" → pede para colar código
- "Documenta" → pede para seleccionar ficheiro

### 22. MOBILE OPTIMIZATION
**Impacto:** ⭐⭐ | **Esforço:** 2h

O dashboard funciona em mobile mas não é optimizado.
- Touch gestures para navegar entre pages
- Bottom sheet para chat em mobile
- Responsive KPIs (stack em vez de row)
- Swipe para voltar à page anterior

### 23. NOTIFICATION CENTER
**Impacto:** ⭐ | **Esforço:** 1h

Toast notifications desaparecem. Falta:
- Ícone sino no header com badge de notificações não lidas
- Painel com histórico de notificações
- Mark all as read

### 24. VOICE OUTPUT (TTS) NO CHAT
**Impacto:** ⭐⭐ | **Esforço:** 1h

voice.py já tem TTS via edge-tts. Só precisa de:
- Botão 🔊 em cada mensagem brain para ouvir
- `/api/tts` endpoint que gera MP3
- Audio player no chat

### 25. PWA (Progressive Web App)
**Impacto:** ⭐ | **Esforço:** 1h

O GOD pode ser instalado como app no desktop/mobile.
- manifest.json com ícone
- Service worker para offline (mostra última snapshot)
- "Install" prompt

---

## 📊 Prioridade Final

| # | Recomendação | Impacto | Rating | Esforço |
|---|-------------|---------|--------|---------|
| 1 | Unit tests por módulo | ⭐⭐⭐⭐ | +4 | 4h |
| 2 | RAG | ⭐⭐⭐ | +3 | 3h |
| 3 | Tool use via LLM | ⭐⭐⭐ | +3 | 4h |
| 4 | Async pipeline | ⭐⭐⭐ | +2 | 3h |
| 5 | Smart model selection | ⭐⭐⭐ | +2 | 2h |
| 6 | Integration tests | ⭐⭐⭐ | +2 | 2h |
| 7 | Backup/restore | ⭐⭐⭐ | +1 | 30min |
| 8 | Conversation summarization | ⭐⭐ | +2 | 2h |
| 9 | Global error handler | ⭐⭐ | +1 | 15min |
| 10 | Graceful shutdown | ⭐⭐ | +1 | 15min |
| 11 | Connection pooling | ⭐⭐ | +1 | 30min |
| 12 | WebSocket | ⭐⭐ | +1 | 2h |
| 13 | Provider status header | ⭐⭐ | +1 | 20min |
| 14 | Latency sparkline/provider | ⭐⭐ | +1 | 30min |
| 15 | Conversation search server | ⭐⭐ | +1 | 30min |
| 16 | Config via API | ⭐⭐ | +1 | 15min |
| 17 | Follow-up detection | ⭐⭐ | +1 | 1h |
| 18 | Model selector UI | ⭐⭐ | +1 | 1h |
| 19 | Drag-drop upload | ⭐⭐ | +1 | 1h |
| 20 | Chat templates | ⭐⭐ | +1 | 30min |
| 21 | TTS no chat | ⭐⭐ | +1 | 1h |
| 22 | Conversation threads | ⭐⭐ | +1 | 2h |
| 23 | Mobile optimization | ⭐⭐ | +1 | 2h |
| 24 | Notification center | ⭐ | +1 | 1h |
| 25 | PWA | ⭐ | +1 | 1h |

**Total para 90/100:** ~35h de trabalho (~2h com agent)

---

*Análise: 49 módulos, 13.372 LOC, 161 commits, 164 testes, 43 features, 7 commits profissionais*
