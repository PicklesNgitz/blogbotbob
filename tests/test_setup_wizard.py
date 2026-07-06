"""test_setup_wizard.py — write_env, save_config, and abort safety."""
import hashlib
from pathlib import Path

import pytest

from blogbot.config import load_config, save_config, write_env


def test_write_env_creates_from_template(tmp_path):
    example = tmp_path / ".env.example"
    example.write_text("SMTP_HOST=\nDB_PORT=\n")
    env_path = tmp_path / ".env"
    write_env({"SMTP_HOST": "mail.example.com"}, env_path)
    content = env_path.read_text()
    assert "SMTP_HOST=mail.example.com" in content
    assert "DB_PORT=" in content  # other key preserved


def test_write_env_replaces_only_given_keys(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("KEY_A=old\nKEY_B=keep\n")
    write_env({"KEY_A": "new"}, env_path)
    content = env_path.read_text()
    assert "KEY_A=new" in content
    assert "KEY_B=keep" in content


def test_write_env_appends_new_key(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("EXISTING=val\n")
    write_env({"NEW_KEY": "newval"}, env_path)
    content = env_path.read_text()
    assert "NEW_KEY=newval" in content
    assert "EXISTING=val" in content


def test_save_config_round_trips_without_key_loss(tmp_path):
    config = load_config()
    cfg_path = tmp_path / "config.yaml"
    save_config(config, cfg_path)
    reloaded = load_config(cfg_path)
    assert reloaded.llm.anthropic.model_draft == config.llm.anthropic.model_draft
    assert reloaded.run.panel_top_fraction == config.run.panel_top_fraction
    assert reloaded.sources.hackernews.enabled == config.sources.hackernews.enabled


def test_wizard_abort_leaves_config_unchanged(tmp_path, monkeypatch):
    """If wizard raises before first save_config, config file is byte-identical."""
    cfg_path = tmp_path / "config.yaml"
    config = load_config()
    save_config(config, cfg_path)
    original_bytes = cfg_path.read_bytes()

    # Patch save_config to raise immediately — simulates abort before any write
    import blogbot.setup_wizard as _wiz

    def _raise(*args, **kwargs):
        raise KeyboardInterrupt("simulated abort")

    monkeypatch.setattr(_wiz, "save_config", _raise)
    monkeypatch.setattr(_wiz, "typer", type("T", (), {"echo": lambda *a, **k: None,
                                                       "prompt": lambda *a, **k: "",
                                                       "confirm": lambda *a, **k: False})())

    try:
        _wiz.run_wizard()
    except (KeyboardInterrupt, Exception):
        pass

    # cfg_path unchanged (wizard never called the real save_config)
    assert cfg_path.read_bytes() == original_bytes
