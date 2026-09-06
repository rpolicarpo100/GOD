# GOD — Recomendações Adicionais (Fase 2)
**Data:** 2026-09-06 | **Base:** Análise pós-implementação das 10 primeiras

---

## 🔴 CRÍTICAS (Impacto no produto)

### 11. STREAMING TOKEN-A-TOKEN (já recomendado, não implementado)
**Impacto:** ⭐⭐⭐⭐ | **Esforço:** Alto

O utilizador espera sempre a resposta completa. Com LLMs a 2-3s, a experiência parece lenta.
- `providers.py`: adicionar `stream=True`, iterar SSE lines
- `routing.py`: propagar callback `on_token`
- `pipeline.py`: usar callback em vez de esperar resposta completa
- `server.py`: endpoint SSE ou chunked response
- `index.html`: append tokens ao último `.m.brain` em tempo real

**Estimativa:** Latência percebida de 2.9s → ~200ms (primeiro token).

---

### 12. VOICE INPUT (STT) — O micro já existe no dashboard mas não faz nada
**Impacto:** ⭐⭐⭐ | **Esforço:** Médio

O dashboard mostra badge "MIC" mas não há STT implementado. `voice.py` só tem TTS.
- Usar Web Speech API do browser (gratuito, 0 dependências)
- Ou Whisper via Groq (já suporta whisper nos models)
- Activar com clique no badge MIC ou shortcut Ctrl+M

```javascript
// Web Speech API (nativo no browser)
const recognition = new webkitSpeechRecognition();
recognition.lang = 'pt-PT';
recognition.onresult = (e) => {
  $('chat-i').value = e.results[0][0].transcript;
};
```

---

### 13. PROVIDER HEALTH AUTO-RECOVERY
**Impacto:** ⭐⭐⭐ | **Esforço:** Baixo

Quando um provider falha, o GOD não tenta novamente. O health check é feito uma vez no startup.
- Background task a cada 60s: re-probe providers em background
- Se um provider volta, actualizar status e notificar
- Evitar re-probe durante requests activas (race condition)

```python
# No runtime, thread separada:
def _health_loop():
    while True:
        time.sleep(60)
        providers.health_all(force=True)
```

---

### 14. RATE LIMITING PER PROVIDER
**Impacto:** ⭐⭐ | **Esforço:** Baixo

`rate_limit.py` existe mas só protege o server. Providers como Groq têm free tier limits.
- Track requests/min per provider
- Se approaching limit, preferir outro provider
- Cooldown period após 429 response

---

## 🟡 IMPORTANTES (Qualidade do produto)

### 15. TESTES POR MÓDULO (49 módulos, 0 testes unitários)
**Impacto:** ⭐⭐⭐ | **Esforço:** Alto

Todos os testes estão em `tests/test_core.py` (monolito). Nenhum módulo tem testes próprios.
- Criar `tests/test_brain.py` — testar analyze(), _classify_by_embedding()
- Criar `tests/test_pipeline.py` — testar stages isoladamente
- Criar `tests/test_routing.py` — testar provider racing
- Criar `tests/test_shortcuts.py` — testar cada shortcut
- Criar `tests/test_observer.py` — testar alertas, suggestions

**Prioridade:** brain, pipeline, routing (core path)

---

### 16. CONVERSATION MEMORY PERSISTENTE
**Impacto:** ⭐⭐ | **Esforço:** Médio

O `_chat` é in-memory — perde-se quando o servidor reinicia. O utilizador perde contexto.
- Guardar `_chat` em SQLite a cada `_say()`
- Restaurar no startup com `boot()`
- Limitar a últimas 200 mensagens (trim automático)

---

### 17. DASHBOARD RESPONSIVE MELHORADO
**Impacto:** ⭐⭐ | **Esforço:** Médio

O dashboard funciona em mobile mas não é optimizado:
- KPIs ficam tiny em ecrãs pequenos
- System Map não é legível em mobile
- Chat input demasiado pequeno
- Panels não colapsam automaticamente em mobile

---

### 18. MULTI-MODEL STRATEGY
**Impacto:** ⭐⭐ | **Esforço:** Médio

Actual: usa o primeiro provider disponível. Não distingue modelos por tarefa.
- **Simple queries** → modelo rápido/barato (Groq/qwen)
- **Coding** → modelo forte (Claude, GPT-4)
- **Research** → modelo com contexto largo
- Usar `task.type` e `task.complexity` para escolher modelo

---

### 19. ERROR RECOVERY NO PIPELINE
**Impacto:** ⭐⭐ | **Esforço:** Baixo

Se uma stage do pipeline falha, o GOD retorna erro genérico. Devia:
- Tentar fallback (ex: se LLM falha → usar cache stale)
- Se memory search falha → continuar sem memória
- Se tools falham → informar e sugerir alternativa

---

### 20. WEB SEARCH REAL (SearXNG ou DuckDuckGo)
**Impacto:** ⭐⭐ | **Esforço:** Baixo (já existe!)

`websearch.py` já tem DuckDuckGo fallback! Mas o shortcut recusa se SearXNG não está.
- Verificar se DDG funciona no ambiente do utilizador
- Se sim, usar DDG como search engine activo
- Mostrar resultados no chat com links clicáveis

---

## 🟢 NICE-TO-HAVE (Experiência)

### 21. THEME PERSISTENCE POR SESSÃO
O dashboard tem3 temas (midnight/dawn/neon) mas não guarda a escolha por sessão do utilizador (só localStorage).

### 22. CHAT EXPORT MELHORADO
Export já existe (JSON) mas falta:
- Export como Markdown legível
- Export com timestamps formatados
- Import de conversas anteriores

### 23. KEYBOARD SHORTCUTS PARA CHAT
- Ctrl+Enter → enviar (toggle com Enter)
- Ctrl+L → limpar chat
- Ctrl+/ → slash commands (/estado, /tokens, /roadmap)

### 24. NOTIFICATION TOASTS
Em vez de só mudar o badge do header, mostrar toast notifications:
- "GOD respondeu" (quando chat fechado)
- "Provider Groq online" (quando reconecta)
- "Cache hit — resposta instantânea" (quando usa cache)

### 25. DASHBOARD METRICS NO TERMINAL
Mostrar no terminal do servidor:
```
[20:07:25] GET /api/state 200 — 12ms
[20:07:25] POST /api/chat 200 — 2900ms (Groq/qwen, cache=miss)
```

---

## 📋 Prioridade Actualizada

| # | Recomendação | Impacto | Esforço | Estado |
|---|-------------|---------|---------|--------|
| 1 | Streaming | ⭐⭐⭐⭐ | Alto | Pendente |
| 2 | Voice Input (STT) | ⭐⭐⭐ | Médio | Pendente |
| 3 | Provider Auto-Recovery | ⭐⭐⭐ | Baixo | Pendente |
| 4 | Testes por módulo | ⭐⭐⭐ | Alto | Pendente |
| 5 | Rate Limit per Provider | ⭐⭐ | Baixo | Pendente |
| 6 | Conversation Memory Persist | ⭐⭐ | Médio | Pendente |
| 7 | Multi-Model Strategy | ⭐⭐ | Médio | Pendente |
| 8 | Error Recovery Pipeline | ⭐⭐ | Baixo | Pendente |
| 9 | Web Search DDG | ⭐⭐ | Baixo | Já existe! |
| 10 | Dashboard Responsive | ⭐⭐ | Médio | Pendente |

---

*Gerado após implementação das10 primeiras recomendações (5c89d5e)*
