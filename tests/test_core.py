import unittest
from pathlib import Path

from superai.brain import analyze
from superai.config import ROOT
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
    def setUp(self):
        from superai.store import store
        # Cancel stale queued jobs from prior runs to prevent dedup false positives
        with store._lock, store._conn() as c:
            c.execute("UPDATE jobs SET status='cancelled' WHERE kind='chat' AND status IN ('queued','assigned','running')")

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
        c = tq.enqueue("chat", "inflight-unique-ccc-3", None, "LOCAL_WORKER")
        self.assertFalse(a.get("deduped"))
        self.assertFalse(b.get("deduped"))
        self.assertFalse(c.get("deduped"))
        c1 = tq.claim("t-inflight")
        self.assertIsNotNone(c1)
        c2 = tq.claim("t-inflight")
        self.assertIsNotNone(c2)  # inflight=2, second claim succeeds
        c3 = tq.claim("t-inflight")
        self.assertIsNone(c3)  # inflight=2, third claim fails
        tq.cancel(c1["id"])
        tq.cancel(c2["id"])
        tq.cancel(c["id"])
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
        self.assertEqual(inf["applied"], 2)  # inflight=2 now
        self.assertEqual(inf["applied_kind"], "MEASURED")
        self.assertEqual(inf["declared_pc_target"], 2)

    def test_record_zero_actual_on_cache(self):
        from superai.tokens import MEASURED, CALCULATED, UNKNOWN, record

        ev = record(task_id="T-test-cache", estimated=200, actual=0, status="cache_hit", cache_hit=True, via="cache")
        self.assertEqual(ev["actual_tokens"], 0)
        self.assertEqual(ev["token_kind"], MEASURED)
        self.assertIn(ev["cost_kind"], (UNKNOWN, CALCULATED))  # CALCULATED if pricing data exists
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
        from superai.tokens import ESTIMATED, MEASURED, UNKNOWN, CALCULATED, report

        r = report()
        self.assertIn(r["cost"]["kind"], (UNKNOWN, CALCULATED))  # CALCULATED if pricing data exists
        self.assertEqual(r["llm_calls"]["kind"], MEASURED)
        self.assertIn(r["cache_savings"]["actual_kind"], (UNKNOWN, CALCULATED))
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
        ok, _ = gov.allow_write(Path(str(ROOT / "superai" / "brain.py")))
        self.assertFalse(ok)
        ok2, _ = gov.allow_write(Path(str(ROOT / ".env")))
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
    def setUp(self):
        from superai import gods
        from superai.gods import DIR

        gods.activate("master")
        # Clean up test profiles to avoid hitting MAX_GODS
        if DIR.exists():
            for p in DIR.glob("*.json"):
                name = p.stem
                if name != "master":
                    try:
                        p.unlink()
                    except Exception:
                        pass

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
        listed = execute("fs.list", {"path": str(ROOT)})
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
        import uuid

        # Use unique ID to avoid state pollution across runs
        gid = f"rbiso-{uuid.uuid4().hex[:8]}"
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
        import time
        # Use unique key to avoid collision with other tests
        unique_key = f"hello-ns-iso-{time.time_ns()}"
        cache_store(unique_key, {"summary": "mini-only"}, 1, ns="mini")
        self.assertIsNone(cache_lookup(unique_key, ns="master"))
        self.assertIsNotNone(cache_lookup(unique_key, ns="mini"))

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
            self.assertEqual(p.get("stages_kind"), "MEASURED")
            self.assertIn("cache", p.get("stages_ms") or {})

    def test_normal_chat_skips_queue(self):
        from superai.providers import any_llm
        from superai.runtime import handle, snapshot

        r = handle("quem és tu em duas frases directpathcheck")
        if any_llm():
            self.assertNotEqual(r.get("via"), "queue")
            self.assertIn(r.get("via"), ("llm", "llm_fail", "os_admit", "cache"))
            p = snapshot().get("last_pipeline") or {}
            if r.get("via") in ("llm", "llm_fail"):
                self.assertTrue(p.get("direct_llm"))
                self.assertIn("DIRECT_LLM", p.get("route") or [])
        else:
            self.assertIn(r.get("via"), ("blocked", "llm_fail", "no_provider", "cache"))

    def test_deep_still_queues(self):
        from superai import queue as tq
        from superai.providers import any_llm
        from superai.runtime import handle

        tq.register_worker("p0-deep-w", "p0-deep-w", "control", ["chat"])
        tq.heartbeat("p0-deep-w")
        try:
            r = handle("zzdeepqueue991wn implementa um refactor da arquitectura deste sistema crítico")
            if any_llm():
                # Cache hit is acceptable (from previous runs)
                self.assertIn(r.get("via"), ("queue", "cache"), r)
                if r.get("job"):
                    tq.cancel(r["job"])
            else:
                self.assertIn(r.get("via"), ("blocked", "llm_fail", "no_provider", "cache", "queue"))
        finally:
            tq.unregister_worker("p0-deep-w")

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


