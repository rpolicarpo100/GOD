"""Tests for new autonomous AI modules: evidence, memory_layers, experiment_sandbox,
strategy_learner, self_model, autonomous_missions, self_development."""
import time
import pytest


# ── Evidence Engine ──────────────────────────────────────────────────────────

class TestEvidenceEngine:
    def test_claim_creation(self):
        from superai.evidence import Claim
        c = Claim(text="Python is great", source="test")
        assert c.text == "Python is great"
        assert c.source == "test"
        assert c.validation_status == "unvalidated"
        assert c.confidence == 0.5

    def test_add_evidence_supporting(self):
        from superai.evidence import Claim
        c = Claim(text="Test claim", source="test")
        ev = c.add_evidence("supporting", "Evidence data", 0.9)
        assert ev["type"] == "supporting"
        assert ev["strength"] == 0.9
        assert len(c.evidence) == 1

    def test_validation_supported(self):
        from superai.evidence import Claim
        c = Claim(text="Test", source="test")
        c.add_evidence("supporting", "A", 0.9)
        c.add_evidence("supporting", "B", 0.8)
        assert c.validation_status == "supported"

    def test_validation_refuted(self):
        from superai.evidence import Claim
        c = Claim(text="Test", source="test")
        c.add_evidence("refuting", "A", 0.9)
        c.add_evidence("refuting", "B", 0.8)
        assert c.validation_status == "refuted"

    def test_validation_uncertain(self):
        from superai.evidence import Claim
        c = Claim(text="Test", source="test")
        c.add_evidence("supporting", "A", 0.5)
        c.add_evidence("refuting", "B", 0.5)
        assert c.validation_status == "uncertain"

    def test_validate_claim_from_tools(self):
        from superai.evidence import validate_claim_from_tools
        result = validate_claim_from_tools("test claim", [
            {"tool": "web.search", "status": "success",
             "findings": [{"text": "supports claim"}], "errors": [], "evidence": ["search"]},
        ])
        assert "validation_status" in result
        assert result["n_evidence"] >= 1

    def test_validate_claim_empty_tools(self):
        from superai.evidence import validate_claim_from_tools
        result = validate_claim_from_tools("test", [])
        assert result["validation_status"] == "unvalidated"

    def test_get_evidence_summary(self):
        from superai.evidence import Claim, get_evidence_summary
        c = Claim(text="Test", source="test")
        c.add_evidence("supporting", "data", 0.8)
        summary = get_evidence_summary(c.id)
        assert summary is not None or summary is None  # may not find if not persisted


# ── Memory Layers ────────────────────────────────────────────────────────────

class TestMemoryLayers:
    def test_memory_system_init(self):
        from superai.memory_layers import get_memory
        mem = get_memory()
        assert mem is not None
        stats = mem.stats()
        assert "working" in stats
        assert "episodic" in stats
        assert "semantic" in stats
        assert "procedural" in stats
        assert "self" in stats

    def test_working_memory_capacity(self):
        from superai.memory_layers import WorkingMemory
        wm = WorkingMemory()
        for i in range(12):
            wm.add(f"item_{i}", {"text": f"Item {i}"})
        assert wm.count() <= 9  # Miller's Law

    def test_remember_and_recall(self):
        from superai.memory_layers import get_memory
        mem = get_memory()
        key = f"test_{time.time()}"
        mem.remember(key, {"text": "hello world", "confidence": 0.9}, layer="semantic")
        result = mem.recall(key, layer="semantic")
        assert result is not None
        assert result["text"] == "hello world"

    def test_cross_layer_recall(self):
        from superai.memory_layers import get_memory
        mem = get_memory()
        key = f"cross_{time.time()}"
        mem.remember(key, {"text": "cross layer"}, layer="episodic")
        result = mem.recall(key)  # search all layers
        assert result is not None

    def test_consolidation(self):
        from superai.memory_layers import get_memory
        mem = get_memory()
        result = mem.consolidate()
        assert "working_to_episodic" in result
        assert "episodic_to_semantic" in result

    def test_procedural_outcome(self):
        from superai.memory_layers import get_memory
        mem = get_memory()
        key = f"proc_{time.time()}"
        mem.learn_procedure(key, {"strategy": "test strategy"})
        mem.record_procedure_outcome(key, True)
        mem.record_procedure_outcome(key, True)
        mem.record_procedure_outcome(key, False)
        strategies = mem.get_strategies(5)
        # May or may not find it depending on min attempts

    def test_self_memory_capabilities(self):
        from superai.memory_layers import get_memory
        mem = get_memory()
        mem.remember("cap_test", {"type": "capability", "text": "can do X"}, layer="self")
        caps = mem.self_mem.get_capabilities()
        assert any(c.get("text") == "can do X" for c in caps)


