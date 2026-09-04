import unittest
from pathlib import Path

from superai.brain import analyze
from superai.governor import gov
from superai.providers import health_all
from superai.tools import execute
from superai.util import count_tokens, normalize_query as nq


class Tokens(unittest.TestCase):
    def test_tiktoken(self):
        t = count_tokens("hello")
        self.assertTrue(t["verified"])
        self.assertEqual(t["method"], "tiktoken cl100k_base")
        self.assertGreaterEqual(t["tokens"], 1)


class Analyzer(unittest.TestCase):
    def test_math(self):
        t = analyze("calcula 2+2*3")
        self.assertEqual(t["type"], "math")
        self.assertEqual(t["exec_mode"], "FAST")
        self.assertIn("calculator", t["tool_requirement"])

    def test_coding_is_deep(self):
        t = analyze("implementa um refactor da arquitectura deste sistema crítico")
        self.assertEqual(t["exec_mode"], "DEEP")

    def test_git(self):
        t = analyze("git status")
        self.assertEqual(t["type"], "git")


class Tools(unittest.TestCase):
    def test_calc(self):
        r = execute("calculator", {"expr": "2+2*3"})
        self.assertEqual(r["status"], "success")
        self.assertEqual(r["findings"][0]["result"], 8)

    def test_json(self):
        r = execute("json", {"text": '{"a":1}'})
        self.assertEqual(r["status"], "success")
        self.assertEqual(r["findings"][0]["keys"], ["a"])

    def test_fs_denied(self):
        r = execute("fs.read", {"path": "/etc/passwd"})
        self.assertEqual(r["status"], "error")


class Governor(unittest.TestCase):
    def test_root(self):
        ok, _ = gov.allow_path(Path("/tmp/x"))
        self.assertFalse(ok)

    def test_python_ban(self):
        ok, _ = gov.allow_python("import socket\nsocket.socket()")
        self.assertFalse(ok)


class Providers(unittest.TestCase):
    def test_no_fake_scores(self):
        hs = health_all()
        ollama = next(h for h in hs if h["id"] == "ollama")
        claude = next(h for h in hs if h["id"] == "claude")
        self.assertFalse(ollama["available"])
        self.assertIsNone(claude["historical_score"])
        self.assertEqual(claude.get("samples"), 0)
        if claude.get("has_key"):
            self.assertIn(claude["available"], (True, False))
        else:
            self.assertFalse(claude["available"])

    def test_pick_skips_guard(self):
        from superai.providers import pick_chat_model

        self.assertIsNone(pick_chat_model(["whisper-large-v3", "llama-prompt-guard-2-86m"]))
        self.assertEqual(
            pick_chat_model(["whisper-large-v3", "llama-3.1-8b-instruct", "gpt-oss-safeguard-20b"]),
            "llama-3.1-8b-instruct",
        )
        self.assertEqual(
            pick_chat_model(["openai/gpt-oss-120b", "qwen/qwen3.8-27b", "google/gemini-3.8-flash:batch"]),
            "qwen/qwen3.8-27b",
        )

    def test_openai_message_ignores_reasoning(self):
        from superai.providers import openai_message_text

        self.assertEqual(openai_message_text({"choices": [{"message": {"content": "OI"}}]}), "OI")
        self.assertEqual(
            openai_message_text({"choices": [{"message": {"content": "", "reasoning": "think"}}]}),
            "",
        )

    def test_llm_prompt_is_constitution_not_essay(self):
        from superai.runtime import _llm_prompt

        p = _llm_prompt("oi", [])
        self.assertIn("GOD", p)
        self.assertIn("SearXNG", p)
        self.assertIn("USER: oi", p)
        self.assertNotIn("Diálogo:", p)
        self.assertLess(len(p), 1200)

    def test_dialogue_is_short_context(self):
        from superai.runtime import _dialogue, _llm_prompt

        p = _llm_prompt("e o CSS?", [], ["TU: cria um site", "GOD: gravei index.html"])
        self.assertIn("Diálogo:", p)
        self.assertIn("cria um site", p)
        self.assertIn("USER: e o CSS?", p)
        self.assertLess(len(p), 2000)
        lines = _dialogue(4, current="agora")
        self.assertTrue(all(not x.startswith("GOD: Um momento") for x in lines))

    def test_quem_es_goes_to_llm_path(self):
        from superai.providers import any_llm
        from superai.runtime import handle

        r = handle("quem és")
        if any_llm():
            self.assertIn(r.get("via"), ("queue", "llm", "llm_fail", "os_admit", "cache"))
            self.assertNotEqual(r.get("via"), "roadmap")
        else:
            self.assertIn(r.get("via"), ("blocked", "llm_fail", "no_provider"))

    def test_roadmap_stays_shortcut(self):
        from superai.runtime import handle

        r = handle("roadmap")
        self.assertEqual(r.get("via"), "roadmap")

    def test_web_search_refused(self):
        from superai.runtime import handle

        r = handle("pesquisa na web alternativas ao n8n")
        self.assertEqual(r.get("via"), "no_web")

    def test_format_leads_with_speech(self):
        from superai.runtime import _format_result

        out = _format_result(
            {"task_id": "T-x", "type": "general", "complexity": 2, "reasoning_budget": "low", "estimated_tokens": 10, "via": "llm"},
            {"firewall": {"action": "approve"}, "cache": "miss", "route": ["DIRECT"]},
            [{"tool": "llm:groq", "status": "success", "findings": [{"text": "Olá."}], "evidence": ["adapter=groq model=qwen"]}],
            {"tokens_actual": 19, "QUALITY": 1, "CORRECTNESS": 1, "TOKEN_EFFICIENCY": 1, "OVERALL": 1, "llm_used": True},
            None,
        )
        self.assertTrue(out.startswith("Olá."))
        self.assertNotIn("Tarefa T-x", out)


