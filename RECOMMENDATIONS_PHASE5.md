# GOD — Recomendações Fase 5: Chat, UX, Temas
**Data:** 2026-09-06 | **Foco:** Experiência do utilizador

---

## 🔴 CHAT (O que falta para chat profissional)

### 1. MODEL SELECTOR NO CHAT
O utilizador não pode escolher qual LLM usar. Pipeline decide automaticamente.
- Dropdown no header do chat: "Auto" | "Groq/qwen" | "Cerebras/llama" | "Claude"
- Envia com `prefer` param no POST /api/chat
- Persiste preferência em localStorage

### 2. DRAG-DROP FILE UPLOAD
Upload existe via botão 📎 mas drag-drop é mais natural.
- Event listeners `dragover`/`drop` na area do chat
- Preview do ficheiro antes de enviar
- Paste de imagens do clipboard (`paste` event)
- Visual feedback (border glow quando arrasta)

### 3. CHAT TEMPLATES EXPANDIDOS
Quick buttons existem mas são limitados. Expandir com categorias:
- **Análise:** "Analisa este código" | "Revê este texto" | "Resume isto"
- **Criação:** "Escreve um script" | "Cria uma API" | "Faz um site"
- **Debug:** "Porque não funciona?" | "Encontra o bug" | "Optimiza isto"
- **Sistema:** "Estado" | "Performance" | "Providers" | "Cache"

### 4. CONVERSATION THREADS
Uma conversa linear é limitada.
- Branch em qualquer mensagem do GOD
- Sidebar mostra árvore de threads
- Click para navegar entre branches
- Merge de threads de volta à conversa principal

### 5. MARKDOWN MELHORADO
O renderMd() já suporta markdown mas falta:
- Tabelas com scroll horizontal
- Code blocks com syntax highlighting melhorado
- LaTeX/math rendering (básico)
- Mermaid diagrams (renderização SVG)
- Copy button por code block (já existe)

### 6. CHAT REACTIONS MELHORADAS
Reactions existem (👍👎) mas são locais.
- Persistir reactions em SQLite
- Mostrar contagem agregada
- Mais emojis: 🎯⚡🔥💡🤔

---

## 🎨 TEMAS + VISUAL

### 7. CUSTOM THEME BUILDER
3 temas fixos (midnight/dawn/neon). Permitir customização:
- Color picker para accent color
- Toggle dark/light mode
- Opacidade do glass effect
- Guardar tema custom como nome

### 8. ANIMAÇÕES MELHORADAS
Transições são básicas.
- Page transitions com slide/fade
- Panel collapse com spring animation
- KPI counter animation (número a subir)
- Orb pulse sincronizado com heartbeat real do sistema

### 9. GLASSMORPHISM MELHORADO
O glass effect é sutil. Melhorar:
- Backdrop-filter blur mais visível
- Gradient borders em panels activos
- Glow effect em KPIs com valores críticos
- Depth shadows em elementos hover

### 10. TYPOGRAPHY SYSTEM
Fontes são definidas ad-hoc.
- System font stack optimizado
- Font scale consistente (8/10/11/13/15/22px)
- Letter-spacing por hierarchy
- Line-height optimizado para leitura

---

## 📱 MOBILE

### 11. MOBILE-FIRST CHAT
Chat não é optimizado para mobile.
- Full-screen chat em mobile (bottom sheet)
- Swipe up para abrir, swipe down para fechar
- Input fixo no bottom com teclado virtual
- Voice input mais proeminente em mobile

### 12. MOBILE NAV
Rail não funciona bem em mobile.
- Bottom tab bar em mobile (5 tabs max)
- Swipe entre pages
- Pull-to-refresh no estado
- Gestures para voltar

### 13. RESPONSIVE KPIs
KPIs ficam tiny em mobile.
- Stack vertical em mobile (2 colunas)
- Font size maior em mobile
- Touch targets mínimo 44px

---

## 🔔 NOTIFICAÇÕES

### 14. NOTIFICATION CENTER
Toasts desaparecem. Falta persistência.
- Ícone sino no header com badge
- Painel com histórico de notificações
- Mark all as read
- Filter por tipo (alert, info, success)

### 15. PUSH NOTIFICATIONS
Para quando GOD responde em background.
- Notification API do browser
- Request permission no primeiro chat
- "GOD respondeu" notification quando tab não está activa

---

## ⚡ PERFORMANCE

### 16. VIRTUAL SCROLLING NO CHAT
Se o chat tem muitas mensagens, innerHTML fica lento.
- Virtual scroll: só renderiza mensagens visíveis
- Recicla DOM elements
- Mantém scroll position

### 17. LAZY LOADING DE PAGES
Todas as pages são renderizadas no load.
- Só renderiza page activa
- Lazy load quando se navega pela primeira vez
- Cache de pages visitadas

### 18. DEBOUNCE NO SSE
SSE snapshots chegam a cada 200ms. Muitas re-renderizações.
- Debounce pChat() para max 5 renders/second
- RequestAnimationFrame para paint()
- Batch updates

---

## 📋 Prioridade

| # | Recomendação | Impacto | Esforço | Rating |
|---|-------------|---------|---------|--------|
| 1 | Model selector | ⭐⭐⭐ | 1h | +2 |
| 2 | Drag-drop upload | ⭐⭐ | 1h | +1 |
| 3 | Mobile chat | ⭐⭐⭐ | 2h | +2 |
| 4 | Chat templates | ⭐⭐ | 30min | +1 |
| 5 | Notification center | ⭐⭐ | 1h | +1 |
| 6 | Custom theme | ⭐⭐ | 1.5h | +1 |
| 7 | Page transitions | ⭐⭐ | 1h | +1 |
| 8 | Virtual scrolling | ⭐⭐ | 2h | +1 |
| 9 | Threads | ⭐⭐ | 3h | +2 |
| 10 | Push notifications | ⭐ | 1h | +1 |

*Total para 85/100: ~14h*
