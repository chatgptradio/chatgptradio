import pytest
from pathlib import Path
import tempfile
import yaml

from core.config import load_config, AppConfig, CollectorConfig, WebSocketConfig, SQLiteConfig


MINIMAL_YAML = """
collectors:
  - name: openai_status
    module: collectors.openai_status
    interval_s: 30
websocket:
  port: 8765
  fps: 4
sqlite:
  path: streams/state.db
  snapshot_retention_days: 30
  history_retention_days: 90
"""


def test_load_config_returns_app_config(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(MINIMAL_YAML)
    cfg = load_config(cfg_file)
    assert isinstance(cfg, AppConfig)


def test_collectors_parsed(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(MINIMAL_YAML)
    cfg = load_config(cfg_file)
    assert len(cfg.collectors) == 1
    c = cfg.collectors[0]
    assert isinstance(c, CollectorConfig)
    assert c.name == "openai_status"
    assert c.module == "collectors.openai_status"
    assert c.interval_s == 30


def test_websocket_config(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(MINIMAL_YAML)
    cfg = load_config(cfg_file)
    assert isinstance(cfg.websocket, WebSocketConfig)
    assert cfg.websocket.port == 8765
    assert cfg.websocket.fps == 4


def test_sqlite_config(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(MINIMAL_YAML)
    cfg = load_config(cfg_file)
    assert isinstance(cfg.sqlite, SQLiteConfig)
    assert cfg.sqlite.path == "streams/state.db"
    assert cfg.sqlite.snapshot_retention_days == 30
    assert cfg.sqlite.history_retention_days == 90


def test_empty_collectors(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("collectors: []\nwebsocket:\n  port: 9000\n  fps: 10\nsqlite:\n  path: x.db\n")
    cfg = load_config(cfg_file)
    assert cfg.collectors == []
    assert cfg.websocket.port == 9000


def test_defaults_when_keys_missing(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("{}")
    cfg = load_config(cfg_file)
    assert cfg.websocket.port == 8765
    assert cfg.sqlite.path == "streams/state.db"
