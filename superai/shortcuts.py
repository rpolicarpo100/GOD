"""Shortcuts — handlers para comandos directos sem pipeline.

Extraído de runtime.py. Cada shortcut: pattern match → resposta rápida.
Não passa por analyze/plan/execute.
"""
from __future__ import annotations

import re
from typing import Any

from . import aios, benchmark, evolution, mission, observer, providers, queue as tq, tokens as ti
from .config import cfg
from .events import bus
from .governor import gov


def _handle_token_report(_say, _broadcast) -> dict:
    snap = ti.snapshot()
    u, b, f, c = snap["usage"], snap["budget"], snap["forecast"], snap["cost"]
    rp = snap.get("report") or ti.report()
    cs = rp.get("cache_savings") or {}
    cx = rp.get("context_savings") or {}
    md = rp.get("models") or {}
    lines = [
        "TOKEN ECONOMY REPORT — MEASURED vs ESTIMATED vs FORECAST vs UNKNOWN.",
        f"MEASURED session={u['session_tokens']} daily={u['daily_tokens']} actual_sum={u['sum_actual']} llm_calls={u['llm_calls']}",
        f"ESTIMATED sum={u['sum_estimated']}  (tiktoken; não é consumo de provider)",
        f"COST {c['kind']}: {c.get('reason')}",
        f"BUDGET daily used={b['daily']['used_measured']}/{b['daily']['limit']} hard={b['daily']['hard']}",
        f"CACHE hits={cs.get('hits_measured')} estimated_savings={cs.get('estimated_savings')} actual_savings={cs.get('actual_savings')} ({cs.get('actual_kind')})",
        f"CONTEXT saved_est={cx.get('tokens_saved_estimated')} actual={cx.get('actual_savings')} ({cx.get('actual_kind')})",
        f"MODELS {md.get('kind')}: {md.get('reason') or md.get('models')}",
        f"FORECAST {f['kind']} status={f.get('status')} {f.get('reason') or ''}",
        f"useful_work/token {snap['efficiency'].get('useful_work_per_token')} ({snap['efficiency'].get('kind')})",
        f"Langfuse {snap['externals']['langfuse']['available']} LiteLLM {snap['externals']['litellm']['available']}",
    ]
    _say("brain", "\n".join(lines))
    _broadcast()
    return {"ok": True, "via": "tokens"}


def _handle_web_refusal(_say, _broadcast) -> dict:
    _say("brain",
         "SearXNG ausente. Pesquisa web NÃO foi feita. Não invento resultados da internet. "
         "Reformula com o que está neste repo, ou um cálculo/git/ficheiro.")
    _broadcast()
    return {"ok": True, "via": "no_web", "blocked": True}


def _handle_web_search(query, _say, _broadcast) -> dict:
    """Search the web using available backends."""
    from .websearch import search
    r = search(query, max_results=5)
    if r.get("status") == "success":
        lines = [f"PESQUISA WEB ({r['backend']}) — {r['n']} resultados:"]
        for i, res in enumerate(r["results"], 1):
            lines.append(f"{i}. {res['title']}")
            lines.append(f"   {res['url']}")
            if res.get("snippet"):
                lines.append(f"   {res['snippet'][:200]}")
        _say("brain", "\n".join(lines))
        _broadcast()
        return {"ok": True, "via": "web_search", "results": r}
    else:
        _say("brain",
             f"Pesquisa web falhou: {r.get('error', 'unknown')}. "
             "Nenhum search engine disponível.")
        _broadcast()
        return {"ok": True, "via": "no_web", "blocked": True}


