from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .config import DATA
from .util import now_iso, uid

DB = DATA / "spine.db"


class Store:
    def __init__(self, path: Path = DB) -> None:
        self._lock = threading.Lock()
        self.path = path
        self._tls = threading.local()
        self._init()

    def _get_conn(self) -> sqlite3.Connection:
        """Return a thread-local persistent connection."""
        c = getattr(self._tls, "conn", None)
        if c is None:
            c = sqlite3.connect(str(self.path), timeout=5)
            c.row_factory = sqlite3.Row
            try:
                c.execute("PRAGMA journal_mode=WAL")
                c.execute("PRAGMA busy_timeout=3000")
            except Exception:
                pass
            self._tls.conn = c
        return c

    @contextmanager
    def _conn(self):
        c = self._get_conn()
        try:
            yield c
            c.commit()
        except Exception:
            try:
                c.rollback()
            except Exception:
                pass
            raise

    def _init(self) -> None:
        with self._conn() as c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                  id TEXT PRIMARY KEY, name TEXT, level TEXT, msg TEXT, ts TEXT, payload TEXT
                );
                CREATE TABLE IF NOT EXISTS tasks (
                  id TEXT PRIMARY KEY, status TEXT, type TEXT, title TEXT, payload TEXT, ts TEXT
                );
                CREATE TABLE IF NOT EXISTS cache (
                  key TEXT PRIMARY KEY, norm TEXT, result TEXT, quality REAL, ts TEXT, hits INTEGER
                );
                CREATE TABLE IF NOT EXISTS memory (
                  id TEXT PRIMARY KEY, kind TEXT, key TEXT, value TEXT, ts TEXT
                );
                CREATE TABLE IF NOT EXISTS token_log (
                  id TEXT PRIMARY KEY, task_id TEXT, estimated INTEGER, actual INTEGER,
                  model TEXT, llm INTEGER, ts TEXT
                );
                CREATE TABLE IF NOT EXISTS audit (
                  id TEXT PRIMARY KEY, actor TEXT, action TEXT, detail TEXT, ts TEXT
                );
                CREATE TABLE IF NOT EXISTS ratings (
                  id TEXT PRIMARY KEY, task_id TEXT, scores TEXT, ts TEXT
                );
                CREATE TABLE IF NOT EXISTS usage (
                  k TEXT PRIMARY KEY, v INTEGER
                );
                CREATE TABLE IF NOT EXISTS benchmarks (
                  id TEXT PRIMARY KEY, run_id TEXT, case_id TEXT, kind TEXT, provider TEXT,
                  passed INTEGER, score REAL, latency_ms REAL, skipped INTEGER,
                  skip_reason TEXT, detail TEXT, ts TEXT
                );
                CREATE TABLE IF NOT EXISTS experiments (
                  id TEXT PRIMARY KEY, title TEXT, hypothesis TEXT, status TEXT,
                  metric TEXT, before TEXT, after TEXT, risk TEXT, payload TEXT, ts TEXT
                );
                CREATE TABLE IF NOT EXISTS token_events (
                  id TEXT PRIMARY KEY,
                  request_id TEXT,
                  task_id TEXT,
                  provider TEXT,
                  model TEXT,
                  ts TEXT,
                  estimated_tokens INTEGER,
                  actual_tokens INTEGER,
                  input_tokens INTEGER,
                  output_tokens INTEGER,
                  cached_tokens INTEGER,
                  reasoning_tokens INTEGER,
                  total_tokens INTEGER,
                  cost_kind TEXT,
                  actual_cost REAL,
                  token_kind TEXT,
                  latency_ms REAL,
                  status TEXT,
                  retry_count INTEGER,
                  cache_hit INTEGER,
                  context_tokens INTEGER,
                  quality_score REAL,
                  estimation_error REAL,
                  via TEXT,
                  payload TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_te_ts ON token_events(ts);
                CREATE INDEX IF NOT EXISTS idx_te_task ON token_events(task_id);
                CREATE INDEX IF NOT EXISTS idx_te_model ON token_events(model);
                CREATE TABLE IF NOT EXISTS model_pricing (
                  id TEXT PRIMARY KEY,
                  provider TEXT,
                  model TEXT,
                  input_cost_per_1m REAL,
                  output_cost_per_1m REAL,
                  cached_cost_per_1m REAL,
                  currency TEXT,
                  effective_from TEXT,
                  source TEXT,
                  verified INTEGER
                );
                CREATE TABLE IF NOT EXISTS perf_history (
                  id TEXT PRIMARY KEY,
                  ts TEXT,
                  latency_ms REAL,
                  type TEXT,
                  complexity INTEGER,
                  exec_mode TEXT,
                  tokens_est INTEGER,
                  via TEXT,
                  ok INTEGER,
                  text_len INTEGER
                );
                CREATE INDEX IF NOT EXISTS idx_perf_ts ON perf_history(ts);
                """
            )
            for k in ("session_tokens", "daily_tokens", "project_tokens", "llm_calls", "tool_calls", "cache_hits", "cache_misses"):
                c.execute("INSERT OR IGNORE INTO usage(k,v) VALUES(?,0)", (k,))

    def audit(self, actor: str, action: str, detail: str) -> None:
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT INTO audit VALUES(?,?,?,?,?)",
                (uid("au"), actor, action, detail[:4000], now_iso()),
            )

    def save_event(self, ev: dict) -> None:
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO events VALUES(?,?,?,?,?,?)",
                (ev["id"], ev["name"], ev["level"], ev["msg"], ev["ts"], json.dumps({k: v for k, v in ev.items() if k not in ("id", "name", "level", "msg", "ts")})),
            )

    def save_task(self, task: dict) -> None:
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO tasks VALUES(?,?,?,?,?,?)",
                (task["task_id"], task.get("status", ""), task.get("type", ""), task.get("title", ""), json.dumps(task), task.get("ts") or now_iso()),
            )

    def tasks(self, n: int = 40) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT payload FROM tasks ORDER BY ts DESC LIMIT ?", (n,)).fetchall()
        out = []
        for r in rows:
            try:
                out.append(json.loads(r["payload"]))
            except Exception:
                pass
        return out

    def incr(self, k: str, n: int = 1) -> int:
        with self._lock, self._conn() as c:
            c.execute("INSERT OR IGNORE INTO usage(k,v) VALUES(?,0)", (k,))
            c.execute("UPDATE usage SET v = v + ? WHERE k = ?", (n, k))
            v = c.execute("SELECT v FROM usage WHERE k=?", (k,)).fetchone()[0]
        return int(v)

    def usage(self) -> dict[str, int]:
        with self._conn() as c:
            rows = c.execute("SELECT k,v FROM usage").fetchall()
        return {r["k"]: int(r["v"]) for r in rows}

    def cache_get(self, key: str) -> dict | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM cache WHERE key=?", (key,)).fetchone()
        if not r:
            return None
        with self._lock, self._conn() as c:
            c.execute("UPDATE cache SET hits = hits + 1 WHERE key=?", (key,))
        return {"key": r["key"], "norm": r["norm"], "result": json.loads(r["result"]), "quality": r["quality"], "ts": r["ts"], "hits": r["hits"] + 1}

    def cache_put(self, key: str, norm: str, result: dict, quality: float) -> None:
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO cache VALUES(?,?,?,?,?,?)",
                (key, norm, json.dumps(result, ensure_ascii=False), quality, now_iso(), 0),
            )

    def cache_stats(self) -> dict:
        with self._conn() as c:
            n = c.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
            hits = c.execute("SELECT COALESCE(SUM(hits),0) FROM cache").fetchone()[0]
        u = self.usage()
        miss = u.get("cache_misses", 0)
        hit = u.get("cache_hits", 0)
        total = hit + miss
        return {"entries": int(n), "stored_hits": int(hits), "hit_rate": (hit / total) if total else None, "hits": hit, "misses": miss}

    def mem_put(self, kind: str, key: str, value: Any) -> None:
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT INTO memory VALUES(?,?,?,?,?)",
                (uid("mem"), kind, key[:200], json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value, now_iso()),
            )

    def mem_search(self, q: str, limit: int = 8, kinds: list[str] | None = None) -> list[dict]:
        words = [w for w in q.lower().split() if len(w) > 2][:8]
        if not words:
            return []
        like = " OR ".join(["key LIKE ? OR value LIKE ?"] * len(words))
        args: list[str] = []
        where = f"({like})"
        if kinds:
            clean = [str(k)[:80] for k in kinds if k][:8]
            if clean:
                ph = ",".join("?" * len(clean))
                where = f"kind IN ({ph}) AND {where}"
                args.extend(clean)
        for w in words:
            args.extend([f"%{w}%", f"%{w}%"])
        with self._conn() as c:
            rows = c.execute(
                f"SELECT * FROM memory WHERE {where} ORDER BY ts DESC LIMIT {int(limit)}",
                args,
            ).fetchall()
        return [{"id": r["id"], "kind": r["kind"], "key": r["key"], "value": r["value"], "ts": r["ts"]} for r in rows]

    def mem_counts(self) -> dict[str, int]:
        with self._conn() as c:
            rows = c.execute("SELECT kind, COUNT(*) n FROM memory GROUP BY kind").fetchall()
        return {r["kind"]: r["n"] for r in rows}

    def log_tokens(self, task_id: str, estimated: int, actual: int, model: str | None, llm: bool) -> None:
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT INTO token_log VALUES(?,?,?,?,?,?,?)",
                (uid("tok"), task_id, estimated, actual, model, 1 if llm else 0, now_iso()),
            )
        if actual:
            self.incr("session_tokens", actual)
            self.incr("daily_tokens", actual)
            self.incr("project_tokens", actual)

    def save_rating(self, task_id: str, scores: dict) -> None:
        with self._lock, self._conn() as c:
            c.execute("INSERT INTO ratings VALUES(?,?,?,?)", (uid("rt"), task_id, json.dumps(scores), now_iso()))

    def last_rating(self) -> dict | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM ratings ORDER BY ts DESC LIMIT 1").fetchone()
        if not r:
            return None
        return {"task_id": r["task_id"], **json.loads(r["scores"]), "ts": r["ts"]}

    def save_benchmark(self, row: dict) -> None:
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT INTO benchmarks VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    row["id"],
                    row["run_id"],
                    row["case_id"],
                    row["kind"],
                    row.get("provider"),
                    1 if row.get("passed") else 0,
                    row.get("score"),
                    row.get("latency_ms"),
                    1 if row.get("skipped") else 0,
                    row.get("skip_reason"),
                    json.dumps(row.get("detail"), ensure_ascii=False, default=str),
                    row["ts"],
                ),
            )

    def last_benchmark_run(self) -> dict | None:
        with self._conn() as c:
            r = c.execute("SELECT run_id FROM benchmarks ORDER BY ts DESC LIMIT 1").fetchone()
            if not r:
                return None
            rows = c.execute("SELECT * FROM benchmarks WHERE run_id=? ORDER BY ts", (r["run_id"],)).fetchall()
        items = [dict(x) for x in rows]
        for it in items:
            it["passed"] = bool(it["passed"])
            it["skipped"] = bool(it["skipped"])
            try:
                it["detail"] = json.loads(it["detail"]) if it["detail"] else None
            except Exception:
                pass
        return {
            "run_id": r["run_id"],
            "n": len(items),
            "n_llm_samples": sum(1 for i in items if i["kind"] == "llm" and not i["skipped"]),
            "passed": sum(1 for i in items if i["passed"]),
            "skipped": sum(1 for i in items if i["skipped"]),
            "rows": items,
        }

    def save_experiment(self, exp: dict) -> None:
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO experiments VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    exp["id"],
                    exp.get("title"),
                    exp.get("hypothesis"),
                    exp.get("status"),
                    exp.get("metric"),
                    json.dumps(exp.get("before"), ensure_ascii=False),
                    json.dumps(exp.get("after"), ensure_ascii=False),
                    exp.get("risk"),
                    json.dumps(exp.get("payload"), ensure_ascii=False, default=str),
                    exp.get("ts"),
                ),
            )

    def get_experiment(self, xid: str) -> dict | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM experiments WHERE id=?", (xid,)).fetchone()
        return self._exp_row(r) if r else None

    def set_experiment_status(self, xid: str, status: str) -> None:
        with self._lock, self._conn() as c:
            c.execute("UPDATE experiments SET status=? WHERE id=?", (status, xid))

    def experiments(self, n: int = 20) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM experiments ORDER BY ts DESC LIMIT ?", (n,)).fetchall()
        return [self._exp_row(r) for r in rows]

    def _exp_row(self, r: sqlite3.Row) -> dict:
        def j(x):
            try:
                return json.loads(x) if x else None
            except Exception:
                return x

        return {
            "id": r["id"],
            "title": r["title"],
            "hypothesis": r["hypothesis"],
            "status": r["status"],
            "metric": r["metric"],
            "before": j(r["before"]),
            "after": j(r["after"]),
            "risk": r["risk"],
            "payload": j(r["payload"]),
            "ts": r["ts"],
        }

    def save_token_event(self, ev: dict) -> None:
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT INTO token_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    ev["id"],
                    ev.get("request_id"),
                    ev.get("task_id"),
                    ev.get("provider"),
                    ev.get("model"),
                    ev.get("timestamp"),
                    ev.get("estimated_tokens"),
                    ev.get("actual_tokens"),
                    ev.get("input_tokens"),
                    ev.get("output_tokens"),
                    ev.get("cached_tokens"),
                    ev.get("reasoning_tokens"),
                    ev.get("total_tokens"),
                    ev.get("cost_kind"),
                    ev.get("actual_cost"),
                    ev.get("token_kind"),
                    ev.get("latency_ms"),
                    ev.get("status"),
                    int(ev.get("retry_count") or 0),
                    1 if ev.get("cache_hit") else 0,
                    ev.get("context_tokens"),
                    ev.get("quality_score"),
                    ev.get("estimation_error"),
                    ev.get("via"),
                    json.dumps(
                        {k: ev.get(k) for k in ("estimated_cost", "agent_id", "project_id", "context", "fallback", "route_advice")},
                        ensure_ascii=False,
                    ),
                ),
            )

    def recent_token_events(self, n: int = 40) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM token_events ORDER BY ts DESC LIMIT ?", (n,)).fetchall()
        return [dict(r) for r in rows]

    def token_log_stats(self) -> dict:
        with self._conn() as c:
            n = c.execute("SELECT COUNT(*) FROM token_log").fetchone()[0]
            se = c.execute("SELECT COALESCE(SUM(estimated),0) FROM token_log").fetchone()[0]
            sa = c.execute("SELECT COALESCE(SUM(actual),0) FROM token_log").fetchone()[0]
            llm = c.execute("SELECT COUNT(*) FROM token_log WHERE llm=1").fetchone()[0]
        return {"n": int(n), "sum_estimated": int(se), "sum_actual": int(sa), "llm_rows": int(llm)}

    def token_log_day_count(self) -> int:
        with self._conn() as c:
            n = c.execute("SELECT COUNT(DISTINCT substr(ts,1,10)) FROM token_log").fetchone()[0]
        return int(n or 0)

    def token_log_daily_actual(self) -> dict[str, int]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT substr(ts,1,10) d, COALESCE(SUM(actual),0) s FROM token_log GROUP BY d"
            ).fetchall()
        return {r["d"]: int(r["s"]) for r in rows}

    def pricing_rows(self, provider: str | None = None, model: str | None = None) -> list[dict]:
        q = "SELECT * FROM model_pricing"
        args: list[Any] = []
        if provider and model:
            q += " WHERE provider=? AND (model=? OR model='*')"
            args = [provider, model]
        elif provider:
            q += " WHERE provider=?"
            args = [provider]
        with self._conn() as c:
            rows = c.execute(q, args).fetchall()
        return [dict(r) for r in rows]

    def recent_ratings(self, n: int = 40) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT scores FROM ratings ORDER BY ts DESC LIMIT ?", (n,)).fetchall()
        out = []
        for r in rows:
            try:
                out.append(json.loads(r["scores"]))
            except Exception:
                pass
        return out

    def save_perf(self, entry: dict) -> None:
        """Save performance history entry."""
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT INTO perf_history VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    uid("ph"),
                    entry.get("ts"),
                    entry.get("latency_ms"),
                    entry.get("type"),
                    entry.get("complexity"),
                    entry.get("exec_mode"),
                    entry.get("tokens_est"),
                    entry.get("via"),
                    1 if entry.get("ok") else 0,
                    entry.get("text_len"),
                ),
            )

    def perf_history(self, n: int = 10) -> list[dict]:
        """Get last N performance history entries."""
        with self._conn() as c:
            rows = c.execute("SELECT * FROM perf_history ORDER BY ts DESC LIMIT ?", (n,)).fetchall()
        return [dict(r) for r in rows]

    def perf_stats(self) -> dict:
        """Get performance statistics."""
        with self._conn() as c:
            row = c.execute(
                "SELECT COUNT(*) n, AVG(latency_ms) avg_ms, MIN(latency_ms) min_ms, MAX(latency_ms) max_ms FROM perf_history"
            ).fetchone()
        if not row or row["n"] == 0:
            return {"n": 0, "avg_ms": None, "min_ms": None, "max_ms": None}
        return {
            "n": int(row["n"]),
            "avg_ms": round(row["avg_ms"], 1) if row["avg_ms"] else None,
            "min_ms": round(row["min_ms"], 1) if row["min_ms"] else None,
            "max_ms": round(row["max_ms"], 1) if row["max_ms"] else None,
        }


store = Store()
