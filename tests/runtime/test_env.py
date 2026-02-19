from __future__ import annotations

import os
from pathlib import Path

from palfrey.env import load_env_file


def test_load_env_file_sets_missing_variables(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("ONE=1\nTWO=2\n", encoding="utf-8")

    monkeypatch.delenv("ONE", raising=False)
    monkeypatch.delenv("TWO", raising=False)

    load_env_file(str(env_file))

    assert os.environ["ONE"] == "1"
    assert os.environ["TWO"] == "2"


def test_load_env_file_does_not_override_existing(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("THREE=from-file\n", encoding="utf-8")

    monkeypatch.setenv("THREE", "existing")

    load_env_file(str(env_file))

    assert os.environ["THREE"] == "existing"


def test_load_env_file_ignores_missing_path(monkeypatch) -> None:
    monkeypatch.delenv("MISSING", raising=False)
    load_env_file("/definitely/missing/.env")
    assert "MISSING" not in os.environ


def test_load_env_file_noop_when_path_is_none(monkeypatch) -> None:
    monkeypatch.delenv("NOT_SET", raising=False)
    load_env_file(None)
    assert "NOT_SET" not in os.environ
