# GOD — log para o próximo trabalhador

Data: 2026-09-04. Ela = GOD. Host 2 CPU ~2 GB, GPU `required=false`.

## Passo actual
Código em `/home/user/super-ai`, live **uvicorn :8000**. Versão `0.3.0`. Modo **OFFLINE**.

## Feito (no disco + processo)
- Cérebro LLM-last, tools, Governor, cache, Qdrant embedded (hashing, não neural)
- Fila + worker `control-local`, observer, Token Intel, OS kernel
- Dashboard vivo (não tabs de docs)
- 47 testes OK na corrida do OS

## A fazer
1. Um LLM verificado (Ollama a correr **ou** key) — sem isto ela não conversa como modelo
2. ~~GitHub~~ **feito** https://github.com/rpolicarpo100/GOD
3. Plane: API user ok; **produto ainda sem adapter / workspace**
4. Limpar `session_tokens=9240` (lixo de testes, não Claude)

## Deploy GitHub
**SIM** — `main` em https://github.com/rpolicarpo100/GOD (`840d3d5` e commits seguintes). Deploy key SSH neste host. Sem secrets no repo.

## Não fazer
Reescrever Brain/Router/Governor. Inventar providers, preços, poupanças €, scores de modelos. Segundo processo com `memory_vec` enquanto `:8000` tem `data/qdrant`.