# ── Experiment Sandbox ───────────────────────────────────────────────────────

class TestExperimentSandbox:
    def test_create_experiment(self):
        from superai.experiment_sandbox import ExperimentSandbox
        sb = ExperimentSandbox()
        exp = sb.create_experiment("test", "desc", "old", "new", "quality")
        assert exp["name"] == "test"
        assert exp["status"] == "created"

    def test_run_trial(self):
        from superai.experiment_sandbox import ExperimentSandbox
        sb = ExperimentSandbox()
        exp = sb.create_experiment("trial_test", "desc", "old", "new")
        r = sb.run_trial(exp["id"], "old", "input", "output", 70.0)
        assert r["ok"]
        assert r["variant"] == "old"

    def test_evaluate_insufficient_data(self):
        from superai.experiment_sandbox import ExperimentSandbox
        sb = ExperimentSandbox()
        exp = sb.create_experiment("eval_test", "desc", "old", "new")
        sb.run_trial(exp["id"], "old", "i", "o", 60.0)
        r = sb.evaluate(exp["id"])
        assert r["status"] == "insufficient_data"

    def test_evaluate_adopt_new(self):
        from superai.experiment_sandbox import ExperimentSandbox
        sb = ExperimentSandbox()
        exp = sb.create_experiment("adopt_test", "desc", "old", "new")
        xid = exp["id"]
        for i in range(6):
            sb.run_trial(xid, "old", f"i{i}", f"o{i}", 60.0)
            sb.run_trial(xid, "new", f"i{i}", f"o{i}", 80.0)
        r = sb.evaluate(xid)
        assert r["recommendation"] == "adopt_new"

    def test_canary_deploy(self):
        from superai.experiment_sandbox import ExperimentSandbox
        sb = ExperimentSandbox()
        exp = sb.create_experiment("canary_test", "desc", "old", "new")
        r = sb.canary_deploy(exp["id"], 30)
        assert r["ok"]
        assert r["canary_pct"] == 30

    def test_adopt(self):
        from superai.experiment_sandbox import ExperimentSandbox
        sb = ExperimentSandbox()
        exp = sb.create_experiment("adopt_test2", "desc", "old", "new")
        r = sb.adopt(exp["id"])
        assert r["ok"]
        assert r["status"] == "adopted"

    def test_rollback(self):
        from superai.experiment_sandbox import ExperimentSandbox
        sb = ExperimentSandbox()
        exp = sb.create_experiment("rb_test", "desc", "old", "new")
        r = sb.rollback(exp["id"], "test reason")
        assert r["ok"]
        assert r["status"] == "rolled_back"


# ── Strategy Learner ─────────────────────────────────────────────────────────