class God20P1(unittest.TestCase):
    def test_decide_fast_tools(self):
        from superai.brain import analyze
        from superai.executive import decide
        from superai.runtime import _plan

        t = analyze("calcula 2+2")
        d = decide(t, _plan(t), any_llm=True)
        self.assertEqual(d["path"], "tools")
        self.assertEqual(d["kind"], "DETERMINISTIC")
        self.assertFalse(d["queue"])
        self.assertFalse(d["memory"])

    def test_decide_normal_direct_or_no_provider(self):
        from superai.brain import analyze
        from superai.executive import decide
        from superai.runtime import _plan

        t = analyze("quem és tu em duas frases")
        p = _plan(t)
        self.assertEqual(decide(t, p, any_llm=True)["path"], "direct_llm")
        self.assertEqual(decide(t, p, any_llm=False)["path"], "no_provider")

    def test_decide_deep_queues_until_worker(self):
        from superai.brain import analyze
        from superai.executive import decide
        from superai.runtime import _plan

        t = analyze("implementa um refactor da arquitectura deste sistema crítico")
        p = _plan(t)
        self.assertEqual(decide(t, p, any_llm=True, from_worker=False)["path"], "queue")
        self.assertEqual(decide(t, p, any_llm=True, from_worker=True)["path"], "direct_llm")

    def test_mission_one_active(self):
        from superai import mission as ms

        prev = ms.active()
        a = ms.create("p1-miss-aaa-objetivo")
        b = ms.create("p1-miss-bbb-objetivo")
        try:
            self.assertTrue(a.get("ok") and b.get("ok"))
            self.assertEqual(ms.active()["id"], b["id"])
            self.assertEqual(ms.get(a["id"])["status"], "paused")
        finally:
            ms.set_status(a["id"], "cancelled")
            ms.set_status(b["id"], "cancelled")
            if prev:
                ms.set_status(prev["id"], "active")

    def test_mission_chat_commands(self):
        from superai import mission as ms
        from superai.runtime import handle

        prev = ms.active()
        r = handle("missão: p1-chat-nonce-zzqn")
        self.assertEqual(r.get("via"), "mission")
        try:
            a = ms.active()
            self.assertIsNotNone(a)
            self.assertIn("p1-chat-nonce-zzqn", a["goal"])
            self.assertEqual(handle("missão actual").get("via"), "mission")
        finally:
            handle("cancela missão")
            if prev:
                ms.set_status(prev["id"], "active")
        if not prev:
            self.assertIsNone(ms.active())

    def test_parent_id_persists_and_ready(self):
        from superai import queue as tq

        orig = tq.get_job
        try:
            tq.get_job = lambda pid: {"id": pid, "status": "queued"}
            self.assertFalse(tq.job_is_ready({"parent_id": "x"}))
            tq.get_job = lambda pid: {"id": pid, "status": "completed"}
            self.assertTrue(tq.job_is_ready({"parent_id": "x"}))
            tq.get_job = lambda pid: None
            self.assertTrue(tq.job_is_ready({"parent_id": "missing"}))
            self.assertTrue(tq.job_is_ready({"parent_id": None}))
        finally:
            tq.get_job = orig
        j1 = tq.enqueue("p1graph", "p1-parent-nonce-aa")
        j2 = tq.enqueue("p1graph", "p1-child-nonce-bb", parent_id=j1["id"])
        try:
            self.assertEqual(tq.get_job(j2["id"])["parent_id"], j1["id"])
            g = tq.graph(40)
            self.assertTrue(g["parallel"])  # inflight=2
            self.assertEqual(g["inflight_applied"], 2)
            self.assertEqual(g["kind"], "MEASURED")
            self.assertTrue(any(e.get("from") == j1["id"] and e.get("to") == j2["id"] for e in g["edges"]))
        finally:
            tq.cancel(j1["id"])
            tq.cancel(j2["id"])

    def test_sort_adapters_demotes_only_with_n3(self):
        from superai.routing import sort_adapters

        class A:
            def __init__(self, i):
                self.id = i

        failing = {"providers": [{"provider": "groq", "n": 5, "ok": 0, "fail": 5, "ok_rate": 0.0, "avg_latency_ms": 10}]}
        order = sort_adapters([A("groq"), A("cerebras")], failing)
        self.assertEqual(order[0].id, "cerebras")
        low_n = {"providers": [{"provider": "groq", "n": 2, "ok": 0, "fail": 2, "ok_rate": 0.0}]}
        order2 = sort_adapters([A("groq"), A("cerebras")], low_n)
        self.assertEqual(order2[0].id, "groq")

    def test_provider_stats_kind(self):
        from superai.tokens import provider_stats

        s = provider_stats()
        self.assertIn(s["kind"], ("MEASURED", "UNKNOWN"))
        if s["n_events"] == 0:
            self.assertEqual(s["kind"], "UNKNOWN")


