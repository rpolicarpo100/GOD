# Provider Tiers — Estratégia 2026-09-05

## Estado Actual (6/8 providers)

| Provider | Tier | Custo | Velocidade | Modelos |
|----------|------|-------|------------|---------|
| ✅ Groq | PRIMARY | Gratuito | Muito rápido | qwen/qwen3.8-27b, allam-2-7b |
| ✅ Cerebras | PRIMARY | Gratuito | Muito rápido | gemma-4-31b, qwen-3.8-27b |
| ✅ Claude | PRIMARY | Pago | Médio | claude-opus-5, claude-sonnet-5 |
| ✅ OpenRouter | SECONDARY | Gratuito | Médio | 14+ modelos gratuitos |
| ✅ Inference.net | SECONDARY | Gratuito | Médio | claude-fable-5, claude-haiku-4-5 |
| ✅ Z.ai | SECONDARY | Gratuito | Médio | glm-4.5, glm-4.5-air |
| ❌ Gemini | — | — | — | — |
| ❌ Ollama | — | — | — | — |

## Providers Disponíveis (não temos)

| Provider | Free Tier | Credit Card? | Modelos | Velocidade | Recomendação |
|----------|-----------|--------------|---------|------------|--------------|
| **Google Gemini** | ✅ Permanente | Não | Gemini 3.5/3.6 Flash, Gemma 4 | Rápido | ✅ ADICIONAR |
| **NVIDIA NIM** | ✅ ~40 RPM | Não | DeepSeek, Llama, Nemotron, Gemma | Rápido | ✅ ADICIONAR |
| **Mistral AI** | ✅ Free mode | Não | Large, Medium, Small, Codestral | Médio | ✅ ADICIONAR |
| **Cohere** | ✅ 1000 calls/mês | Não | Command A/R, Aya, rerank, embed | Médio | ⚠️ OPCIONAL |
| **SambaNova** | ✅ 200K tokens/dia | Não | DeepSeek-V3.1, Llama-3.3-70B | Rápido | ⚠️ OPCIONAL |
| **GitHub Models** | ✅ Free para GitHub | Não | GPT-4.1, GPT-5, o3, o4-mini | Médio | ⚠️ OPCIONAL |
| **Cloudflare Workers AI** | ✅ 10K Neurons/dia | Não | Llama, Qwen, Mistral, GLM | Edge | ❌ NÃO (sem integração) |
| **Hugging Face** | ✅ $0.10/mês | Não | 4 modelos gratuitos | Variável | ⚠️ OPCIONAL (para Whisper) |

## Recomendação Final

### Tier 1 — PRIMARY (principais, usar para tudo)

| Provider | Prioridade | Razão |
|----------|------------|-------|
| **Groq** | 1 | Mais rápido, gratuito, modelos bons |
| **Cerebras** | 2 | Muito rápido, gratuito, modelos bons |
| **Claude** | 3 | Melhor qualidade, pago, HARDCORE MODE |

**Uso:** Requests principais, respostas rápidas, tarefas importantes.

### Tier 2 — SECONDARY (substituição rápida, side tasks)

| Provider | Prioridade | Razão |
|----------|------------|-------|
| **OpenRouter** | 4 | Agrega 14+ modelos gratuitos, fallback universal |
| **Inference.net** | 5 | Gratuito, modelos Claude (alternativa ao Claude pago) |
| **Z.ai** | 6 | Gratuito, modelos GLM (diferentes dos outros) |
| **Google Gemini** | 7 | Gratuito, Gemini Flash rápido, modelos diferentes |
| **NVIDIA NIM** | 8 | Gratuito, DeepSeek, Llama, Nemotron |

**Uso:** Quando PRIMARY falha, side tasks, diversidade de modelos.

### Tier 3 — BRAINSTORMING (chamado por PRIMARY ou SECONDARY)

| Provider | Prioridade | Razão |
|----------|------------|-------|
| **Mistral AI** | 9 | Gratuito, modelos Europeus, Codestral para código |
| **Cohere** | 10 | Gratuito, rerank e embed (útil para RAG) |
| **SambaNova** | 11 | Gratuito, DeepSeek-V3.1 (diferente) |
| **GitHub Models** | 12 | Gratuito, GPT-4.1, GPT-5 (se disponível) |

**Uso:** Brainstorming, comparação de modelos, tarefas específicas (código, RAG).

## Providers a Adicionar Agora

### Prioridade Alta (adicionar agora):

1. **Google Gemini** — `GOOGLE_API_KEY`
   - Free tier permanente, sem cartão
   - Gemini 3.5/3.6 Flash (rápido)
   - Gemma 4 (open-source)
   - Modelo diferente dos outros providers

2. **NVIDIA NIM** — `NVIDIA_API_KEY`
   - Free tier, sem cartão
   - DeepSeek, Llama, Nemotron, Gemma
   - Rápido, modelos diferentes

3. **Mistral AI** — `MISTRAL_API_KEY`
   - Free mode, sem cartão
   - Large, Medium, Small, Codestral
   - Modelos Europeus, bom para código

### Prioridade Média (adicionar se necessário):

4. **Cohere** — `COHERE_API_KEY`
   - Free trial, 1000 calls/mês
   - Command A/R, Aya, rerank, embed
   - Útil para RAG (rerank)

5. **SambaNova** — `SAMBANOVA_API_KEY`
   - Free tier, 200K tokens/dia
   - DeepSeek-V3.1, Llama-3.3-70B
   - Rápido

## Configuração Recomendada

```env
# Tier 1 — PRIMARY
GROQ_API_KEY=... (já configurado)
CEREBRAS_API_KEY=... (já configurado)
ANTHROPIC_API_KEY=... (já configurado)

# Tier 2 — SECONDARY
OPENROUTER_API_KEY=... (já configurado)
INFERENCE_API_KEY=... (já configurado)
ZAI_API_KEY=... (já configurado)
GOOGLE_API_KEY=... (adicionar)
NVIDIA_API_KEY=... (adicionar)

# Tier 3 — BRAINSTORMING
MISTRAL_API_KEY=... (adicionar)
COHERE_API_KEY=... (opcional)
SAMBANOVA_API_KEY=... (opcional)
```

## Resumo

| Tier | Providers | Função |
|------|-----------|--------|
| PRIMARY | Groq, Cerebras, Claude | Requests principais, respostas rápidas |
| SECONDARY | OpenRouter, Inference.net, Z.ai, Gemini, NVIDIA NIM | Substituição rápida, side tasks |
| BRAINSTORMING | Mistral, Cohere, SambaNova, GitHub Models | Brainstorming, comparação, tarefas específicas |

**Total recomendado:** 11 providers (6 actuais + 5 novos)