class CacheNorm(unittest.TestCase):
    def test_same_intent(self):
        a = nq("Faz uma análise da arquitectura deste projecto.")
        b = nq("Analisa a arquitectura deste projecto.")
        self.assertEqual(a, b)


class Embed(unittest.TestCase):
    def test_paraphrase_closer_than_unrelated(self):
        from superai.embed import cosine, embed

        a = embed("Analisa a arquitectura deste projecto.")
        b = embed("Faz uma análise da arquitectura deste projecto.")
        c = embed("receita de bacalhau com natas")
        self.assertGreater(cosine(a, b), cosine(a, c))
        self.assertEqual(len(a), 384)


class Qdrant(unittest.TestCase):
    def test_health_embedded(self):
        from superai.memory_vec import vectors

        h = vectors.health()
        self.assertTrue(h["available"], h.get("error"))
        self.assertEqual(h["embed"]["dim"], 384)


class Routing(unittest.TestCase):
    def test_omniroute_probed_down(self):
        from superai.routing import health

        gw = health()
        self.assertEqual(gw["omniroute"]["available"], False)
        self.assertIn("20128", gw["omniroute"]["error"] or "")
        self.assertEqual(gw["active"], "direct")


class Resources(unittest.TestCase):
    def test_gpu_optional(self):
        from superai.resources import host

        h = host()
        self.assertFalse(h["gpu"]["required"])
        self.assertGreaterEqual(h["cpu_count"], 1)

    def test_light_stays_local(self):
        from superai.resources import decide

        d = decide({"type": "math", "complexity": 2}, [])
        self.assertFalse(d["enqueue"])
        self.assertEqual(d["location"], "LOCAL")

    def test_heavy_enqueues_when_worker_alive(self):
        from superai import queue as tq
        from superai.resources import decide

        tq.register_worker("t-heavy-test", "t-heavy-test", "control", ["chat"])
        d = decide({"type": "research", "complexity": 8, "job_kind": "chat"}, tq.list_workers())
        self.assertTrue(d["enqueue"])
        tq.unregister_worker("t-heavy-test")


class Queue(unittest.TestCase):
    def test_claim_complete(self):
        from superai import queue as tq

        tq.enqueue("chat", "hello-queue-test", None, "LOCAL_WORKER")
        got = tq.claim("t-claim-test")
        self.assertIsNotNone(got)
        tq.complete(got["id"], {"ok": True})
        st = tq.stats()
        self.assertGreaterEqual(st["completed"], 1)
        tq.unregister_worker("t-claim-test")

    def test_claim_respects_inflight_cap(self):
        from superai import queue as tq

        tq.register_worker("t-inflight", "t-inflight", "control", ["chat"])
        a = tq.enqueue("chat", "inflight-unique-aaa-1", None, "LOCAL_WORKER")
        b = tq.enqueue("chat", "inflight-unique-bbb-2", None, "LOCAL_WORKER")
        self.assertFalse(a.get("deduped"))
        self.assertFalse(b.get("deduped"))
        c1 = tq.claim("t-inflight")
        self.assertIsNotNone(c1)
        c2 = tq.claim("t-inflight")
        self.assertIsNone(c2)
        tq.cancel(c1["id"])
        tq.cancel(b["id"])
        tq.unregister_worker("t-inflight")