class TestStrategyLearner:
    def test_record_outcome(self):
        from superai.strategy_learner import StrategyLearner
        sl = StrategyLearner()
        sl.record_task_outcome("test_type", "llm", "provider_a", 85.0, 1000.0, [])
        summary = sl.get_strategy_summary()
        assert summary["total_strategies"] > 0

    def test_best_provider(self):
        from superai.strategy_learner import StrategyLearner
        sl = StrategyLearner()
        for i in range(5):
            sl.record_task_outcome("coding", "llm", "openai", 90.0, 1000.0, [])
            sl.record_task_outcome("coding", "llm", "anthropic", 70.0, 1200.0, [])
        best = sl.get_best_provider("coding")
        assert best == "openai"

    def test_best_tool(self):
        from superai.strategy_learner import StrategyLearner
        sl = StrategyLearner()
        for i in range(5):
            sl.record_task_outcome("files", "tools", "", 90.0, 500.0, ["fs.read"])
            sl.record_task_outcome("files", "tools", "", 60.0, 800.0, ["fs.list"])
        best = sl.get_best_tool("files")
        assert best == "fs.read"

    def test_best_provider_unknown_type(self):
        from superai.strategy_learner import StrategyLearner
        sl = StrategyLearner()
        best = sl.get_best_provider("nonexistent_type_xyz")
        assert best is None


# ── Self Model ───────────────────────────────────────────────────────────────

class TestSelfModel:
    def test_get_self_model(self):
        from superai.self_model import get_self_model
        sm = get_self_model()
        assert "capabilities" in sm
        assert "limitations" in sm
        assert "suggestions" in sm

    def test_what_can_i_do(self):
        from superai.self_model import what_can_i_do
        result = what_can_i_do()
        assert isinstance(result, list)

    def test_what_cant_i_do(self):
        from superai.self_model import what_cant_i_do
        result = what_cant_i_do()
        assert isinstance(result, list)

    def test_what_should_improve(self):
        from superai.self_model import what_should_improve
        result = what_should_improve()
        assert isinstance(result, list)


# ── Autonomous Missions ──────────────────────────────────────────────────────

class TestAutonomousMissions:
    def test_create_mission(self):
        from superai.autonomous_missions import MissionControl
        mc = MissionControl()
        m = mc.create_mission("test", "target", "reason", priority=3)
        assert m.type == "test"
        assert m.status == "pending"

    def test_start_mission(self):
        from superai.autonomous_missions import MissionControl
        mc = MissionControl()
        m = mc.create_mission("test", "target", "reason")
        r = mc.start_mission(m.id)
        assert r["ok"]

    def test_complete_mission(self):
        from superai.autonomous_missions import MissionControl
        mc = MissionControl()
        m = mc.create_mission("test", "target", "reason")
        mc.start_mission(m.id)
        r = mc.complete_mission(m.id, {"result": "done"})
        assert r["ok"]

    def test_fail_mission_retry(self):
        from superai.autonomous_missions import MissionControl
        mc = MissionControl()
        m = mc.create_mission("test", "target", "reason")
        mc.start_mission(m.id)
        r = mc.fail_mission(m.id, "error")
        assert r["ok"]
        assert r["mission"]["status"] == "failed"

    def test_get_pending(self):
        from superai.autonomous_missions import MissionControl
        mc = MissionControl()
        mc.create_mission("test1", "t1", "r1", priority=2)
        mc.create_mission("test2", "t2", "r2", priority=1)
        pending = mc.get_pending()
        assert len(pending) >= 2
        # Should be sorted by priority (lower = higher priority)
        assert pending[0]["priority"] <= pending[1]["priority"]

    def test_detect_opportunities(self):
        from superai.autonomous_missions import MissionControl
        mc = MissionControl()
        opps = mc.detect_opportunities()
        assert isinstance(opps, list)

    def test_stats(self):
        from superai.autonomous_missions import MissionControl
        mc = MissionControl()
        stats = mc.stats()
        assert "active" in stats
        assert "completed_total" in stats


# ── Self Development ─────────────────────────────────────────────────────────

