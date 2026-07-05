"""test_config.py — config loading and secrets."""
import pytest
import yaml

from blogbot.config import MissingSecretError, load_config, require_secret, save_config


def test_defaults_load_minimal_yaml(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("run:\n  max_publishes_per_run: 3\n")
    config = load_config(cfg_file)
    assert config.run.max_publishes_per_run == 3
    assert config.llm.anthropic.model_draft == "claude-sonnet-4-6"


def test_unknown_key_errors(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("run:\n  unknown_key: 99\n")
    with pytest.raises(Exception):
        load_config(cfg_file)


def test_require_secret_raises_naming_key():
    with pytest.raises(MissingSecretError, match="MY_KEY"):
        require_secret("MY_KEY", "")


def test_require_secret_passes_when_set():
    assert require_secret("MY_KEY", "abc") == "abc"


def test_save_config_round_trips(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    config = load_config()
    config.run.max_publishes_per_run = 5
    save_config(config, cfg_file)
    reloaded = load_config(cfg_file)
    assert reloaded.run.max_publishes_per_run == 5
    assert reloaded.llm.anthropic.model_draft == "claude-sonnet-4-6"
