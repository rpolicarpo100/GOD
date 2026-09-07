#!/usr/bin/env python3
"""GOD — Startup Diagnostic Script

Run this to identify why GOD won't start, load, or respond.
Usage: python diagnose.py
"""
from __future__ import annotations

import json
import os
import socket
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"

# Colors
G = "\033[92m"  # Green
Y = "\033[93m"  # Yellow
R = "\033[91m"  # Red
B = "\033[94m"  # Blue
W = "\033[0m"   # Reset

def ok(msg): print(f"  {G}✓{W} {msg}")
def warn(msg): print(f"  {Y}⚠{W} {msg}")
def fail(msg): print(f"  {R}✗{W} {msg}")
def info(msg): print(f"  {B}ℹ{W} {msg}")
def header(msg): print(f"\n{B}{'═'*60}{W}\n  {msg}\n{B}{'─'*60}{W}")

def main():
    print(f"\n{B}╔══════════════════════════════════════════════════════════╗{W}")
    print(f"{B}║           GOD — Startup Diagnostic                      ║{W}")
    print(f"{B}╚══════════════════════════════════════════════════════════╝{W}")

    issues = []

    # 1. Python version
    header("1. Python Environment")
    v = sys.version_info
    if v >= (3, 10):
        ok(f"Python {v.major}.{v.minor}.{v.micro}")
    else:
        fail(f"Python {v.major}.{v.minor}.{v.micro} — need 3.10+")
        issues.append("Python version too old")

    # 2. Virtual environment
    if sys.prefix != sys.base_prefix:
        ok(f"Virtual environment: {sys.prefix}")
    else:
        warn("Not in a virtual environment (recommended: .venv)")

    # 3. Core dependencies
    header("2. Dependencies")
    deps = {
        "fastapi": "fastapi",
        "uvicorn": "uvicorn",
        "httpx": "httpx",
        "pydantic": "pydantic",
        "sqlite3": "sqlite3",
        "qdrant_client": "qdrant_client",
        "numpy": "numpy",
        "tiktoken": "tiktoken",
        "yaml": "yaml",
        "lxml": "lxml",
    }
    missing = []
    for name, module in deps.items():
        try:
            __import__(module)
            ok(f"{name}")
        except ImportError:
            fail(f"{name} — MISSING")
            missing.append(name)
    if missing:
        issues.append(f"Missing dependencies: {', '.join(missing)}")
        info(f"Fix: pip install {' '.join(missing)}")

    # 4. Port availability
    header("3. Port Availability")
    ports_to_check = [8000, 8080, 3000, 9000, 5000]
    available_port = None
    for port in ports_to_check:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(("0.0.0.0", port))
            s.close()
            ok(f"Port {port}: available")
            if not available_port:
                available_port = port
        except OSError:
            warn(f"Port {port}: BLOCKED")
    if not available_port:
        fail("No ports available!")
        issues.append("All ports blocked")
    elif available_port != 8000:
        info(f"Will use port {available_port} instead of 8000")

    # 5. Data directories
    header("4. Data Directories")
    required_dirs = ["data", "data/auth", "data/gods", "data/qdrant", "data/projects", "logs", "backups"]
    for d in required_dirs:
        p = ROOT / d
        if p.exists():
            ok(f"{d}/")
        else:
            warn(f"{d}/ — missing, will be created")
            p.mkdir(parents=True, exist_ok=True)

    # 6. SQLite database
    header("5. SQLite Database")
    db_path = DATA / "spine.db"
    if db_path.exists():
        size_mb = db_path.stat().st_size / (1024 * 1024)
        ok(f"spine.db: {size_mb:.1f} MB")
        try:
            import sqlite3
            conn = sqlite3.connect(str(db_path), timeout=5)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            # Check integrity
            result = conn.execute("PRAGMA integrity_check").fetchone()
            if result[0] == "ok":
                ok("SQLite integrity: OK")
            else:
                fail(f"SQLite integrity: {result[0]}")
                issues.append("SQLite database corrupted")
            conn.close()
        except Exception as e:
            fail(f"SQLite error: {e}")
            issues.append(f"SQLite error: {e}")
    else:
        warn("spine.db not found — will be created on first start")

    # 7. Qdrant vector store
    header("6. Vector Store (Qdrant)")
    qdrant_path = DATA / "qdrant"
    if qdrant_path.exists():
        ok(f"Qdrant data: {qdrant_path}")
        try:
            from qdrant_client import QdrantClient
            client = QdrantClient(path=str(qdrant_path))
            collections = client.get_collections().collections
            for col in collections:
                count = client.get_collection(col.name).points_count
                ok(f"  Collection '{col.name}': {count} points")
            client.close()
        except Exception as e:
            warn(f"Qdrant error: {e}")
            info("Fix: rm -rf data/qdrant && restart (will rebuild)")
    else:
        warn("Qdrant data not found — will be created on first start")

    # 8. API Keys
    header("7. API Keys")
    env_path = ROOT / ".env"
    if env_path.exists():
        ok(".env file exists")
        # Load and check keys
        try:
            from dotenv import load_dotenv
            load_dotenv(env_path)
        except ImportError:
            # Manual parse
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip())

        key_names = [
            ("GROQ_API_KEY", "Groq (free, fast)"),
            ("GOOGLE_API_KEY", "Google Gemini"),
            ("ANTHROPIC_API_KEY", "Anthropic Claude"),
            ("OPENROUTER_API_KEY", "OpenRouter"),
            ("CEREBRAS_API_KEY", "Cerebras (free, fast)"),
            ("NVIDIA_API_KEY", "NVIDIA"),
            ("MISTRAL_API_KEY", "Mistral"),
            ("SAMBANOVA_API_KEY", "SambaNova"),
        ]
        configured = 0
        for key, name in key_names:
            val = os.environ.get(key, "").strip()
            if val:
                ok(f"{name}: configured ({val[:8]}...)")
                configured += 1
            else:
                info(f"{name}: not set")
        if configured == 0:
            warn("No API keys configured — GOD will run in OFFLINE mode")
            info("Fix: ./god.sh config")
        else:
            ok(f"{configured} API key(s) configured")
    else:
        warn(".env file not found — no API keys")
        info("Fix: ./god.sh config")

    # 9. Auth system
    header("8. Authentication")
    users_path = DATA / "auth" / "users.json"
    if users_path.exists():
        try:
            users = json.loads(users_path.read_text())
            ok(f"Users file: {len(users)} user(s)")
            has_owner = any(u.get("role") == "OWNER" for u in users.values())
            if has_owner:
                ok("Owner account exists")
            else:
                warn("No OWNER account — create via POST /api/auth/setup")
        except Exception as e:
            warn(f"Users file error: {e}")
    else:
        warn("No users file — will be created on first setup")
        info("Create owner: POST /api/auth/setup")

    # 10. Feature flags
    header("9. Feature Flags")
    config_path = DATA / "config.yaml"
    if config_path.exists():
        ok("config.yaml exists")
    else:
        info("config.yaml not found — using defaults")

    # 11. GOD profiles
    header("10. GOD Profiles")
    gods_path = DATA / "gods"
    if gods_path.exists():
        profiles = list(gods_path.glob("*.json"))
        if profiles:
            ok(f"{len(profiles)} profile(s): {', '.join(p.stem for p in profiles)}")
        else:
            warn("No GOD profiles — will be created on boot")
    else:
        warn("gods/ directory missing")

    # 12. Test suite
    header("11. Test Suite")
    test_dir = ROOT / "tests"
    if test_dir.exists():
        test_files = list(test_dir.glob("test_*.py"))
        ok(f"{len(test_files)} test file(s)")
    else:
        warn("tests/ directory not found")

    # Summary
    header("SUMMARY")
    if not issues:
        print(f"\n  {G}✓ All checks passed! GOD should start normally.{W}")
        print(f"\n  Start: python -m uvicorn server:app --host 0.0.0.0 --port {available_port or 8000}")
        print(f"  Or:    ./god.sh start\n")
    else:
        print(f"\n  {R}✗ {len(issues)} issue(s) found:{W}")
        for i, issue in enumerate(issues, 1):
            print(f"    {R}{i}.{W} {issue}")
        print(f"\n  Fix the issues above, then restart GOD.\n")

    return len(issues)

if __name__ == "__main__":
    sys.exit(main())