def _handle_roadmap(_say, _broadcast, resolve_mode) -> dict:
    os_s = aios.snapshot()
    llm = providers.any_llm()
    lines = [
        "Sou a GOD. Falo no feminino. Não sou um tab de documentação.",
        f"Modo {resolve_mode()[0]}. GPU required=false. OS booted={os_s.get('booted')} syscalls={os_s.get('syscalls')}.",
        "P0 FEITO: Fast Path, latency MEASURED, Direct LLM, smart memory.",
        "P1 FEITO: decide() + missão SQLite + graph inflight=2 + router fiabilidade + HARDCORE MODE.",
        "P2 FEITO: Validator + Third Eye 2.0. Factory NÃO. P3 mesh NÃO. P4 UI FEITO.",
        "P1.5 FEITO: System State + Capabilities + Health + Trace + Flags + Runtime Protection + GOD Object refactor.",
        f"LLM vivo: {'sim' if llm else 'não'} — up={[h['id'] for h in providers.health_all() if h.get('available')]} · Ollama={'up' if any(h['id']=='ollama' and h.get('available') for h in providers.health_all()) else 'down'}. GitHub main. Plane godsx MEASURED, não no produto.",
        "Não adiciono camadas nem resultados fictícios. Sem provider, recuso.",
    ]
    _say("brain", "\n".join(lines))
    _broadcast()
    return {"ok": True, "via": "roadmap"}


def _handle_os_commands(low, _say, _broadcast) -> dict:
    snap = aios.snapshot()
    lines = [
        f"{snap['sysname']} {snap['version']}  uptime={snap['uptime_s']}s  {snap['kind']}",
        f"pressure={snap['pressure']} ram_avail={snap['ram_avail_mb']}MB  gpu_required=false  preempt=false",
        f"ready={snap['ready']} running={snap['running']} killed={snap['killed']} syscalls={snap['syscalls']}",
        f"quota agent {snap['quota']['used_measured']}/{snap['quota']['limit']} {snap['quota']['kind']}",
    ]
    if low.strip() == "dmesg":
        evs = aios.dmesg(16)
        if not evs:
            lines.append("dmesg vazio (ainda sem SYSCALL/OS_* neste processo)")
        for e in evs:
            lines.append(f"  {e.get('name')}  {e.get('msg')}")
    else:
        for pproc in (aios.ps(16).get("processes") or []):
            lines.append(
                f"  {(pproc.get('status') or ''):8} {pproc.get('pid')} {pproc.get('type')} {pproc.get('kind') or ''} prio={pproc.get('priority')}"
            )
    _say("brain", "\n".join(lines))
    _broadcast()
    return {"ok": True, "via": "os"}


def _handle_kill(target, _say, _broadcast) -> dict:
    r = aios.kill(target)
    _say("brain", f"OS kill {target}: ok={r.get('ok')} {r.get('status') or r.get('reason')}")
    _broadcast()
    return {"ok": True, "via": "os"}


def _handle_repair(_say, _broadcast) -> dict:
    from . import repair
    r = repair.run()
    lines = [f"REPAIR {r['kind']} ok={r['ok']}", r.get("note") or ""]
    for a in r.get("actions") or []:
        lines.append(f"  {a.get('check')} ok={a.get('ok')} {a.get('error') or a.get('fix') or ''}")
    _say("brain", "\n".join(lines))
    _broadcast()
    return {"ok": True, "via": "repair", "repair": r}


def _handle_mission_create(text, _say, _broadcast) -> dict:
    mm = re.match(r"^\s*(missão|nova missão|objectivo)\s*[:\-]\s*(.+)$", text, re.I | re.S)
    if not mm:
        return None
    r = mission.create(mm.group(2).strip())
    if not r.get("ok"):
        _say("brain", f"Missão recusada: {r.get('error')}")
        return {"ok": False, "via": "mission"}
    _say("brain",
         "MISSÃO ACTIVE (SQLite, MEASURED).\n"
         f"id={r['id']}\n{r['goal']}\n"
         "Tarefas seguintes ficam ligadas a esta missão. Uma active de cada vez.")
    _broadcast()
    return {"ok": True, "via": "mission", "mission": r}


