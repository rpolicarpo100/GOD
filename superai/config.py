from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
CFG_PATH = ROOT / "config.yaml"

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
        return deepcopy(self._cfg)


cfg = Config()