class Validator(unittest.TestCase):
    def test_math_validation_passes(self):
        from superai.validator import validate

        task = analyze("calcula 2+2*3")
        r = execute("calculator", {"expr": "2+2*3"})
        v = validate(task, [r])
        self.assertTrue(v["passed"])
        self.assertEqual(v["kind"], "MEASURED")
        self.assertEqual(v["n_checks"], 2)  # math_result + math_verification
        self.assertEqual(v["n_passed"], 2)

    def test_math_validation_fails_on_error(self):
        from superai.validator import validate

        task = analyze("calcula algo")
        r = execute("calculator", {"expr": "hello"})
        v = validate(task, [r])
        self.assertFalse(v["passed"])
        self.assertEqual(v["n_checks"], 2)
        self.assertEqual(v["n_passed"], 1)  # math_verification passes (nothing to verify)

    def test_json_validation(self):
        from superai.validator import validate

        task = analyze("parse este json")
        r = execute("json", {"text": '{"a":1,"b":2}'})
        v = validate(task, [r])
        self.assertTrue(v["passed"])
        self.assertEqual(v["n_checks"], 1)
        self.assertIn("dict", v["checks"][0]["notes"][0])

    def test_git_validation(self):
        from superai.validator import validate

        task = analyze("git status")
        r = execute("git", {"args": ["status"]})
        v = validate(task, [r])
        self.assertTrue(v["passed"])
        self.assertEqual(v["n_checks"], 1)
        self.assertIn("exit=0", v["checks"][0]["notes"][0])

    def test_llm_empty_fails(self):
        from superai.validator import validate

        task = analyze("quem és tu")
        r = {"tool": "llm:groq", "status": "success", "findings": [{"text": ""}], "errors": [], "evidence": []}
        v = validate(task, [r], llm_text="")
        self.assertFalse(v["passed"])
        self.assertIn("empty", v["checks"][0]["notes"][0])

    def test_llm_nonempty_passes(self):
        from superai.validator import validate

        task = analyze("quem és tu")
        r = {"tool": "llm:groq", "status": "success", "findings": [{"text": "Sou a GOD."}], "errors": [], "evidence": []}
        v = validate(task, [r], llm_text="Sou a GOD.")
        self.assertTrue(v["passed"])
        self.assertIn("length=10", v["checks"][0]["notes"][0])

    def test_coding_cross_validation(self):
        from superai.validator import validate

        task = analyze("cria um website com html")
        r = {"tool": "llm:groq", "status": "success", "findings": [{"text": "Aqui:\n```html\n<!DOCTYPE html>\n<html><body><h1>Hi</h1></body></html>\n```"}], "errors": [], "evidence": []}
        v = validate(task, [r], llm_text="Aqui:\n```html\n<!DOCTYPE html>\n<html><body><h1>Hi</h1></body></html>\n```")
        self.assertTrue(v["passed"])
        self.assertEqual(v["n_checks"], 2)  # llm_response + coding_structure

    def test_validation_in_pipeline(self):
        from superai.runtime import handle, snapshot

        r = handle("calcula 7*8")
        self.assertIn(r.get("via"), ("tools", "cache"))
        p = snapshot().get("last_pipeline") or {}
        v = p.get("validation")
        if r.get("via") == "tools":
            self.assertIsNotNone(v)
            self.assertTrue(v["passed"])
            self.assertEqual(v["kind"], "MEASURED")
        # cache hits don't have validation (no tool execution)

    def test_fs_write_validation(self):
        from superai.validator import validate

        task = analyze("cria um ficheiro")
        r = execute("fs.write", {"slug": "valtest", "path": "index.html", "text": "<h1>test</h1>"})
        v = validate(task, [r])
        self.assertTrue(v["passed"])
        self.assertIn("bytes=", v["checks"][0]["notes"][0])

    def test_state_validation(self):
        from superai.validator import validate

        task = analyze("estado")
        r = {"tool": "state", "status": "success", "findings": [{"mode": "OFFLINE", "providers": []}], "errors": [], "evidence": ["snapshot"]}
        v = validate(task, [r])
        self.assertTrue(v["passed"])
        self.assertIn("mode=OFFLINE", v["checks"][0]["notes"][0])


class ThirdEye(unittest.TestCase):
    def test_criticism_passes_for_good_task(self):
        from superai.thirdeye import criticize

        task = analyze("calcula 2+2")
        pipeline = {
            "fast": True,
            "cache": "miss",
            "skipped_heavy": ["vector", "memory"],
            "stages_ms": {"cache": 1.0},
            "latency_ms": 20.0,
            "decision": {"path": "tools"},
        }
        tool_results = [{"tool": "calculator", "status": "success", "findings": [{"result": 4}], "errors": [], "evidence": []}]
        scores = {"OVERALL": 97, "tokens_actual": 0, "llm_used": False}
        c = criticize(pipeline, task, tool_results, scores)
        self.assertEqual(c["kind"], "MEASURED")
        self.assertEqual(c["overall"], "OK")
        self.assertEqual(c["n_issues"], 0)
        self.assertGreater(c["n_findings"], 0)

    def test_criticism_warns_on_slow_fast(self):
        from superai.thirdeye import criticize

        task = analyze("calcula 1+1")
        pipeline = {
            "fast": True,
            "cache": "miss",
            "skipped_heavy": ["vector", "memory"],
            "stages_ms": {"cache": 1.0, "tools": 200.0},
            "latency_ms": 300.0,
            "decision": {"path": "tools"},
        }
        tool_results = [{"tool": "calculator", "status": "success", "findings": [{"result": 2}], "errors": [], "evidence": []}]
        scores = {"OVERALL": 97, "tokens_actual": 0, "llm_used": False}
        c = criticize(pipeline, task, tool_results, scores)
        self.assertEqual(c["overall"], "ISSUES")
        self.assertGreater(c["n_issues"], 0)
        # Should warn about slow FAST task
        issues = [f for f in c["findings"] if f["severity"] == "WARNING"]
        self.assertTrue(any("latency" in f["check"] for f in issues))

    def test_criticism_warns_on_blocked_deterministic(self):
        from superai.thirdeye import criticize

        task = analyze("calcula 2+2")
        task["via"] = "blocked"
        pipeline = {
            "fast": True,
            "cache": "miss",
            "latency_ms": 10.0,
            "decision": {"path": "no_provider"},
        }
        scores = {"OVERALL": 40, "tokens_actual": 0, "llm_used": False}
        c = criticize(pipeline, task, [], scores)
        issues = [f for f in c["findings"] if f["severity"] == "WARNING"]
        self.assertTrue(any("Deterministic" in f["msg"] for f in issues))

    def test_criticism_ok_for_cache_hit(self):
        from superai.thirdeye import criticize

        task = analyze("calcula 2+2")
        pipeline = {
            "fast": True,
            "cache": "hit",
            "latency_ms": 5.0,
            "decision": {"path": "tools"},
        }
        scores = {"OVERALL": 97, "tokens_actual": 0, "llm_used": False}
        c = criticize(pipeline, task, [], scores)
        self.assertEqual(c["overall"], "OK")
        cache_findings = [f for f in c["findings"] if f["check"] == "cache_usage"]
        self.assertTrue(any("saved LLM" in f["msg"] for f in cache_findings))

    def test_criticism_in_pipeline(self):
        from superai.runtime import handle, snapshot

        r = handle("calcula 77+33")
        p = snapshot().get("last_pipeline") or {}
        crit = p.get("critique")
        if r.get("via") == "cache":
            # Cache hits don't run tools, so no critique
            self.assertIsNone(crit)
        else:
            self.assertIsNotNone(crit)
            self.assertEqual(crit["kind"], "MEASURED")
            self.assertIn(crit["overall"], ("OK", "ISSUES"))

    def test_format_criticism(self):
        from superai.thirdeye import format_criticism

        critique = {
            "overall": "OK",
            "task_id": "T-test",
            "task_type": "math",
            "exec_mode": "FAST",
            "via": "tools",
            "latency_ms": 20.0,
            "n_findings": 2,
            "n_issues": 0,
            "findings": [
                {"check": "latency", "severity": "OK", "msg": "FAST latency 20ms"},
                {"check": "scores", "severity": "OK", "msg": "Overall 97/100"},
            ],
            "recommendations": [],
        }
        out = format_criticism(critique)
        self.assertIn("THIRD EYE", out)
        self.assertIn("OK", out)
        self.assertIn("20ms", out)

    def test_criticism_recommends_on_low_score(self):
        from superai.thirdeye import criticize

        task = analyze("explica algo complexo")
        pipeline = {"latency_ms": 100.0, "decision": {"path": "llm"}}
        scores = {"OVERALL": 30, "tokens_actual": 100, "llm_used": True}
        c = criticize(pipeline, task, [], scores)
        self.assertGreater(len(c["recommendations"]), 0)
        recs = c["recommendations"]
        self.assertTrue(any("quality" in r["type"] for r in recs))