class CacheHitFormat(unittest.TestCase):
    def test_second_math_does_not_crash(self):
        from superai.runtime import handle

        a = handle("calcula 9+1")
        b = handle("calcula 9+1")
        self.assertIn(a.get("via"), ("tools", "cache"))
        self.assertIn(b.get("via"), ("tools", "cache"))


class Observer(unittest.TestCase):
    def test_inspect_real_metrics(self):
        from superai.observer import inspect

        e = inspect()
        self.assertIn("metrics", e)
        self.assertFalse(e["metrics"]["gpu_required"])
        self.assertIn("cache_hit_rate", e["metrics"])
        self.assertIn("useful_work_per_token", e["metrics"])

    def test_tick_edge(self):
        from superai.observer import tick

        a = tick()
        b = tick()
        self.assertEqual({x["code"] for x in a["alerts"]}, {x["code"] for x in b["alerts"]})


class StaleJob(unittest.TestCase):
    def test_assigned_without_start_requeues(self):
        from superai import queue as tq

        tq.register_worker("expire-w", "expire-w", "control", ["chat"])
        tq.heartbeat("expire-w")
        tq.enqueue("chat", "expire-stale-unique-xyz", None, "LOCAL_WORKER")
        got = tq.claim("expire-w")
        self.assertIsNotNone(got)
        n = tq.expire_stale(assigned_s=-1)
        self.assertGreaterEqual(n, 1)
        found = next(x for x in tq.jobs(80) if x["id"] == got["id"])
        self.assertEqual(found["status"], "queued")
        self.assertIsNone(found["worker_id"])
        tq.unregister_worker("expire-w")


class NoFakeCompute(unittest.TestCase):
    def test_research_path_depends_on_llm(self):
        from superai.providers import any_llm
        from superai.runtime import handle

        r = handle("explica o conceito QW-LLM-7a1 em duas frases")
        if any_llm():
            self.assertIn(r.get("via"), ("queue", "llm", "llm_fail", "os_admit", "cache"))
        else:
            self.assertEqual(r.get("via"), "blocked")


