"""CLI surface tests."""

from __future__ import annotations

from click.testing import CliRunner

from palfrey.cli import main


def test_cli_help_contains_expected_options() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])

    assert result.exit_code == 0
    assert "--host" in result.output
    assert "--port" in result.output
    assert "--reload" in result.output
    assert "--workers" in result.output