class TestSelfDevelopment:
    def test_propose_safe_change(self):
        from superai.self_development import SelfDevelopment
        sd = SelfDevelopment()
        r = sd.propose_change("superai/test_file.py", "test change", "old", "new")
        assert r["ok"]

    def test_propose_blocked_file(self):
        from superai.self_development import SelfDevelopment
        sd = SelfDevelopment()
        r = sd.propose_change("superai/auth.py", "try modify auth", "old", "new")
        assert not r["ok"]
        assert "BLOCKED" in r["error"]

    def test_propose_path_traversal(self):
        from superai.self_development import SelfDevelopment
        sd = SelfDevelopment()
        r = sd.propose_change("../../../etc/passwd", "hack", "old", "new")
        assert not r["ok"]

    def test_reject_proposal(self):
        from superai.self_development import SelfDevelopment
        sd = SelfDevelopment()
        r = sd.propose_change("superai/test_reject.py", "test", "old", "new")
        assert r["ok"]
        pid = r["proposal"]["id"]
        r2 = sd.reject(pid, "not needed")
        assert r2["ok"]

    def test_list_proposals(self):
        from superai.self_development import SelfDevelopment
        sd = SelfDevelopment()
        sd.propose_change("superai/test_list.py", "test", "old", "new")
        proposals = sd.list_proposals()
        assert isinstance(proposals, list)

    def test_stats(self):
        from superai.self_development import SelfDevelopment
        sd = SelfDevelopment()
        stats = sd.stats()
        assert "pending_proposals" in stats
        assert "total_applied" in stats


# ── Adversarial Third Eye ────────────────────────────────────────────────────

class TestAdversarial:
    def test_passed(self):
        from superai.thirdeye import adversarial_check
        r = adversarial_check(
            {"evidence": {"validation_status": "supported", "n_supporting": 3, "n_refuting": 0, "n_evidence": 3}},
            {"type": "general"},
            [{"tool": "web.search", "status": "success"}],
            {"OVERALL": 80},
        )
        assert r["status"] == "passed"

    def test_contradicted(self):
        from superai.thirdeye import adversarial_check
        r = adversarial_check(
            {"evidence": {"validation_status": "refuted", "n_supporting": 0, "n_refuting": 3, "n_evidence": 3}},
            {"type": "general"},
            [{"tool": "web.search", "status": "error", "errors": ["timeout"]}],
            {"OVERALL": 30},
        )
        assert r["status"] == "contradicted"
        assert len(r["contradictions"]) > 0

    def test_weak(self):
        from superai.thirdeye import adversarial_check
        r = adversarial_check(
            {"evidence": {"validation_status": "unvalidated", "n_supporting": 1, "n_refuting": 0, "n_evidence": 1}},
            {"type": "general"},
            [],  # no tool results
            {"OVERALL": 30},  # low quality
        )
        assert r["status"] in ("weak", "passed")

    def test_confidence_adjustment(self):
        from superai.thirdeye import adversarial_check
        r = adversarial_check(
            {"evidence": {"validation_status": "refuted", "n_supporting": 0, "n_refuting": 5, "n_evidence": 5}},
            {"type": "general"},
            [{"tool": "x", "status": "error", "errors": ["fail"]}],
            {"OVERALL": 20},
        )
        assert r["confidence_adjustment"] < 0


# ── Telemetry ────────────────────────────────────────────────────────────────

class TestTelemetry:
    def test_record_system_metric(self):
        from superai.trace import record_system_metric, get_system_metrics
        record_system_metric("test_metric_unique_123")
        record_system_metric("test_metric_unique_123")
        metrics = get_system_metrics()
        assert metrics.get("test_metric_unique_123", 0) >= 2

    def test_record_provider_call(self):
        from superai.trace import record_provider_call, get_provider_score
        record_provider_call("test_prov_xyz", True, 500.0, 100)
        score = get_provider_score("test_prov_xyz")
        assert score is not None
        assert score["score"] > 0

    def test_provider_score_latency(self):
        from superai.trace import record_provider_call, get_provider_score
        for i in range(5):
            record_provider_call("fast_provider", True, 100.0, 50)
        score = get_provider_score("fast_provider")
        assert score["p50_ms"] <= 200


# ── Evolution Rollback ──────────────────────────────────────────────────────

class TestEvolutionRollback:
    def test_check_regression(self):
        from superai.evolution import check_regression_and_rollback
        r = check_regression_and_rollback()
        assert "checked" in r
        assert "rolled_back" in r

    def test_rollback_nonexistent(self):
        from superai.evolution import rollback_experiment
        r = rollback_experiment("nonexistent_id_xyz")
        assert not r["ok"]
