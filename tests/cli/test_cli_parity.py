"""Expanded CLI parity tests modeled after Uvicorn's Click surface."""

from __future__ import annotations

import ssl

from click.testing import CliRunner

from palfrey.cli import main
from palfrey.config import PalfreyConfig
from palfrey.importer import AppImportError


def _capture_config(monkeypatch) -> tuple[list[PalfreyConfig], CliRunner]:
    captured: list[PalfreyConfig] = []

    def fake_run(config: PalfreyConfig) -> None:
        captured.append(config)

    monkeypatch.setattr("palfrey.cli.run", fake_run)
    return captured, CliRunner()


def test_cli_reads_app_from_environment(monkeypatch) -> None:
    captured, runner = _capture_config(monkeypatch)
    result = runner.invoke(main, env={"PALFREY_APP": "tests.fixtures.apps:http_app"})
    assert result.exit_code == 0
    assert captured[0].app == "tests.fixtures.apps:http_app"


def test_cli_reads_app_from_uvicorn_environment(monkeypatch) -> None:
    captured, runner = _capture_config(monkeypatch)
    result = runner.invoke(main, env={"UVICORN_APP": "tests.fixtures.apps:http_app"})
    assert result.exit_code == 0
    assert captured[0].app == "tests.fixtures.apps:http_app"


def test_cli_argument_overrides_environment_app(monkeypatch) -> None:
    captured, runner = _capture_config(monkeypatch)
    result = runner.invoke(
        main,
        ["tests.fixtures.apps:websocket_app"],
        env={"PALFREY_APP": "tests.fixtures.apps:http_app"},
    )
    assert result.exit_code == 0
    assert captured[0].app == "tests.fixtures.apps:websocket_app"


def test_cli_forwards_reload_dirs(monkeypatch, tmp_path) -> None:
    captured, runner = _capture_config(monkeypatch)
    first = tmp_path / "one"
    second = tmp_path / "two"
    first.mkdir()
    second.mkdir()
    result = runner.invoke(
        main,
        [
            "tests.fixtures.apps:http_app",
            "--reload",
            "--reload-dir",
            str(first),
            "--reload-dir",
            str(second),
        ],
    )
    assert result.exit_code == 0
    assert captured[0].reload_dirs == sorted([str(first), str(second)])


def test_cli_forwards_reload_include_patterns(monkeypatch) -> None:
    captured, runner = _capture_config(monkeypatch)
    result = runner.invoke(
        main,
        [
            "tests.fixtures.apps:http_app",
            "--reload-include",
            "*.py",
            "--reload-include",
            "*.yaml",
        ],
    )
    assert result.exit_code == 0
    assert sorted(captured[0].reload_includes) == ["*.py", "*.yaml"]


def test_cli_forwards_reload_exclude_patterns(monkeypatch) -> None:
    captured, runner = _capture_config(monkeypatch)
    result = runner.invoke(
        main,
        [
            "tests.fixtures.apps:http_app",
            "--reload-exclude",
            ".venv/*",
            "--reload-exclude",
            "*.pyc",
        ],
    )
    assert result.exit_code == 0
    assert sorted(captured[0].reload_excludes) == ["*.pyc", ".venv/*"]


def test_cli_uses_uvicorn_compatible_ssl_defaults(monkeypatch) -> None:
    captured, runner = _capture_config(monkeypatch)
    result = runner.invoke(main, ["tests.fixtures.apps:http_app"])
    assert result.exit_code == 0
    assert captured[0].ssl_version == int(ssl.PROTOCOL_TLS_SERVER)
    assert captured[0].ssl_cert_reqs == int(ssl.CERT_NONE)


def test_cli_allows_ssl_integer_overrides(monkeypatch) -> None:
    captured, runner = _capture_config(monkeypatch)
    result = runner.invoke(
        main,
        [
            "tests.fixtures.apps:http_app",
            "--ssl-version",
            "17",
            "--ssl-cert-reqs",
            "2",
        ],
    )
    assert result.exit_code == 0
    assert captured[0].ssl_version == 17
    assert captured[0].ssl_cert_reqs == 2


