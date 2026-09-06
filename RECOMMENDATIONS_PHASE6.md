# PHASE 6 — Auto-Learning + Speed Recommendations

## Current State Analysis

### What EXISTS (strengths):
- L1 hash cache + L2 semantic cache (Qdrant + FastEmbed)
- Evolution engine (observe → hypothesize → experiment → adopt/reject)
- Knowledge extraction (basic keyword: "prefiro", "gosto de")
- Self-reflection (if score < 0.5, re-prompt)
- Provider ranking by ok_rate + latency
- Provider racing (top2 parallel)
- Concurrent cache + memory pipeline stages
- Fast path for status/math/parse
- Shortcut caching (30s TTL)
- Rating system (OVERALL, QUALITY, CORRECTNESS, etc.)
- SQLite WAL mode

### What's MISSING:

## 🔴 AUTO-LEARNING (HIGH IMPACT)

### 1. Adaptive Prompting — Learn from successful interactions
**Gap:** `_extract_and_store_knowledge()` only catches "prefiro"/"gosto" keywords. No semantic extraction.
**Fix:** After each successful interaction (OVERALL ≥ 70), extract key patterns:
- What task type + provider produced best results
- What response style the user prefers (short vs long, code vs explanation)
- What complexity level the user typically asks
**Impact:** GOD learns user style over time → better first-attempt responses

### 2. Provider Quality Predictor
**Gap:** `sort_adapters()` uses ok_rate + latency but ignores task-type fit. A provider great at "coding" may be bad at "research".
**Fix:** Track per-provider per-task-type quality scores. Route "coding" to best-coding provider, "research" to best-research.
**Impact:** +15-25% quality on first attempt (no self-reflection retry needed)

### 3. Context-Aware Memory Retrieval
**Gap:** Memory search uses raw query text. No conversation context in retrieval.
**Fix:** Augment memory query with last 2 dialogue turns + task type. Weight recent episodes higher.
**Impact:** More relevant memory hits → better context → higher quality

### 4. Self-Improving Shortcuts
**Gap:** Shortcuts are static regex patterns. No learning from usage frequency.
**Fix:** Track shortcut hit counts. Auto-promote frequent patterns. Learn new shortcut patterns from repeated queries.
**Impact:** More queries hit fast path → faster responses

### 5. Knowledge Graph from Interactions
**Gap:** Knowledge is stored flat (kind, key, value). No relations between facts.
**Fix:** Build simple subject-predicate-object triples from interactions. "User prefers Python" → (user, prefers, python).
**Impact:** Richer context for LLM prompts → better responses

### 6. Automatic Experiment Generation
**Gap:** Evolution only tests 3 hardcoded paraphrase pairs. No real experimentation.
**Fix:** Generate experiments from actual usage patterns: "Can we cache this type of query?" "Should we use a shorter prompt for status queries?"
**Impact:** Continuous improvement based on real usage

### 7. Reinforcement Learning for Routing
**Gap:** Provider ranking uses simple ok_rate average. No weighting by recency or task fit.
**Fix:** Exponential moving average with task-type dimension. Recent good results weight more. Decay stale data.
**Impact:** Routing adapts in real-time to provider performance

### 8. Proactive Knowledge Gap Detection
**Gap:** GOD doesn't know what it doesn't know. No "I should learn about X" detection.
**Fix:** When a query triggers self-reflection (score < 0.5), log the topic. After N failures on similar topics, flag as knowledge gap and suggest learning.
**Impact:** Identifies weaknesses → targeted improvement

## 🟡 SPEED (HIGH IMPACT)

### 9. Embedding Cache (LRU)
**Gap:** `embed()` recomputes embeddings every call. No caching. Cold start loads model.
**Fix:** LRU cache (256 entries) for embedding vectors. Warmup on boot.
**Impact:** -50ms per cache hit, eliminates cold-start latency for repeated queries

### 10. Intent Embedding Pre-warm
**Gap:** `_classify_by_embedding()` lazily computes intent embeddings on first call.
**Fix:** Pre-warm intent embeddings during `boot()` in background thread.
**Impact:** First query is 200-500ms faster

### 11. Batch Embedding
**Gap:** `embed()` is single-query. Memory search embeds one text at a time.
**Fix:** Add `embed_batch(texts)` that processes multiple texts in one FastEmbed call.
**Impact:** -30% latency for memory-heavy queries

### 12. Pipeline Stage Timing
**Gap:** No per-stage timing in pipeline. Can't identify bottlenecks.
**Fix:** Add `time.perf_counter()` around each stage (cache, memory, firewall, plan, tools, llm). Store in pipeline dict. Surface in `/api/status`.
**Impact:** Visibility into where time is spent → targeted optimization

### 13. httpx Connection Pooling (routing.py)
**Gap:** `routing.py` creates new httpx connections for OmniRoute health + complete calls.
**Fix:** Use a shared `httpx.Client()` with connection pooling (already done in providers.py).
**Impact:** -10-20ms per OmniRoute call

### 14. Cache Pre-warm for Frequent Queries
**Gap:** Cache is cold after restart. First N queries are slow.
**Fix:** On boot, pre-warm L1 cache from last 20 successful interactions stored in SQLite.
**Impact:** Post-restart queries are instant for common patterns

### 15. Parallel Tool Execution
**Gap:** Pipeline runs tools sequentially when independent.
**Fix:** When plan has multiple independent tool steps, run them in parallel with ThreadPoolExecutor.
**Impact:** -40% latency for multi-tool queries

### 16. Lazy Module Loading
**Gap:** Heavy imports (numpy, sklearn, qdrant) happen at module load time.
**Fix:** Already partially done (some are lazy). Ensure all heavy modules use lazy imports.
**Impact:** -200-500ms boot time

## 🟢 NICE-TO-HAVE

### 17. Conversation Memory Compression
**Gap:** `_dialogue()` returns last N raw messages. Long conversations bloat context.
**Fix:** Summarize older messages (>4 turns ago) into 1-line summaries.
**Impact:** Better context management for long sessions

### 18. Adaptive Token Budget
**Gap:** Token budgets are static (task=8000, session=50000, daily=200000).
**Fix:** Adjust based on time of day, usage patterns, and provider availability.
**Impact:** Better resource utilization

### 19. Response Quality Feedback Loop
**Gap:** Ratings are stored but not fed back into the system.
**Fix:** When user gives explicit feedback (TTS reactions, chat responses), use it to adjust quality thresholds and provider preferences.
**Impact:** Continuous improvement from user feedback

### 20. Multi-turn Context Optimization
**Gap:** `_llm_prompt()` always includes full dialogue context.
**Fix:** Compress context based on task type. Status queries need no history. Coding queries need relevant code context.
**Impact:** -30% tokens per query → faster + cheaper

## Implementation Priority

| Priority | Items | Expected Impact |
|----------|-------|-----------------|
| P0 (now) | 9, 10, 13, 14 | -100ms avg latency |
| P1 (next) | 1, 2, 7 | +20% quality, -15% retries |
| P2 | 3, 5, 11, 12 | Better context, visibility |
| P3 | 4, 6, 8, 15-20 | Long-term learning |