class TokenIntel(unittest.TestCase):
    def test_estimate_is_estimated_not_measured(self):
        from superai.tokens import ESTIMATED, estimate

        e = estimate("hello")
        self.assertEqual(e["kind"], ESTIMATED)
        self.assertGreaterEqual(e["input_tokens"], 1)
        self.assertEqual(e["cost_kind"], "UNKNOWN")

    def test_pricing_unknown(self):
        from superai.tokens import UNKNOWN, pricing

        p = pricing("claude", "claude-opus")
        self.assertEqual(p["kind"], UNKNOWN)
        self.assertIsNone(p.get("cost"))

    def test_cost_split_does_not_mix_subscription_and_api(self):
        from superai.tokens import UNKNOWN, cost_split

        s = cost_split()
        self.assertEqual(s["subscription"]["kind"], "USER_STATED")
        self.assertEqual(s["subscription"]["amount_eur"], 22)
        self.assertEqual(s["subscription"]["official_usd_monthly"], 20)
        self.assertIn("claude.com/pricing", s["subscription"]["source"] or "")
        self.assertTrue(s["subscription"]["not_api"])
        self.assertTrue(s["subscription"]["includes_vat"])
        self.assertFalse(s["subscription"]["official_vat_included"])
        self.assertEqual(s["api"]["kind"], UNKNOWN)
        self.assertIsNone(s["api"]["cost"])
        self.assertIsNone(s["sum_eur"])
        self.assertEqual(s["sum_kind"], UNKNOWN)

    def test_pc_node_declared_not_this_host(self):
        from superai.resources import declared_node, host

        n = declared_node()
        h = host()
        self.assertEqual(n["kind"], "USER_DECLARED")
        self.assertEqual(n["ram_gb"], 24)
        self.assertEqual(n["disk_gb"], 2048)
        self.assertEqual(n["cores"], 4)
        self.assertFalse(n["gpu_required"])
        self.assertEqual(n["caps"]["ram_gb_max"], 12.0)
        self.assertEqual(n["caps"]["cores_max"], 2)
        self.assertFalse(n["caps"]["gpu_for_llm"])
        self.assertTrue(n["this_process_is_not_that_pc"])
        self.assertFalse(n["local_llm"])
        self.assertNotEqual(h.get("ram_mb"), 24 * 1024)
        self.assertIsNotNone(h.get("disk_free_mb"))
        self.assertEqual(h.get("disk_kind"), "MEASURED")

    def test_layout_not_applied_to_this_sandbox(self):
        from superai.resources import inflight_cap, layout

        L = layout()
        self.assertFalse(L["applied_here"])
        self.assertFalse(L["pc"]["gpu_for_llm"])
        self.assertFalse(L["local_llm"]["allowed"])
        self.assertEqual(L["pc"]["cores_god_max"], 2)
        self.assertEqual(L["pc"]["ram_gb_god_max"], 12.0)
        inf = inflight_cap()
        self.assertEqual(inf["applied"], 1)
        self.assertEqual(inf["applied_kind"], "MEASURED")
        self.assertEqual(inf["declared_pc_target"], 2)

    def test_record_zero_actual_on_cache(self):
        from superai.tokens import MEASURED, record

        ev = record(task_id="T-test-cache", estimated=200, actual=0, status="cache_hit", cache_hit=True, via="cache")
        self.assertEqual(ev["actual_tokens"], 0)
        self.assertEqual(ev["token_kind"], MEASURED)
        self.assertEqual(ev["cost_kind"], "UNKNOWN")
        self.assertTrue(ev["cache_hit"])

    def test_estimation_error(self):
        # fórmula só — não persistir actual fictício na spine (não é consumo LLM)
        estimated, actual = 4000, 4620
        err = round((actual - estimated) / estimated * 100, 2)
        self.assertAlmostEqual(err, 15.5, places=1)

    def test_forecast_unknown_without_history(self):
        from superai.tokens import FORECAST, UNKNOWN, forecast

        f = forecast()
        self.assertEqual(f["kind"], FORECAST)
        self.assertIn(f.get("status"), (UNKNOWN, FORECAST))

    def test_gate_reuses_firewall(self):
        from superai.brain import analyze
        from superai.tokens import gate

        t = analyze("calcula 1+1")
        t["estimated_tokens"] = 10**9
        fw = gate(t)
        self.assertEqual(fw["action"], "reject")

    def test_langfuse_absent(self):
        from superai.tokens import adapters_status

        s = adapters_status()
        self.assertFalse(s["langfuse"]["available"])
        self.assertFalse(s["litellm"]["available"])

    def test_route_advice_blocks_without_llm(self):
        from superai.brain import analyze
        from superai.providers import any_llm
        from superai.tokens import route_advice

        d = route_advice(analyze("pesquisa X"))
        if any_llm():
            self.assertNotEqual(d["recommendation"], "BLOCK")
            self.assertTrue(d["any_llm"])
        else:
            self.assertEqual(d["recommendation"], "BLOCK")
            self.assertFalse(d["any_llm"])

    def test_models_unknown_without_llm_samples(self):
        from superai.tokens import UNKNOWN, models

        m = models()
        self.assertIn(m["kind"], (UNKNOWN, "MEASURED"))

    def test_report_kinds(self):
        from superai.tokens import ESTIMATED, MEASURED, UNKNOWN, report

        r = report()
        self.assertEqual(r["cost"]["kind"], UNKNOWN)
        self.assertEqual(r["llm_calls"]["kind"], MEASURED)
        self.assertEqual(r["cache_savings"]["actual_kind"], UNKNOWN)
        self.assertEqual(r["context_savings"]["kind"], ESTIMATED)

    def test_context_efficiency_estimated(self):
        from superai.tokens import ESTIMATED, context_efficiency

        e = context_efficiency("aaaa " * 40, "aaaa")
        self.assertEqual(e["kind"], ESTIMATED)
        self.assertGreater(e["tokens_saved"], 0)

    def test_gateway_fallback_flag(self):
        from superai.routing import complete

        r = complete("ping", max_tokens=8)
        self.assertIn(r.get("status"), ("unavailable", "error", "success"))
        if r.get("gateway") == "direct":
            self.assertTrue(r.get("fallback"))


