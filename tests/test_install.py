"""GOD — Installation E2E tests.

Tests the installation/startup/repair flow WITHOUT requiring a running server.
Run: pytest tests/test_install.py -v

These tests verify that the installer's checks work correctly.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


class TestProjectStructure:
    """Verify project structure matches what installer expects."""

    def test_server_exists(self):
        assert (ROOT / "server.py").is_file()

    def test_worker_exists(self):
        assert (ROOT / "worker.py").is_file()

    def test_config_yaml(self):
        assert (ROOT / "config.yaml").is_file()

    def test_requirements_txt(self):
        assert (ROOT / "requirements.txt").is_file()

    def test_requirements_lock(self):
        assert (ROOT / "requirements-lock.txt").is_file()

    def test_requirements_minimal(self):
        assert (ROOT / "requirements-minimal.txt").is_file()

    def test_env_example(self):
        assert (ROOT / ".env.example").is_file()

    def test_env_example_has_keys(self):
        text = (ROOT / ".env.example").read_text()
        assert "GROQ_API_KEY" in text
        assert "GOOGLE_API_KEY" in text

    def test_gitignore_exists(self):
        assert (ROOT / ".gitignore").is_file()

    def test_gitignore_excludes_env(self):
        text = (ROOT / ".gitignore").read_text()
        assert ".env" in text

    def test_gitignore_excludes_data(self):
        text = (ROOT / ".gitignore").read_text()
        assert "data/" in text or "data" in text

    def test_index_html(self):
        assert (ROOT / "index.html").is_file()

    def test_index_html_size(self):
        """UI should be > 1KB (not empty)."""
        size = (ROOT / "index.html").stat().st_size
        assert size > 1000, f"index.html too small: {size} bytes"


class TestSuperaiModules:
    """Verify superai package structure."""

    def test_init_exists(self):
        assert (ROOT / "superai" / "__init__.py").is_file()

    def test_modules_present(self):
        """Core modules should exist."""
        required = [
            "runtime.py", "brain.py", "config.py", "auth.py",
            "health.py", "repair.py", "gods.py", "queue.py",
            "store.py", "tokens.py", "observer.py", "aios.py",
        ]
        for mod in required:
            assert (ROOT / "superai" / mod).is_file(), f"Missing: superai/{mod}"

    def test_module_count(self):
        """Should have ~48 modules."""
        modules = list((ROOT / "superai").glob("*.py"))
        modules = [m for m in modules if m.name != "__init__.py"]
        assert len(modules) >= 40, f"Only {len(modules)} modules"


class TestTests:
    """Verify test structure."""

    def test_core_tests_exist(self):
        assert (ROOT / "tests" / "test_core.py").is_file()

    def test_security_tests_exist(self):
        assert (ROOT / "tests" / "test_security.py").is_file()

    def test_security_p2_tests_exist(self):
        assert (ROOT / "tests" / "test_security_p2.py").is_file()

    def test_e2e_tests_exist(self):
        assert (ROOT / "tests" / "test_e2e.py").is_file()


class TestDataDirs:
    """Verify data directory structure."""

    def test_data_dir(self):
        assert (ROOT / "data").is_dir()

    def test_auth_dir(self):
        assert (ROOT / "data" / "auth").is_dir()

    def test_gods_dir(self):
        assert (ROOT / "data" / "gods").is_dir()

    def test_spine_db(self):
        assert (ROOT / "data" / "spine.db").is_file()

    def test_users_json(self):
        assert (ROOT / "data" / "auth" / "users.json").is_file()


class TestConfig:
    """Verify configuration files."""

    def test_config_yaml_readable(self):
        import yaml
        cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
        assert isinstance(cfg, dict)

    def test_config_has_budgets(self):
        import yaml
        cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
        assert "budgets" in cfg

    def test_config_has_feature_flags(self):
        """Feature flags are loaded from config.yaml or data/state.yaml (merged)."""
        from superai.config import cfg
        flags = cfg.get("feature_flags")
        assert flags is not None, "feature_flags not found in merged config"
        assert isinstance(flags, dict), "feature_flags should be a dict"
        assert len(flags) > 0, "feature_flags should not be empty"


class TestGodProfiles:
    """Verify GOD profiles."""

    def test_master_profile(self):
        master = ROOT / "data" / "gods" / "master.json"
        if master.exists():
            data = json.loads(master.read_text())
            assert data.get("id") == "master"
            assert "name" in data
            assert "capabilities" in data


class TestInstallManifest:
    """Verify installation manifest if present."""

    def test_manifest_readable(self):
        manifest = ROOT / "data" / "install_manifest.json"
        if manifest.exists():
            data = json.loads(manifest.read_text())
            assert "timestamp" in data
            assert "python_version" in data


class TestScripts:
    """Verify scripts exist and are well-formed."""

    def test_god_sh_exists(self):
        assert (ROOT / "god.sh").is_file()

    def test_god_bat_exists(self):
        assert (ROOT / "god.bat").is_file()

    def test_god_installer_bat(self):
        assert (ROOT / "GOD_INSTALLER.bat").is_file()

    def test_god_installer_sh(self):
        assert (ROOT / "god-installer.sh").is_file()

    def test_setup_sh(self):
        assert (ROOT / "setup.sh").is_file()

    def test_setup_bat(self):
        assert (ROOT / "setup.bat").is_file()

    def test_god_sh_has_start(self):
        text = (ROOT / "god.sh").read_text(encoding="utf-8")
        assert "start)" in text

    def test_god_sh_has_stop(self):
        text = (ROOT / "god.sh").read_text(encoding="utf-8")
        assert "stop)" in text

    def test_god_sh_has_backup(self):
        text = (ROOT / "god.sh").read_text(encoding="utf-8")
        assert "backup)" in text

    def test_god_sh_has_doctor(self):
        text = (ROOT / "god.sh").read_text(encoding="utf-8")
        assert "doctor)" in text

    def test_god_sh_has_repair(self):
        text = (ROOT / "god.sh").read_text(encoding="utf-8")
        assert "repair)" in text

    def test_god_sh_has_uninstall(self):
        text = (ROOT / "god.sh").read_text(encoding="utf-8")
        assert "uninstall)" in text

    def test_god_sh_has_update(self):
        text = (ROOT / "god.sh").read_text(encoding="utf-8")
        assert "update)" in text
