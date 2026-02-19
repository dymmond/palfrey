from __future__ import annotations

import os
import types
from pathlib import Path

from palfrey.env import load_env_file


def test_load_env_file_uses_dotenv_when_available(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("FOO=from-file\n", encoding="utf-8")

    calls: list[Path] = []

    def fake_load_dotenv(*, dotenv_path: Path, override: bool) -> None:
        calls.append(dotenv_path)
        if "FOO" not in os.environ:
            os.environ["FOO"] = "from-dotenv"

    fake_module = types.SimpleNamespace(load_dotenv=fake_load_dotenv)
    monkeypatch.setitem(__import__("sys").modules, "dotenv", fake_module)
    monkeypatch.delenv("FOO", raising=False)

    load_env_file(str(env_file))

    assert calls == [env_file]
    assert os.environ["FOO"] == "from-dotenv"