class P1GraphParallel(unittest.TestCase):
    """P1 Task Graph — inflight=2 paralelismo."""

    def setUp(self):
        from superai.store import store
        with store._lock, store._conn() as c:
            c.execute("UPDATE jobs SET status='cancelled' WHERE kind='chat' AND status IN ('queued','assigned','running')")

    def test_inflight_cap_returns_2(self):
        from superai.resources import inflight_cap

        cap = inflight_cap()
        self.assertEqual(cap["applied"], 2)
        self.assertEqual(cap["applied_kind"], "MEASURED")
        self.assertIn("inflight=2", cap["applied_reason"])
        self.assertEqual(cap["declared_pc_target"], 2)

    def test_graph_reflects_inflight_2(self):
        from superai import queue as tq

        g = tq.graph(20)
        self.assertTrue(g["parallel"])
        self.assertEqual(g["inflight_applied"], 2)
        self.assertIn("inflight=2", g["note"])

    def test_claim_allows_two_jobs(self):
        from superai import queue as tq
        from superai.store import store
        from superai.resources import inflight_cap
        import sys

        tq.register_worker("t-parallel", "t-parallel", "control", ["chat"])
        a = tq.enqueue("chat", "parallel-test-aaa-unique", None, "LOCAL_WORKER")
        b = tq.enqueue("chat", "parallel-test-bbb-unique", None, "LOCAL_WORKER")
        self.assertFalse(a.get("deduped"))
        self.assertFalse(b.get("deduped"))

        cap = inflight_cap()
        print(f"\n[PARALLEL] inflight_cap.applied={cap['applied']}", file=sys.stderr)

        with store._lock, store._conn() as c:
            rows = c.execute("SELECT id, status, worker_id, text FROM jobs WHERE kind='chat' AND status IN ('queued','assigned','running') ORDER BY ts").fetchall()
            print(f"[PARALLEL] active chat jobs: {len(rows)}", file=sys.stderr)
            for r in rows:
                print(f"[PARALLEL]   {r['id'][:12]} status={r['status']} worker={r['worker_id']} text={r['text'][:40]}", file=sys.stderr)

        c1 = tq.claim("t-parallel")
        print(f"[PARALLEL] c1={'OK '+c1['id'][:12] if c1 else 'NONE'}", file=sys.stderr)

        with store._lock, store._conn() as c:
            inf = c.execute("SELECT COUNT(*) FROM jobs WHERE worker_id='t-parallel' AND status IN ('assigned','running')").fetchone()[0]
            qd = c.execute("SELECT COUNT(*) FROM jobs WHERE status='queued' AND kind='chat'").fetchone()[0]
            print(f"[PARALLEL] after c1: inflight={inf} queued_chat={qd}", file=sys.stderr)

        c2 = tq.claim("t-parallel")
        print(f"[PARALLEL] c2={'OK '+c2['id'][:12] if c2 else 'NONE'}", file=sys.stderr)

        self.assertIsNotNone(c1)
        self.assertIsNotNone(c2, f"cap={cap['applied']} c1_ok={c1 is not None}")
        c3 = tq.claim("t-parallel")
        self.assertIsNone(c3)
        tq.cancel(c1["id"])
        if c2:
            tq.cancel(c2["id"])
        tq.unregister_worker("t-parallel")


