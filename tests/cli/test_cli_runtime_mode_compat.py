from __future__ import annotations

from click.testing import CliRunner

from palfrey.cli import main
from palfrey.config import PalfreyConfig


def _capture_config(monkeypatch) -> tuple[list[PalfreyConfig], CliRunner]:
    captured: list[PalfreyConfig] = []

    def fake_run(config: PalfreyConfig) -> None:
        captured.append(config)

    monkeypatch.setattr("palfrey.cli.run", fake_run)
    return captured, CliRunner()


def test_cli_accepts_custom_loop_import_string(monkeypatch) -> None:
    captured, runner = _capture_config(monkeypatch)
    result = runner.invoke(
        main,
        [
            "tests.fixtures.apps:http_app",
            "--loop",
            "tests.loops.custom_loop_factory:setup_loop",
        ],
    )
    assert result.exit_code == 0
    assert captured[0].loop == "tests.loops.custom_loop_factory:setup_loop"


def test_cli_rejects_invalid_http_mode_with_clear_error() -> None:
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "tests.fixtures.apps:http_app",
            "--http",
            "invalid-http",
        ],
    )
    assert result.exit_code == 1
    assert "Unsupported HTTP mode" in result.output


def test_cli_rejects_invalid_loop_mode_with_clear_error() -> None:
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "tests.fixtures.apps:http_app",
            "--loop",
            "invalid-loop",
        ],
    )
    assert result.exit_code == 1
    assert "Unsupported loop mode" in result.output


def test_cli_accepts_http2_and_http3_modes(monkeypatch) -> None:
    captured, runner = _capture_config(monkeypatch)

    result_h2 = runner.invoke(
        main,
        [
            "tests.fixtures.apps:http_app",
            "--http",
            "h2",
        ],
    )
    assert result_h2.exit_code == 0
    assert captured[-1].http == "h2"

    result_h3 = runner.invoke(
        main,
        [
            "tests.fixtures.apps:http_app",
            "--http",
            "h3",
        ],
    )
    assert result_h3.exit_code == 0
    assert captured[-1].http == "h3"
