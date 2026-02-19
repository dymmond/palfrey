from __future__ import annotations

from click.testing import CliRunner

from palfrey.cli import main
from palfrey.config import PalfreyConfig


def test_cli_help_lists_parity_options() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])

    assert result.exit_code == 0
    output = result.output

    for option in (
        "--host",
        "--port",
        "--reload",
        "--workers",
        "--proxy-headers",
        "--forwarded-allow-ips",
        "--ssl-keyfile",
        "--ssl-certfile",
        "--ws-max-size",
        "--limit-max-requests-jitter",
        "--h11-max-incomplete-event-size",
        "--factory",
    ):
        assert option in output


def test_cli_requires_app_argument() -> None:
    runner = CliRunner()
    result = runner.invoke(main, [])
    assert result.exit_code != 0
    assert "Missing argument 'APP'" in result.output


def test_cli_version_option() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    output = result.output.lower()
    assert "running palfrey" in output
    assert "with" in output
    assert "on" in output


def test_cli_accepts_websockets_sansio_and_jitter(monkeypatch) -> None:
    captured: list[PalfreyConfig] = []

    def fake_run(config: PalfreyConfig) -> None:
        captured.append(config)

    monkeypatch.setattr("palfrey.cli.run", fake_run)

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "tests.fixtures.apps:http_app",
            "--ws",
            "websockets-sansio",
            "--limit-max-requests-jitter",
            "11",
        ],
    )

    assert result.exit_code == 0
    assert len(captured) == 1
    assert captured[0].ws == "websockets-sansio"
    assert captured[0].limit_max_requests_jitter == 11


def test_cli_rejects_invalid_lifespan_choice() -> None:
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "tests.fixtures.apps:http_app",
            "--lifespan",
            "sometimes",
        ],
    )
    assert result.exit_code == 2
    assert "Invalid value for '--lifespan'" in result.output


def test_cli_rejects_invalid_log_level_choice() -> None:
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "tests.fixtures.apps:http_app",
            "--log-level",
            "verbose",
        ],
    )
    assert result.exit_code == 2
    assert "Invalid value for '--log-level'" in result.output