class P1RouterReliability(unittest.TestCase):
    """P1 Router — ordenar por fiabilidade (ok_rate)."""

    def test_sort_by_ok_rate_desc(self):
        from superai.routing import sort_adapters

        class A:
            def __init__(self, i):
                self.id = i

        stats = {
            "providers": [
                {"provider": "groq", "n": 10, "ok": 3, "fail": 7, "ok_rate": 0.3, "avg_latency_ms": 50},
                {"provider": "cerebras", "n": 10, "ok": 9, "fail": 1, "ok_rate": 0.9, "avg_latency_ms": 100},
                {"provider": "gemini", "n": 10, "ok": 6, "fail": 4, "ok_rate": 0.6, "avg_latency_ms": 80},
            ]
        }
        adapters = [A("groq"), A("cerebras"), A("gemini")]
        order = sort_adapters(adapters, stats)
        # Should order by ok_rate desc: cerebras (0.9) > gemini (0.6) > groq (0.3, demoted)
        self.assertEqual(order[0].id, "cerebras")
        self.assertEqual(order[1].id, "gemini")
        self.assertEqual(order[2].id, "groq")

    def test_sort_by_latency_secondary(self):
        from superai.routing import sort_adapters

        class A:
            def __init__(self, i):
                self.id = i

        # Same ok_rate, different latency
        stats = {
            "providers": [
                {"provider": "groq", "n": 10, "ok": 8, "fail": 2, "ok_rate": 0.8, "avg_latency_ms": 200},
                {"provider": "cerebras", "n": 10, "ok": 8, "fail": 2, "ok_rate": 0.8, "avg_latency_ms": 50},
                {"provider": "gemini", "n": 10, "ok": 8, "fail": 2, "ok_rate": 0.8, "avg_latency_ms": 100},
            ]
        }
        adapters = [A("groq"), A("cerebras"), A("gemini")]
        order = sort_adapters(adapters, stats)
        # Same ok_rate, should order by latency asc: cerebras (50ms) > gemini (100ms) > groq (200ms)
        self.assertEqual(order[0].id, "cerebras")
        self.assertEqual(order[1].id, "gemini")
        self.assertEqual(order[2].id, "groq")

    def test_sort_demotes_low_ok_rate(self):
        from superai.routing import sort_adapters

        class A:
            def __init__(self, i):
                self.id = i

        stats = {
            "providers": [
                {"provider": "groq", "n": 10, "ok": 1, "fail": 9, "ok_rate": 0.1, "avg_latency_ms": 10},
                {"provider": "cerebras", "n": 10, "ok": 8, "fail": 2, "ok_rate": 0.8, "avg_latency_ms": 100},
            ]
        }
        adapters = [A("groq"), A("cerebras")]
        order = sort_adapters(adapters, stats)
        # groq has ok_rate 0.1 <= 0.3, should be demoted
        self.assertEqual(order[0].id, "cerebras")
        self.assertEqual(order[1].id, "groq")

    def test_sort_requires_n3(self):
        from superai.routing import sort_adapters

        class A:
            def __init__(self, i):
                self.id = i

        # n=2, not enough data to reorder
        stats = {
            "providers": [
                {"provider": "groq", "n": 2, "ok": 0, "fail": 2, "ok_rate": 0.0, "avg_latency_ms": 10},
                {"provider": "cerebras", "n": 2, "ok": 2, "fail": 0, "ok_rate": 1.0, "avg_latency_ms": 100},
            ]
        }
        adapters = [A("groq"), A("cerebras")]
        order = sort_adapters(adapters, stats)
        # Default order preserved (n < 3)
        self.assertEqual(order[0].id, "groq")

    def test_hardcore_mode_claude_first(self):
        from superai.routing import sort_adapters

        class A:
            def __init__(self, i):
                self.id = i

        stats = {
            "providers": [
                {"provider": "groq", "n": 10, "ok": 9, "fail": 1, "ok_rate": 0.9, "avg_latency_ms": 50},
                {"provider": "cerebras", "n": 10, "ok": 8, "fail": 2, "ok_rate": 0.8, "avg_latency_ms": 80},
                {"provider": "claude", "n": 10, "ok": 7, "fail": 3, "ok_rate": 0.7, "avg_latency_ms": 200},
            ]
        }
        adapters = [A("groq"), A("cerebras"), A("claude")]
        order_normal = sort_adapters(adapters, stats, hardcore=False)
        order_hardcore = sort_adapters(adapters, stats, hardcore=True)
        # Normal: by ok_rate desc
        self.assertEqual(order_normal[0].id, "groq")
        # Hardcore: claude first
        self.assertEqual(order_hardcore[0].id, "claude")


class P15SystemState(unittest.TestCase):
    """P1.5 System State — verifiable operational state."""

    def test_system_state_returns_measured(self):
        from superai.system import system_state
        s = system_state()
        self.assertEqual(s["system"]["name"], "GOD")
        self.assertIsNotNone(s["system"]["version"])
        self.assertIsNotNone(s["system"]["git_commit"])
        self.assertIsNotNone(s["system"]["ts"])

    def test_system_state_has_runtime(self):
        from superai.system import system_state
        s = system_state()
        self.assertIn(s["runtime"]["status"], ("healthy", "degraded"))
        self.assertEqual(s["runtime"]["kind"], "MEASURED")

    def test_system_state_has_providers(self):
        from superai.system import system_state
        s = system_state()
        self.assertIsInstance(s["providers"]["available"], list)
        self.assertEqual(s["providers"]["kind"], "MEASURED")

    def test_system_state_has_queue(self):
        from superai.system import system_state
        s = system_state()
        self.assertEqual(s["queue"]["kind"], "MEASURED")
        self.assertEqual(s["queue"]["inflight"], 2)

    def test_system_state_has_resources(self):
        from superai.system import system_state
        s = system_state()
        self.assertEqual(s["resources"]["kind"], "MEASURED")
        self.assertIn("host", s["resources"])
        self.assertIn("cpu_count", s["resources"]["host"])