class EvolutionToken(unittest.TestCase):
    def test_observe_sees_zero_llm(self):
        from superai.evolution import observe
        from superai.store import store

        obs = observe()
        self.assertEqual(obs["token"]["llm_calls"], store.usage().get("llm_calls", 0))
        self.assertEqual(obs["token"]["kind"], "MEASURED")


class Dedup(unittest.TestCase):
    def test_same_job_not_duplicated(self):
        from superai import queue as tq

        a = tq.enqueue("benchmark", "corre benchmark agora", None, "LOCAL_WORKER")
        b = tq.enqueue("benchmark", "corre benchmark agora", None, "LOCAL_WORKER")
        self.assertEqual(a["id"], b["id"])
        self.assertTrue(b.get("deduped"))


class Bench(unittest.TestCase):
    def test_tools_pass_llm_skipped(self):
        from superai.benchmark import run

        s = run("test")
        math = next(r for r in s["rows"] if r["case_id"] == "tool_math")
        llm = next(r for r in s["rows"] if r["case_id"] == "llm_pong")
        self.assertTrue(math["passed"])
        if llm["skipped"]:
            self.assertEqual(s["n_llm_samples"], 0)
        else:
            self.assertGreaterEqual(s["n_llm_samples"], 1)


class OSKernel(unittest.TestCase):
    def test_syscall_calc(self):
        from superai import aios

        r = aios.syscall("calculator", {"expr": "2+2*3"}, actor="test")
        self.assertEqual(r["status"], "success")
        self.assertEqual(r["findings"][0]["result"], 8)
        self.assertEqual(r["kind"], "MEASURED")

    def test_syscall_unknown(self):
        from superai import aios

        r = aios.syscall("no.such.sys", {}, actor="test")
        self.assertEqual(r["status"], "error")

    def test_syscall_governor_blocks_passwd(self):
        from superai import aios

        r = aios.syscall("fs.read", {"path": "/etc/passwd"}, actor="test")
        self.assertEqual(r["status"], "error")

    def test_kill_queued(self):
        from superai import aios
        from superai import queue as tq

        job = tq.enqueue("chat", "os-kill-unique-7c1e", None, "LOCAL_WORKER", priority=9)
        self.assertFalse(job.get("deduped"))
        r = aios.kill(job["id"])
        self.assertTrue(r["ok"])
        self.assertEqual(tq.get_job(job["id"])["status"], "killed")

    def test_priority_claim(self):
        from superai import queue as tq

        low = tq.enqueue("chat", "os-prio-low-aa11", None, "LOCAL_WORKER", priority=0)
        high = tq.enqueue("chat", "os-prio-high-bb22", None, "LOCAL_WORKER", priority=10)
        got = tq.claim("os-prio-w")
        self.assertIsNotNone(got)
        self.assertEqual(got["id"], high["id"])
        tq.cancel(got["id"])
        if not low.get("deduped"):
            tq.cancel(low["id"])
        tq.unregister_worker("os-prio-w")

    def test_ps_measured(self):
        from superai import aios

        table = aios.ps(8)
        self.assertEqual(table["kind"], "MEASURED")
        self.assertFalse(table["preempt"])
        self.assertIn("processes", table)

    def test_drivers_not_invented(self):
        from superai import aios

        ds = aios.drivers()
        omni = next(d for d in ds if d["id"] == "omniroute")
        self.assertFalse(omni["available"])
        self.assertEqual(omni["kind"], "MEASURED")

    def test_gpu_optional(self):
        from superai import aios

        u = aios.uname()
        self.assertFalse(u["gpu_required"])
        self.assertEqual(u["kind"], "MEASURED")

    def test_admit_ok_when_pressure_low(self):
        from superai import aios
        from superai.resources import host

        h = host()
        if h.get("pressure") == "high":
            self.skipTest("host under pressure — cannot assert admit ok")
        a = aios.admit("benchmark", "os-admit-test")
        self.assertTrue(a["ok"])

    def test_chat_ps(self):
        from superai.runtime import handle

        r = handle("ps")
        self.assertEqual(r.get("via"), "os")


