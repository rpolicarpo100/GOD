from __future__ import annotations

import os
import threading
from copy import deepcopy
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
CFG_PATH = ROOT / "config.yaml"
STATE_PATH = DATA / "state.yaml"

# Keys that are runtime state (saved to data/state.yaml, NOT config.yaml)
_STATE_KEYS = {"feature_flags", "feature_flags_meta", "mode", "evolution_policy"}


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


def _load_yaml(path: Path) -> dict:
    """Load a YAML file, return empty dict on failure."""
    try:
        if path.exists():
            return yaml.safe_load(path.read_text()) or {}
    except Exception:
        pass
    return {}


def _save_yaml(path: Path, data: dict) -> None:
    """Save a YAML file atomically."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(data, allow_unicode=True, default_flow_style=False), encoding="utf-8")
    except Exception:
        pass


def load_file() -> dict:
    """Load config.yaml (static) merged with state.yaml (runtime)."""
    cfg = deepcopy(_DEFAULT)
    # Load static config
    raw = _load_yaml(CFG_PATH)
    for k, v in raw.items():
        if isinstance(v, dict) and isinstance(cfg.get(k), dict):
            cfg[k].update(v)
        else:
            cfg[k] = v
    # Load runtime state (overrides config.yaml values)
    state = _load_yaml(STATE_PATH)
    for k, v in state.items():
        cfg[k] = v
    return cfg


class Config:
    def __init__(self) -> None:
        self._cfg = load_file()
        self._lock = threading.Lock()

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

    def set(self, *keys_and_value) -> None:
        """Set a nested value: cfg.set('governor', 'resource_mode', 'ECO')"""
        if len(keys_and_value) < 2:
            return
        *keys, value = keys_and_value
        with self._lock:
            cur = self._cfg
            for k in keys[:-1]:
                if k not in cur or not isinstance(cur[k], dict):
                    cur[k] = {}
                cur = cur[k]
            cur[keys[-1]] = value
            self._save()

    def patch(self, patch: dict) -> dict:
        with self._lock:
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
        """Save config: static keys to config.yaml, runtime keys to state.yaml."""
        static = {k: v for k, v in self._cfg.items() if k not in _STATE_KEYS}
        state = {k: v for k, v in self._cfg.items() if k in _STATE_KEYS}
        _save_yaml(CFG_PATH, static)
        if state:
            _save_yaml(STATE_PATH, state)


cfg = Config()
