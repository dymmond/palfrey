"""CLI surface and validation tests."""

from __future__ import annotations

from click.testing import CliRunner

from palfrey.cli import main


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
    assert "palfrey" in result.output.lower()