class SiteBuilder(unittest.TestCase):
    def test_coding_type_for_site(self):
        self.assertEqual(analyze("cria um site simples de café")["type"], "coding")

    def test_write_ok(self):
        r = execute("fs.write", {"slug": "utest-site", "path": "index.html", "text": "<h1>utest</h1>"})
        self.assertEqual(r["status"], "success", r.get("errors"))
        from superai.config import DATA
        self.assertEqual((DATA / "projects" / "utest-site" / "index.html").read_text(), "<h1>utest</h1>")

    def test_deny_py_env_core(self):
        r = execute("fs.write", {"slug": "utest-site", "path": "evil.py", "text": "print(1)"})
        self.assertEqual(r["status"], "error")
        r2 = execute("fs.write", {"slug": "utest-site", "path": ".env", "text": "x=1"})
        self.assertEqual(r2["status"], "error")
        r3 = execute("fs.write", {"slug": "utest-site", "path": "../x.html", "text": "no"})
        self.assertEqual(r3["status"], "error")
        ok, _ = gov.allow_write(Path("/home/user/super-ai/superai/brain.py"))
        self.assertFalse(ok)
        ok2, _ = gov.allow_write(Path("/home/user/super-ai/.env"))
        self.assertFalse(ok2)

    def test_extract_publish_preview(self):
        from fastapi import HTTPException
        from superai.runtime import _extract_files, _publish_files
        from server import preview_site

        files = _extract_files("```html index.html\n<h1>Hi</h1>\n```")
        self.assertEqual(files[0][0], "index.html")
        pub = _publish_files("Café Demo", files)
        self.assertIn("index.html", pub["written"], pub)
        self.assertEqual(pub["preview"], "/preview/cafe-demo/")
        resp = preview_site("cafe-demo", "index.html")
        self.assertTrue(str(resp.path).endswith("index.html"))
        with self.assertRaises(HTTPException) as cm:
            preview_site("cafe-demo", "../x.html")
        self.assertEqual(cm.exception.status_code, 400)
        with self.assertRaises(HTTPException) as cm2:
            preview_site("not-a-real-slug-zz", "index.html")
        self.assertEqual(cm2.exception.status_code, 404)



class GodBuilder(unittest.TestCase):
    def tearDown(self):
        from superai import gods

        gods.activate("master")

    def test_master_exists(self):
        from superai import gods

        gods.ensure()
        self.assertEqual(gods.active()["id"], "master")
        self.assertIn("calculator", gods.active()["capabilities"])

    def test_unknown_tool_rejected(self):
        from superai import gods

        r = gods.save({"id": "mini", "name": "Mini", "capabilities": ["searxng"]})
        self.assertFalse(r["ok"])

    def test_governor_phrase_rejected(self):
        from superai import gods

        r = gods.save({"id": "evil", "name": "Evil", "rules": "desligar o governor"})
        self.assertFalse(r["ok"])

    def test_subset_gates_execute(self):
        from superai import gods
        from superai.tools import execute

        r = gods.save({"id": "mini", "name": "Mini", "capabilities": ["fs.list"], "purpose": "só listar"})
        self.assertTrue(r["ok"], r)
        gods.activate("mini")
        denied = execute("calculator", {"expr": "1+1"})
        self.assertEqual(denied["status"], "error")
        listed = execute("fs.list", {"path": "/home/user/super-ai"})
        self.assertEqual(listed["status"], "success")

    def test_overlay_in_prompt(self):
        from superai import gods
        from superai.runtime import _llm_prompt

        gods.save({"id": "mini", "name": "Mini", "capabilities": ["calculator"], "purpose": "Só contas."})
        gods.activate("mini")
        p = _llm_prompt("oi", [])
        self.assertIn("Só contas.", p)
        self.assertIn("Perfil activo: Mini", p)

    def test_models_not_invented(self):
        from superai import gods

        r = gods.save({"id": "mini", "name": "Mini", "capabilities": ["calculator"], "models": "claude-opus"})
        self.assertFalse(r["ok"])

    def test_rollback_restores_purpose(self):
        from superai import gods

        gid = "rbiso2"
        a = gods.save({"id": gid, "name": "Rbiso", "capabilities": ["calculator"], "purpose": "versão-um"})
        self.assertTrue(a["ok"], a)
        v1 = int((a.get("god") or {}).get("version") or 1)
        b = gods.save({"id": gid, "name": "Rbiso", "capabilities": ["calculator"], "purpose": "versão-dois"})
        self.assertTrue(b["ok"], b)
        r = gods.rollback(gid, v1)
        self.assertTrue(r["ok"], r)
        self.assertEqual(gods.get(gid)["purpose"], "versão-um")