def _handle_mission_commands(low, _say, _broadcast) -> dict | None:
    if re.match(r"^\s*(missão actual|objectivo actual|qual (é )?a missão|missão)\s*$", low):
        a = mission.active()
        if not a:
            _say("brain", "Nenhuma missão active. Escreve: missão: <objectivo>")
        else:
            _say("brain", f"MISSÃO ACTIVE {a['id']}\n{a['goal']}\nstatus={a['status']} ts={a['ts']}")
        _broadcast()
        return {"ok": True, "via": "mission", "mission": a}
    if re.match(r"^\s*(conclui missão|missão feita|fecha missão)\s*$", low):
        a = mission.active()
        if not a:
            _say("brain", "Nenhuma missão active para concluir.")
            return {"ok": True, "via": "mission"}
        mission.set_status(a["id"], "done")
        _say("brain", f"Missão {a['id']} → done.\n{a['goal']}")
        _broadcast()
        return {"ok": True, "via": "mission"}
    if re.match(r"^\s*pausa missão\s*$", low):
        a = mission.active()
        if not a:
            _say("brain", "Nenhuma missão active para pausar.")
            return {"ok": True, "via": "mission"}
        mission.set_status(a["id"], "paused")
        _say("brain", f"Missão {a['id']} → paused.")
        _broadcast()
        return {"ok": True, "via": "mission"}
    if re.match(r"^\s*cancela missão\s*$", low):
        a = mission.active()
        if not a:
            _say("brain", "Nenhuma missão active para cancelar.")
            return {"ok": True, "via": "mission"}
        mission.set_status(a["id"], "cancelled")
        _say("brain", f"Missão {a['id']} → cancelled.")
        _broadcast()
        return {"ok": True, "via": "mission"}
    return None


def _handle_observer(low, _say, _broadcast, _last_pipeline) -> dict:
    from .thirdeye import format_criticism
    eye = observer.tick()
    m = eye["metrics"]
    lines = [
        "TERCEIRO OLHO — só factos medidos.",
        f"ok={eye['ok']}  pressure={m.get('pressure')}  load1={m.get('cpu_load1')}  ram_avail={m.get('ram_avail_mb')}MB",
        f"fila={m.get('queue_depth')}  workers_alive={m.get('workers_alive')} dead={m.get('workers_dead')}",
        f"cache_hit={m.get('cache_hit_rate')}  tools={m.get('tool_calls')}  llm={m.get('llm_calls')}",
        f"avg_overall={m.get('avg_overall')} n={m.get('rating_n')}  useful_work/token={m.get('useful_work_per_token')}",
        f"blocked_no_provider={m.get('blocked_no_provider')}  GPU required=false present={m.get('gpu_present')}",
    ]
    if eye["alerts"]:
        lines.append("ALERTAS:")
        for a in eye["alerts"]:
            lines.append(f"  [{a['level']}] {a['code']}: {a['msg']}")
    else:
        lines.append("Sem alertas.")
    p = _last_pipeline
    if p and p.get("critique"):
        lines.append("")
        lines.append("ÚLTIMA CRÍTICA (Third Eye 2.0):")
        lines.append(format_criticism(p["critique"]))
    _say("brain", "\n".join(lines))
    _broadcast()
    return {"ok": True, "via": "observer"}


def _handle_benchmark(text, from_worker, _say, _broadcast, _fmt_bench, _enqueue) -> dict | None:
    if not from_worker:
        q = _enqueue("benchmark", text)
        if not q.get("skip"):
            return q
    s = benchmark.run("chat" if not from_worker else "worker")
    _say("brain", _fmt_bench(s))
    _broadcast()
    return {"ok": True, "via": "benchmark"}


def _handle_evolution(text, from_worker, _say, _broadcast, _enqueue) -> dict | None:
    if not from_worker:
        q = _enqueue("evolution", text)
        if not q.get("skip"):
            return q
    cyc = evolution.run_cycle()
    exp = cyc["experiment"]
    _say("brain",
         "EVOLUTION CYCLE\n"
         f"gaps: {cyc['observe'].get('gaps')}\n"
         f"hash paráfrases {cyc['observe']['hash_paraphrase_hits']}/{cyc['observe']['pairs']} · "
         f"semantic {cyc['observe']['semantic_paraphrase_hits']}/{cyc['observe']['pairs']}\n"
         f"benchmark {cyc['benchmark']['run_id']} passed={cyc['benchmark']['passed']} skipped={cyc['benchmark']['skipped']} n_llm={cyc['benchmark']['n_llm_samples']}\n"
         f"experiência {exp['id']} [{exp['status']}] {exp['title']}\n"
         f"{exp['hypothesis']}\n"
         "Nada entrou em produção sem ADOPT.")
    _broadcast()
    return {"ok": True, "via": "evolution"}


