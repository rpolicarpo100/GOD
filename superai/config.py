from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
CFG_PATH = ROOT / "config.yaml"


def load_dotenv(path: Path | None = None) -> int:
    """Load KEY=VAL from .env without overriding a real process env. Never logs values."""
    p = path or (ROOT / ".env")
    n = 0
    if not p.is_file():
        return 0
    for raw in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if not k or k in os.environ:
            continue
        os.environ[k] = v
        n += 1
    return n


load_dotenv()

_DEFAULT = {
    "mode": "auto",
    "budgets": {"task": 8000, "session": 50000, "daily": 200000, "project": 2000000, "agent": 40000},
    "governor": {
        "strict": True,
        "fs_root": "/home/user",
        "python_timeout_s": 8,
        "deny_names": [".env", ".netrc", "credentials", "id_rsa", ".git-credentials"],
    },
    "thresholds": {"accept": 70, "max_retries": 3},
}


def load_file() -> dict:
    if CFG_PATH.exists():
        raw = yaml.safe_load(CFG_PATH.read_text()) or {}
        cfg = deepcopy(_DEFAULT)
        for k, v in raw.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
        return cfg
    return deepcopy(_DEFAULT)


class Config:
    def __init__(self) -> None:
        self._cfg = load_file()

    @property
    def data(self) -> dict:
        return self._cfg

    def get(self, *keys, default=None):
        cur = self._cfg
        for k in keys:
            if not isinstance(cur, dict) or k not in cur:
                return default
            cur = cur[k]
        return cur

    def patch(self, patch: dict) -> dict:
        if "mode" in patch:
            if patch["mode"] in ("auto", "token_saver", "conservative", "offline", "normal"):
                self._cfg["mode"] = patch["mode"]
        if "budgets" in patch and isinstance(patch["budgets"], dict):
            for k, v in patch["budgets"].items():
                if k in self._cfg["budgets"]:
                    self._cfg["budgets"][k] = int(v)
        if "governor" in patch and isinstance(patch["governor"], dict):
            g = patch["governor"]
            if "strict" in g:
                self._cfg["governor"]["strict"] = bool(g["strict"])
            if "python_timeout_s" in g:
                self._cfg["governor"]["python_timeout_s"] = int(g["python_timeout_s"])
        if "evolution_policy" in patch and isinstance(patch["evolution_policy"], dict):
            self._cfg.setdefault("evolution_policy", {})
            self._cfg["evolution_policy"].update(patch["evolution_policy"])
        if "feature_flags" in patch and isinstance(patch["feature_flags"], dict):
            self._cfg.setdefault("feature_flags", {})
            self._cfg["feature_flags"].update(patch["feature_flags"])
        if "feature_flags_meta" in patch and isinstance(patch["feature_flags_meta"], dict):
            self._cfg.setdefault("feature_flags_meta", {})
            self._cfg["feature_flags_meta"].update(patch["feature_flags_meta"])
        self._save()
        return deepcopy(self._cfg)

    def _save(self) -> None:
        try:
            CFG_PATH.write_text(yaml.safe_dump(self._cfg, allow_unicode=True, default_flow_style=False), encoding="utf-8")
        except Exception:
            pass


cfg = Config()
