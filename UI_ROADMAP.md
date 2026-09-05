# GOD UI ROADMAP

---

## CURRENT (v4) ✅

**GOD CORE + Living Interface + Event-Driven + Personality**

### GOD CORE ✅
- [x] Organic breathing orb (4 layers, cubic-bezier)
- [x] 8 states (idle/ready/listening/thinking/tools/responding/error/offline)
- [x] Event-driven via SSE (11 events)
- [x] Personality messages in Portuguese
- [x] Auto-return to ready after 3 seconds
- [x] Interactive hover effect (scale)

### Intelligence ✅
- [x] SSE-driven GOD CORE states
- [x] Latency sparkline (SVG, last N requests)
- [x] Provider health display
- [x] Active model display
- [x] Route visualization

### Performance ✅
- [x] Performance history (SQLite, last 10 requests)
- [x] Latency stats (avg/min/max)
- [x] MEASURED/ESTIMATED/TARGET separation
- [x] Resource Governor modes (ECO/NORMAL/PERFORMANCE)

### Voice ✅
- [x] TTS via edge-tts
- [x] Capability distinction (TTS/STT/Input/Duplex)
- [x] Voice badge shows TTS status

### Nodes ✅
- [x] Node Registry (capability-based)
- [x] Local node auto-registered
- [x] Node visualization in UI
- [x] API: GET/POST/DELETE /api/system/nodes

### Proactive Messages ✅
- [x] Budget exceeded alert
- [x] Quality drop alert
- [x] PC overload alert
- [x] Provider gap alert
- [x] Budget recovery message

### UI ✅
- [x] Sidebar navigation (8 pages)
- [x] KPIs with real data
- [x] System Map
- [x] Nodes panel
- [x] Providers panel
- [x] Performance panel (sparkline + stats)
- [x] Activity Feed (live)
- [x] Chat with quick actions + timestamps
- [x] Typing indicator
- [x] Responsive (mobile/tablet/desktop)
- [x] prefers-reduced-motion
- [x] No WebGL/Canvas/Three.js
- [x] Performance optimized

### Truth Model ✅
- [x] Classification system (IMPLEMENTED/TESTED/ENABLED/ACTIVE/MEASURED/ESTIMATED/TARGET/UNKNOWN/BLOCKED/MISSING)
- [x] All capabilities audited
- [x] Documentation consistent

---

## NEXT (v4.1)

**Chat Enhancement**

- [ ] Code syntax highlighting
- [ ] Markdown rendering
- [ ] File upload support

**System Map Enhancement**

- [ ] Interactive nodes (click to see details)
- [ ] Connection lines between modules
- [ ] Data flow visualization
- [ ] Worker topology view

**Advanced Monitoring**

- [ ] Alert history with acknowledgement
- [ ] Performance baselines
- [ ] Anomaly detection visualization
- [ ] Resource prediction

---

## FUTURE (v5)

**Advanced Visualization**

- [ ] Task dependency graph (SVG, interactive)
- [ ] Memory knowledge graph
- [ ] Evolution timeline
- [ ] Provider comparison matrix
- [ ] Token cost breakdown chart

**GOD Personality**

- [ ] Mood indicator based on system state
- [ ] Contextual suggestions
- [ ] Learning curve visualization

**Multi-Window**

- [ ] Detachable panels
- [ ] Custom layout save/restore
- [ ] Multi-monitor support

**Accessibility**

- [ ] High contrast mode
- [ ] Font size controls
- [ ] Screen reader optimization
- [ ] Keyboard shortcuts overlay

**Future Devices**

- [ ] Samsung A23 integration
- [ ] Audio input/output
- [ ] Camera access
- [ ] Context awareness

---

## DESIGN PRINCIPLES (Standing)

1. **Living but light** — CSS/SVG only, no GPU impact
2. **Real data only** — Never mock, show N/A when unavailable
3. **Feminine AI personality** — Elegant, calm, competent
4. **Professional** — Not a game demo, a tool
5. **Responsive** — Works everywhere
6. **Accessible** — respects reduced-motion, keyboard nav
7. **Event-driven** — React to real backend events
8. **Truth Model** — Distinguish IMPLEMENTED/TESTED/ENABLED/ACTIVE

---

## PERFORMANCE TARGETS (Standing)

| Metric | Target | Status |
|--------|--------|--------|
| Idle CPU | < 3% | TARGET |
| Active CPU | < 15% | TARGET |
| Idle RAM | < 250MB | TARGET |
| GPU | 0% | TARGET |
| Animations | CSS/SVG only | ✅ ACHIEVED |
| Bundle | < 50KB | ✅ ACHIEVED (~30KB) |
| External deps | 0 | ✅ ACHIEVED |

---

## VERSION HISTORY

```
v4.0 — GOD CORE organic breathing orb
v4.1 — Event-driven states + Performance history
v4.2 — Resource Governor + Voice distinction
v4.3 — Node Registry + Proactive messages
v4.4 — Truth Model + Documentation consistency
v4.5 — Chat timestamps + Typing indicator
v4.6 — Performance panel + Sparkline + Telemetry
v4.7 — GOD CORE hover effect + Visual polish
v5.0 — Chat enhancement + Interactive system map
```
