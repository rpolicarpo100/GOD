from __future__ import annotations

from pathlib import Path

from .config import DATA, cfg


# Resource modes
RESOURCE_MODES = {
    "ECO": {
        "description": "Low resource usage — avoid unnecessary LLM, prioritize cache/tools",
        "max_concurrent": 1,
        "allow_heavy_llm": False,
        "prefer_cache": True,
        "prefer_tools": True,
        "gpu_minimal": True,
    },
    "NORMAL": {
        "description": "Balanced usage — standard operation",
        "max_concurrent": 2,
        "allow_heavy_llm": True,
        "prefer_cache": True,
        "prefer_tools": False,
        "gpu_minimal": False,
    },
    "PERFORMANCE": {
        "description": "High resource usage — allow heavy tasks when needed",
        "max_concurrent": 4,
        "allow_heavy_llm": True,
        "prefer_cache": False,
        "prefer_tools": False,
        "gpu_minimal": False,
    },
}


class Governor:
    """Limits. Agents cannot disable this object via chat."""

    FORBIDDEN_CHAT = {
        "alterar o governor",
        "desligar o governor",
        "remover limites",
        "instalar em produção",
    }

    def strict(self) -> bool:
        return bool(cfg.get("governor", "strict", default=True))

    def fs_root(self) -> Path:
        return Path(cfg.get("governor", "fs_root", default="/home/user")).resolve()

    def python_timeout(self) -> int:
        return int(cfg.get("governor", "python_timeout_s", default=8))

    def deny_names(self) -> list[str]:
        return list(cfg.get("governor", "deny_names", default=[".env"]))

    def resource_mode(self) -> str:
        """Get current resource mode (ECO/NORMAL/PERFORMANCE)."""
        mode = cfg.get("governor", "resource_mode", default="NORMAL")
        if mode not in RESOURCE_MODES:
            return "NORMAL"
        return mode

    def set_resource_mode(self, mode: str) -> bool:
        """Set resource mode. Returns True if valid."""
        if mode not in RESOURCE_MODES:
            return False
        cfg.set("governor", "resource_mode", mode)
        return True

    def resource_config(self) -> dict:
        """Get current resource mode configuration."""
        mode = self.resource_mode()
        return {
            "mode": mode,
            **RESOURCE_MODES[mode],
        }

    def allow_path(self, path: Path) -> tuple[bool, str]:
        try:
            p = path.expanduser().resolve()
        except Exception as e:
            return False, f"path error: {e}"
        root = self.fs_root()
        if root not in p.parents and p != root:
            return False, f"fora de {root}"
        name = p.name.lower()
        for d in self.deny_names():
            if d.lower() in name or d.lower() in str(p).lower():
                return False, f"governor bloqueia {d}"
        return True, "ok"

    def allow_write(self, path: Path) -> tuple[bool, str]:
        """Só data/projects. Sem .py (não é auto-modificação do núcleo)."""
        ok, why = self.allow_path(path)
        if not ok:
            return ok, why
        p = path.expanduser().resolve()
        root = (DATA / "projects").resolve()
        root.mkdir(parents=True, exist_ok=True)
        if p == root:
            return False, "não escrever na raiz de projects"
        if root not in p.parents:
            return False, "write só em data/projects"
        allowed = {".html", ".css", ".js", ".svg", ".json", ".md", ".txt", ".csv"}
        if p.suffix.lower() not in allowed:
            return False, f"extensão {p.suffix or '(vazia)'} não permitida"
        return True, "ok"

    def allow_python(self, code: str) -> tuple[bool, str]:
        banned = ("socket", "subprocess", "ctypes", "multiprocessing", "importlib", "os.system", "shutil.rmtree", "eval(", "exec(")
        low = code.lower()
        for b in banned:
            if b.lower() in low:
                return False, f"governor bloqueia {b}"
        if len(code) > 8000:
            return False, "código demasiado grande"
        return True, "ok"

    def allow_git(self, args: list[str]) -> tuple[bool, str]:
        if not args:
            return False, "git sem args"
        cmd = args[0]
        if cmd in ("push", "reset", "clean", "rebase", "filter-branch"):
            return False, f"git {cmd} exige aprovação humana"
        if cmd in ("status", "log", "diff", "show", "rev-parse", "branch"):
            return True, "ok"
        return False, f"git {cmd} não está na allowlist desta fase"


gov = Governor()