def test_cli_forwards_boolean_toggles(monkeypatch) -> None:
    captured, runner = _capture_config(monkeypatch)
    result = runner.invoke(
        main,
        [
            "tests.fixtures.apps:http_app",
            "--no-access-log",
            "--no-proxy-headers",
            "--no-server-header",
            "--no-date-header",
        ],
    )
    assert result.exit_code == 0
    config = captured[0]
    assert config.access_log is False
    assert config.proxy_headers is False
    assert config.server_header is False
    assert config.date_header is False


def test_cli_forwards_use_colors_true(monkeypatch) -> None:
    captured, runner = _capture_config(monkeypatch)
    result = runner.invoke(main, ["tests.fixtures.apps:http_app", "--use-colors"])
    assert result.exit_code == 0
    assert captured[0].use_colors is True


def test_cli_forwards_ws_per_message_deflate_false(monkeypatch) -> None:
    captured, runner = _capture_config(monkeypatch)
    result = runner.invoke(
        main,
        [
            "tests.fixtures.apps:http_app",
            "--ws-per-message-deflate",
            "false",
        ],
    )
    assert result.exit_code == 0
    assert captured[0].ws_per_message_deflate is False


def test_cli_forwards_concurrency_and_request_limits(monkeypatch) -> None:
    captured, runner = _capture_config(monkeypatch)
    result = runner.invoke(
        main,
        [
            "tests.fixtures.apps:http_app",
            "--limit-concurrency",
            "11",
            "--limit-max-requests",
            "99",
            "--limit-max-requests-jitter",
            "5",
        ],
    )
    assert result.exit_code == 0
    config = captured[0]
    assert config.limit_concurrency == 11
    assert config.limit_max_requests == 99
    assert config.limit_max_requests_jitter == 5


def test_cli_forwards_timeout_options(monkeypatch) -> None:
    captured, runner = _capture_config(monkeypatch)
    result = runner.invoke(
        main,
        [
            "tests.fixtures.apps:http_app",
            "--timeout-keep-alive",
            "15",
            "--timeout-graceful-shutdown",
            "6",
            "--timeout-worker-healthcheck",
            "8",
        ],
    )
    assert result.exit_code == 0
    config = captured[0]
    assert config.timeout_keep_alive == 15
    assert config.timeout_graceful_shutdown == 6
    assert config.timeout_worker_healthcheck == 8


def test_cli_forwards_app_dir(monkeypatch, tmp_path) -> None:
    captured, runner = _capture_config(monkeypatch)
    result = runner.invoke(main, ["tests.fixtures.apps:http_app", "--app-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert captured[0].app_dir == str(tmp_path.resolve())


def test_cli_forwards_header_values(monkeypatch) -> None:
    captured, runner = _capture_config(monkeypatch)
    result = runner.invoke(
        main,
        [
            "tests.fixtures.apps:http_app",
            "--header",
            "x-a: one",
            "--header",
            "x-b: two",
        ],
    )
    assert result.exit_code == 0
    assert captured[0].headers == ["x-a: one", "x-b: two"]


def test_cli_returns_clean_error_for_import_failures(monkeypatch) -> None:
    def fake_run(config: PalfreyConfig) -> None:
        raise AppImportError('Could not import module "bad.module".')

    monkeypatch.setattr("palfrey.cli.run", fake_run)
    runner = CliRunner()
    result = runner.invoke(main, ["bad.module:app"])
    assert result.exit_code == 1
    assert 'Error: Could not import module "bad.module".' in result.output
    assert "Traceback" not in result.output


def test_cli_returns_clean_error_for_runtime_failures(monkeypatch) -> None:
    def fake_run(config: PalfreyConfig) -> None:
        raise RuntimeError("Reload mode requires the application to be an import string.")

    monkeypatch.setattr("palfrey.cli.run", fake_run)
    runner = CliRunner()
    result = runner.invoke(main, ["tests.fixtures.apps:http_app"])
    assert result.exit_code == 1
    assert "Error: Reload mode requires the application to be an import string." in result.output
    assert "Traceback" not in result.output