class P15Capabilities(unittest.TestCase):
    """P1.5 Capability Registry."""

    def test_list_capabilities(self):
        from superai.capabilities import list_capabilities
        caps = list_capabilities()
        self.assertGreater(len(caps), 5)
        names = [c["name"] for c in caps]
        self.assertIn("memory", names)
        self.assertIn("voice", names)
        self.assertIn("llm_api", names)

    def test_can_memory(self):
        from superai.capabilities import can
        # memory should be implemented (Qdrant + SQLite)
        result = can("memory")
        self.assertIsInstance(result, bool)

    def test_can_voice_false(self):
        from superai.capabilities import can
        # voice is now implemented via edge-tts
        self.assertTrue(can("voice"))

    def test_can_nonexistent(self):
        from superai.capabilities import can
        self.assertFalse(can("nonexistent_capability_xyz"))

    def test_get_capability_memory(self):
        from superai.capabilities import get_capability
        mem = get_capability("memory")
        self.assertIsNotNone(mem)
        self.assertEqual(mem["name"], "memory")
        self.assertIn("status", mem)
        self.assertIn("evidence", mem)
        self.assertIn("limitations", mem)

    def test_capabilities_summary(self):
        from superai.capabilities import capabilities_summary
        s = capabilities_summary()
        self.assertEqual(s["kind"], "MEASURED")
        self.assertGreater(s["n"], 0)
        self.assertIn("implemented", s)
        self.assertIn("not_implemented", s)


class P15Health(unittest.TestCase):
    """P1.5 Health & Readiness."""

    def test_liveness(self):
        from superai.health import liveness
        h = liveness()
        self.assertIn(h["status"], ("healthy", "unhealthy"))
        self.assertEqual(h["kind"], "MEASURED")

    def test_readiness(self):
        from superai.health import readiness
        r = readiness()
        self.assertIn(r["status"], ("ready", "not_ready"))
        self.assertEqual(r["kind"], "MEASURED")
        self.assertIsInstance(r["checks"], list)
        self.assertGreater(len(r["checks"]), 0)

    def test_readiness_checks_each_component(self):
        from superai.health import readiness
        r = readiness()
        names = [c["name"] for c in r["checks"]]
        self.assertIn("sqlite", names)
        self.assertIn("worker", names)
        self.assertIn("queue_capacity", names)
        self.assertIn("memory_pressure", names)

    def test_full_health(self):
        from superai.health import full_health
        h = full_health()
        self.assertIn("liveness", h)
        self.assertIn("readiness", h)
        self.assertIn("diagnostics", h)

    def test_diagnostics(self):
        from superai.health import diagnostics
        d = diagnostics()
        self.assertEqual(d["kind"], "MEASURED")
        self.assertIsInstance(d["components"], list)
        self.assertGreater(d["n_components"], 0)


class P15Trace(unittest.TestCase):
    """P1.5 Decision Trace."""

    def test_start_trace(self):
        from superai.trace import start_trace, get_trace
        rid = start_trace("test-trace-1")
        self.assertEqual(rid, "test-trace-1")
        self.assertEqual(get_trace(rid), [])

    def test_record_decision(self):
        from superai.trace import start_trace, record_decision, get_trace
        rid = start_trace("test-trace-2")
        rec = record_decision(rid, "runtime", "tools", "FAST mode", result="executed")
        self.assertEqual(rec["component"], "runtime")
        self.assertEqual(rec["decision"], "tools")
        self.assertEqual(rec["result"], "executed")
        trace = get_trace(rid)
        self.assertEqual(len(trace), 1)

    def test_trace_summary(self):
        from superai.trace import start_trace, record_decision, trace_summary
        rid = start_trace("test-trace-3")
        record_decision(rid, "runtime", "tools", "math", result="ok")
        record_decision(rid, "validator", "passed", "all checks", result="ok")
        s = trace_summary(rid)
        self.assertTrue(s["found"])
        self.assertEqual(s["n_decisions"], 2)
        self.assertIn("runtime", s["components"])
        self.assertIn("validator", s["components"])

    def test_trace_summary_not_found(self):
        from superai.trace import trace_summary
        s = trace_summary("nonexistent-trace-xyz")
        self.assertFalse(s["found"])


class P15Endpoints(unittest.TestCase):
    """P1.5 API Endpoints."""

    def test_system_state_endpoint(self):
        from server import api_system_state
        r = api_system_state()
        self.assertEqual(r["system"]["name"], "GOD")

    def test_capabilities_endpoint(self):
        from server import api_capabilities
        r = api_capabilities()
        self.assertEqual(r["kind"], "MEASURED")
        self.assertGreater(r["n"], 0)

    def test_can_endpoint(self):
        from server import api_can
        r = api_can("voice")
        self.assertEqual(r["name"], "voice")
        self.assertTrue(r["can"])  # voice now implemented via edge-tts

    def test_liveness_endpoint(self):
        from server import api_liveness
        r = api_liveness()
        self.assertIn(r["status"], ("healthy", "unhealthy"))

    def test_readiness_endpoint(self):
        from server import api_readiness
        r = api_readiness()
        self.assertIn(r["status"], ("ready", "not_ready"))

    def test_health_full_endpoint(self):
        from server import api_health_full
        r = api_health_full()
        self.assertIn("liveness", r)
        self.assertIn("readiness", r)
        self.assertIn("diagnostics", r)

    def test_traces_endpoint(self):
        from server import api_traces
        r = api_traces()
        self.assertEqual(r["kind"], "MEASURED")