class RepairMemBudget(unittest.TestCase):
    def tearDown(self):
        from superai import gods

        gods.activate("master")

    def test_repair_measured(self):
        from superai import repair

        r = repair.run()
        self.assertEqual(r["kind"], "MEASURED")
        self.assertTrue(any(a["check"] == "gods_master" and a["ok"] for a in r["actions"]))
        self.assertTrue(any(a["check"] == "sqlite" and a["ok"] for a in r["actions"]))

    def test_chat_repara(self):
        from superai.runtime import handle

        r = handle("repara")
        self.assertEqual(r.get("via"), "repair")

    def test_mem_kinds_isolated(self):
        from superai.store import store

        store.mem_put("episode:mini", "iso-k", "segredo-mini-xyz")
        store.mem_put("episode:master", "iso-k", "segredo-master-abc")
        mini = store.mem_search("segredo", kinds=["episode:mini"])
        self.assertTrue(any("mini-xyz" in str(h.get("value")) for h in mini))
        self.assertFalse(any("master-abc" in str(h.get("value")) for h in mini))

    def test_budget_has_70_90_100(self):
        from superai.tokens import budget_status

        d = budget_status()["daily"]
        self.assertIn("warn70", d)
        self.assertIn("warn90", d)
        self.assertIn("hard", d)
        self.assertEqual(d["soft"], d["warn90"])

    def test_cache_namespaced_by_god(self):
        from superai.brain import cache_lookup, cache_store

        cache_store("hello-ns-iso", {"summary": "mini-only"}, 1, ns="mini")
        self.assertIsNone(cache_lookup("hello-ns-iso", ns="master"))
        self.assertIsNotNone(cache_lookup("hello-ns-iso", ns="mini"))

    def test_vector_god_filter(self):
        from superai.memory_vec import vectors

        if not vectors.available():
            self.skipTest(vectors.error or "qdrant down")
        vectors.upsert("memory", "iso-mini-pt", "banana-mini-xyz", {"god_id": "mini"})
        vectors.upsert("memory", "iso-master-pt", "banana-master-abc", {"god_id": "master"})
        mini = vectors.search("memory", "banana", k=8, min_score=0.01, god_id="mini")
        texts = " ".join(str(x.get("text") or "") for x in mini)
        self.assertIn("mini-xyz", texts)
        self.assertNotIn("master-abc", texts)


class God20Sprint1(unittest.TestCase):
    def test_fast_math_skips_vector_and_records_latency(self):
        from superai.runtime import handle, snapshot

        r = handle("calcula 41*3")
        self.assertIn(r.get("via"), ("tools", "cache"))
        p = snapshot().get("last_pipeline") or {}
        if r.get("via") == "tools":
            self.assertTrue(p.get("fast"))
            self.assertEqual((p.get("task") or {}).get("exec_mode"), "FAST")
            self.assertIn("vector", p.get("skipped_heavy") or [])
            self.assertNotIn("vector_cache", p)
            self.assertEqual(p.get("latency_kind"), "MEASURED")
            self.assertIsInstance(p.get("latency_ms"), (int, float))

    def test_plane_probe_no_fake_board(self):
        from superai.plane import probe

        p = probe()
        self.assertEqual(p["kind"], "MEASURED")
        self.assertFalse(p["in_product"])
        if not p.get("has_key"):
            self.assertIsNone(p.get("issues"))
            return
        self.assertEqual(p.get("workspace_slug"), "godsx")
        if p.get("workspace_found"):
            self.assertTrue(p.get("project_found"))
            iss = p.get("issues") or {}
            self.assertEqual(iss.get("kind"), "MEASURED")
            self.assertIsInstance(iss.get("n"), int)
            self.assertGreaterEqual(iss["n"], 1)
            names = [x.get("name") for x in (iss.get("items") or [])]
            self.assertTrue(any(names))
        else:
            self.assertIsNone(p.get("issues"))


if __name__ == "__main__":
    unittest.main()