def _handle_approve_reject(low, _say, _broadcast) -> dict:
    approve = bool(re.search(r"\baprova\b", low))
    pend = evolution.pending()
    if not pend:
        _say("brain", "Não há experiências pendentes.")
        return {"ok": True, "via": "evolution"}
    _say("brain", evolution.decide(pend[0]["id"], approve))
    _broadcast()
    return {"ok": True, "via": "evolution"}


def try_shortcuts(text: str, low: str, from_worker: bool, *,
                  _say, _broadcast, _last_pipeline, _fmt_bench,
                  _enqueue, resolve_mode) -> tuple[bool, dict | None]:
    """Tenta todos os shortcuts. Retorna (handled, result)."""

    # Token economy report
    if re.search(r"economia de tokens|token intelligence|relat[oó]rio de tokens", low):
        return True, _handle_token_report(_say, _broadcast)

    # Web search — try actual search first, fallback to refusal
    if re.search(r"pesquisa na (web|internet)|search the web|\bsearxng\b|\bgoogle\b.*\b(pesquisa|search)", low):
        qm = re.search(r"(?:pesquisa na (?:web|internet)|search the web)[:\s]+(.+)", text, re.I)
        query = qm.group(1).strip() if qm else text
        return True, _handle_web_search(query, _say, _broadcast)

    # Roadmap
    if re.search(r"^\s*(roadmap|fluxo)\s*$", low) or re.search(r"\broadmap\b", low):
        return True, _handle_roadmap(_say, _broadcast, resolve_mode)

    # OS commands
    if re.search(r"^\s*(ps|dmesg|uname)\s*$", low) or low.strip() in ("kernel", "os", "superai os", "estado do kernel"):
        return True, _handle_os_commands(low, _say, _broadcast)

    # Kill
    km = re.match(r"^\s*kill\s+(\S+)\s*$", low)
    if km:
        return True, _handle_kill(km.group(1), _say, _broadcast)

    # Repair
    if re.search(r"^\s*(repara|repair|conserta)\s*$", low):
        return True, _handle_repair(_say, _broadcast)

    # Mission create
    mm = re.match(r"^\s*(missão|nova missão|objectivo)\s*[:\-]\s*(.+)$", text, re.I | re.S)
    if mm:
        r = _handle_mission_create(text, _say, _broadcast)
        if r is not None:
            return True, r

    # Mission commands
    mr = _handle_mission_commands(low, _say, _broadcast)
    if mr is not None:
        return True, mr

    # Observer / Third Eye
    if re.search(r"terceiro olho|olho do sistema|\bobserva sistema\b", low):
        return True, _handle_observer(low, _say, _broadcast, _last_pipeline)

    # Benchmark
    if re.search(r"\b(corre|run|executa)\b.*\bbenchmark|\bbenchmark\b", low):
        r = _handle_benchmark(text, from_worker, _say, _broadcast, _fmt_bench, _enqueue)
        if r is not None:
            return True, r

    # Evolution cycle
    if re.search(r"\b(observa|ciclo de evolu|evolution cycle|evolu[cç][aã]o)\b", low):
        r = _handle_evolution(text, from_worker, _say, _broadcast, _enqueue)
        if r is not None:
            return True, r

    # Approve/reject experiments
    if re.search(r"\baprova\b", low) or re.search(r"\brejeita\b", low):
        return True, _handle_approve_reject(low, _say, _broadcast)

    # Not a shortcut
    return False, None