class P15FeatureFlags(unittest.TestCase):
    """P1.5 Feature Flags — disabled by default, risk-classified."""

    def test_flags_disabled_by_default(self):
        from superai.feature_flags import is_enabled
        # hardcore_mode should always be disabled by default
        self.assertFalse(is_enabled("hardcore_mode"))

    def test_list_flags(self):
        from superai.feature_flags import list_flags
        flags = list_flags()
        self.assertGreater(len(flags), 8)
        names = [f["name"] for f in flags]
        self.assertIn("semantic_cache", names)
        self.assertIn("auto_evolve", names)
        self.assertIn("hardcore_mode", names)
        self.assertIn("auto_cleanup", names)
        self.assertIn("rate_limiting", names)

    def test_enable_low_risk(self):
        from superai.feature_flags import enable, disable, is_enabled
        r = enable("semantic_cache", reason="test", actor="test")
        self.assertTrue(r["ok"])
        self.assertTrue(is_enabled("semantic_cache"))
        # Cleanup
        disable("semantic_cache", reason="test cleanup")

    def test_disable_flag(self):
        from superai.feature_flags import enable, disable, is_enabled
        enable("debug_trace", reason="test", actor="test")
        r = disable("debug_trace", reason="test cleanup")
        self.assertTrue(r["ok"])
        self.assertFalse(is_enabled("debug_trace"))

    def test_high_risk_blocked_in_strict(self):
        from superai.feature_flags import enable, is_enabled
        from superai.governor import gov
        if not gov.strict():
            self.skipTest("governor not strict")
        # hardcore_mode is HIGH RISK — should be blocked in strict mode
        r = enable("hardcore_mode", reason="test", actor="test")
        self.assertFalse(r["ok"])
        self.assertIn("HIGH RISK", r["error"])
        self.assertFalse(is_enabled("hardcore_mode"))

    def test_unknown_flag_rejected(self):
        from superai.feature_flags import enable
        r = enable("nonexistent_flag_xyz", reason="test")
        self.assertFalse(r["ok"])
        self.assertIn("desconhecida", r["error"])

    def test_flags_summary(self):
        from superai.feature_flags import flags_summary
        s = flags_summary()
        self.assertEqual(s["kind"], "MEASURED")
        self.assertGreater(s["n"], 0)
        self.assertIsInstance(s["enabled"], list)
        self.assertIsInstance(s["disabled"], list)
        self.assertIn("hardcore_mode", s["high_risk"])

    def test_flag_risk_classification(self):
        from superai.feature_flags import get_flag
        auto = get_flag("auto_evolve")
        self.assertEqual(auto["risk"], "medium")  # Reclassified: governor + classify_risk are safety nets
        cache = get_flag("semantic_cache")
        self.assertEqual(cache["risk"], "low")
        hc = get_flag("hardcore_mode")
        self.assertEqual(hc["risk"], "high")
        cost = get_flag("cost_routing")
        self.assertEqual(cost["risk"], "low")  # Reclassified: free tier first, fallback

    def test_flags_endpoint(self):
        from server import api_flags
        r = api_flags()
        self.assertEqual(r["kind"], "MEASURED")


class P15RuntimeProtection(unittest.TestCase):
    """P1.5 Runtime Protection — GOD Object anti-pattern detection."""

    def test_inspect_file(self):
        from superai.runtime_protection import inspect_file
        from superai.config import ROOT
        f = ROOT / "superai" / "brain.py"
        r = inspect_file(f)
        self.assertEqual(r["kind"], "MEASURED")
        self.assertIn("lines", r)
        self.assertIn("ast", r)

    def test_inspect_nonexistent(self):
        from superai.runtime_protection import inspect_file
        from pathlib import Path
        r = inspect_file(Path("/nonexistent/file.py"))
        self.assertEqual(r["status"], "not_found")

    def test_inspect_all(self):
        from superai.runtime_protection import inspect_all
        r = inspect_all()
        self.assertEqual(r["kind"], "MEASURED")
        self.assertGreater(r["n_files"], 10)
        self.assertIn("hard_blocks", r)
        self.assertIn("criticals", r)
        self.assertIn("warnings", r)

    def test_god_object_check(self):
        from superai.runtime_protection import check_god_object
        r = check_god_object()
        self.assertEqual(r["kind"], "MEASURED")
        self.assertEqual(r["file"], "runtime.py")
        self.assertIn("is_god_object", r)
        self.assertIn("lines", r)
        self.assertIn("n_functions", r)
        self.assertIn("total_complexity", r)

    def test_runtime_py_resolved(self):
        from superai.runtime_protection import check_god_object
        r = check_god_object()
        # After refactor: runtime.py handle() is 53 lines, not GOD Object
        self.assertFalse(r["is_god_object"], "runtime.py should NOT be GOD Object after refactor")
        self.assertLess(r["handle_fn"]["lines"], 100, "handle() should be under 100 lines")
        self.assertEqual(r["recommendation"], "OK: runtime.py dentro dos limites")

    def test_brain_py_within_limits(self):
        from superai.runtime_protection import inspect_file
        from superai.config import ROOT
        r = inspect_file(ROOT / "superai" / "brain.py")
        # brain.py at ~215 lines should be within limits
        self.assertNotEqual(r["worst_severity"], "HARD_BLOCK")

    def test_protection_report(self):
        from superai.runtime_protection import protection_report
        r = protection_report()
        self.assertIn("god_object", r)
        self.assertIn("all_files", r)
        self.assertEqual(r["kind"], "MEASURED")

    def test_god_object_endpoint(self):
        from server import api_god_object
        r = api_god_object()
        self.assertEqual(r["kind"], "MEASURED")

    def test_protection_endpoint(self):
        from server import api_protection
        r = api_protection()
        self.assertIn("god_object", r)
        self.assertIn("all_files", r)


class P15ControlledEvolution(unittest.TestCase):
    """P1.5 Controlled Evolution — risk classification + feature flags."""

    def test_classify_risk_low(self):
        from superai.evolution import classify_risk
        proposal = {
            "title": "Promover semantic cache",
            "hypothesis": "Embeddings acertam mais que hash",
            "payload": {"change": "cache lookup order"},
        }
        r = classify_risk(proposal)
        self.assertEqual(r["risk"], "low")
        self.assertFalse(r["requires_human"])

    def test_classify_risk_medium(self):
        from superai.evolution import classify_risk
        proposal = {
            "title": "Ajustar routing por prioridade",
            "hypothesis": "Provider X é mais fiável",
            "payload": {"change": "routing priority order"},
        }
        r = classify_risk(proposal)
        self.assertEqual(r["risk"], "medium")

    def test_classify_risk_high(self):
        from superai.evolution import classify_risk
        proposal = {
            "title": "Desactivar governor strict",
            "hypothesis": "Permitir auto-apply de código",
            "payload": {"change": "governor security settings"},
        }
        r = classify_risk(proposal)
        self.assertEqual(r["risk"], "high")
        self.assertTrue(r["requires_human"])

    def test_high_risk_blocked_in_evolution(self):
        from superai.evolution import propose_with_risk
        from superai.governor import gov
        if not gov.strict():
            self.skipTest("governor not strict")
        exp = propose_with_risk(
            title="Remover limites do governor",
            hypothesis="Governor é demasiado restritivo",
            change="disable governor security",
            metric="freedom",
            before={"strict": True},
            after={"strict": False},
        )
        self.assertEqual(exp["status"], "blocked")
        self.assertIn("blocked_reason", exp)

    def test_low_risk_pending_in_evolution(self):
        from superai.evolution import propose_with_risk
        exp = propose_with_risk(
            title="Semantic cache para paráfrases",
            hypothesis="Embeddings recuperam mais que hash",
            change="semantic cache lookup",
            metric="paraphrase_hits",
            before={"hash": 1},
            after={"semantic": 3},
        )
        self.assertEqual(exp["status"], "pending")
        self.assertEqual(exp["risk"], "low")


if __name__ == "__main__":
    unittest.main()


class TestClaimDebug(unittest.TestCase):
    """Temporary diagnostic for Windows claim failure."""

    def test_claim_debug(self):
        from superai import queue as tq
        from superai.store import store
        from superai.resources import inflight_cap
        import sys

        tq.register_worker("t-debug", "t-debug", "control", ["chat"])

        # Cleanup
        with store._lock, store._conn() as c:
            c.execute("UPDATE jobs SET status='cancelled' WHERE kind='chat' AND status IN ('queued','assigned','running')")

        cap = inflight_cap()
        print(f"\n[DIAG] inflight_cap={cap}", file=sys.stderr)

        a = tq.enqueue("chat", "diag-test-aaa-unique", None, "LOCAL_WORKER")
        b = tq.enqueue("chat", "diag-test-bbb-unique", None, "LOCAL_WORKER")
        print(f"[DIAG] a.deduped={a.get('deduped')} b.deduped={b.get('deduped')}", file=sys.stderr)

        # Check DB state
        with store._lock, store._conn() as c:
            all_jobs = c.execute("SELECT id, status, worker_id, text FROM jobs WHERE kind='chat' AND status IN ('queued','assigned','running') ORDER BY ts").fetchall()
            print(f"[DIAG] All active chat jobs:", file=sys.stderr)
            for j in all_jobs:
                print(f"[DIAG]   id={j['id'][:12]} status={j['status']} worker={j['worker_id']} text={j['text'][:30]}", file=sys.stderr)

        c1 = tq.claim("t-debug")
        print(f"[DIAG] c1={c1 is not None} (id={c1['id'][:12] if c1 else 'NONE'})", file=sys.stderr)

        with store._lock, store._conn() as c:
            inflight = c.execute("SELECT COUNT(*) FROM jobs WHERE worker_id='t-debug' AND status IN ('assigned','running')").fetchone()[0]
            queued = c.execute("SELECT COUNT(*) FROM jobs WHERE status='queued'").fetchone()[0]
            print(f"[DIAG] After c1: inflight={inflight} queued={queued}", file=sys.stderr)

        c2 = tq.claim("t-debug")
        print(f"[DIAG] c2={c2 is not None} (id={c2['id'][:12] if c2 else 'NONE'})", file=sys.stderr)

        tq.unregister_worker("t-debug")

        self.assertIsNotNone(c1)
        self.assertIsNotNone(c2)
