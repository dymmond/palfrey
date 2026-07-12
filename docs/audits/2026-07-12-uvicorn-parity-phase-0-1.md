# Uvicorn Parity Campaign Phase 0/1 Handoff

Date: 2026-07-12

Scope: Phase 0 and Phase 1 only. No production code was changed. No version bump was made. Release notes were not updated.

Decision: BLOCKED - INSUFFICIENT EVIDENCE

Reason: this phase establishes ground truth and the reference inventory. It does not prove Palfrey parity or performance superiority.

## Repository Ground Truth

| Item | Palfrey | Uvicorn reference |
| --- | --- | --- |
| Path | `<palfrey-repo>` | `<uvicorn-reference-repo>` |
| Branch | `codex/uvicorn-parity-phase0` | `main` |
| Commit inspected | `9b7b1161aaf673f8eff61ad8d1be5d4a9e6d0b04` | `7e11cc65f0642c823ef18ea01ff6b23af90aaa9e` |
| Dirty state before audit artifact | No tracked changes; ignored build/cache artifacts present | Untracked `.idea/` only |
| Python observed | `python3 --version`: `Python 3.14.3`; Hatch test env used `Python 3.13.12` | `Python 3.14.3` via `uv run` |
| Python requirement | `>=3.10`; classifiers include 3.10-3.14, CPython, PyPy | `>=3.10`; classifiers include 3.10-3.14, CPython, PyPy |
| Package manager | Hatch (`hatchling`, Hatch env scripts) | uv (`uv.lock`, `tool.uv`) plus Hatch build backend |
| Runtime dependencies | `click`, `h11` | `click`, `h11`, `typing_extensions` on Python <3.11 |
| Optional protocol/runtime deps | `httptools`, `python-dotenv`, `PyYAML`, `uvloop`, `watchfiles`, `websockets`, `h2`, `aioquic` | `httptools`, `python-dotenv`, `PyYAML`, `uvloop`, `watchfiles`, `websockets` |
| Entry points | `palfrey = palfrey.cli:main`; `palfrey-benchmark = benchmarks.run:main` | `uvicorn = uvicorn.main:main` |
| CI/workflows | `.github/workflows/ci.yml`, `codspeed.yml`, `publish.yml` | `.github/workflows/main.yml`, `benchmark.yml`, `publish.yml`, `zizmor.yml` |
| Docs | `docs/en/docs`, generated via `scripts/docs.py` and Zensical | `docs`, built via `scripts/docs` and Zensical |

## Documented Commands

Palfrey commands are Hatch-based:

- Full suite: `hatch run test:test`
- Lint: `hatch run lint`
- Format validation: `hatch run format-check`
- Type check: `hatch run check-types`
- Docs build: `hatch run docs-build`
- Package build: `hatch build`
- Benchmark baseline: `hatch run python -m benchmarks.run --enable-phases`

Uvicorn reference commands:

- Full validation wrapper: `scripts/test`
- The wrapper runs `scripts/check`, `uv run coverage run --debug config -m pytest`, and `scripts/coverage`.
- `scripts/check` runs `./scripts/sync-version`, `uv run ruff format --check --diff uvicorn tests`, `uv run mypy uvicorn tests`, and `uv run ruff check uvicorn tests`.

## Baseline Validation Results

| Project | Command | Result |
| --- | --- | --- |
| Palfrey | `hatch run test:test` | Passed: `726 passed, 15 skipped in 7.29s`; coverage `89.37%`, above `85%` threshold |
| Uvicorn | `scripts/test` | Passed: `958 passed, 14 skipped in 16.65s`; coverage report `100.00%` |

Observed Palfrey skipped areas:

- `tests/integration/test_uvicorn_differential_compat.py`: 11 skipped.
- `tests/server/test_socket_options.py`: 2 skipped.
- `tests/unit/test_acceleration.py`: 2 skipped.

Observed Uvicorn skipped areas:

- WebSocketsSansIO response split behavior: 6 skips.
- Platform/reload behavior: SIGBREAK unsupported and reload tests flaky on Windows/macOS.

## Baseline Quality Results

| Project | Command | Result |
| --- | --- | --- |
| Palfrey | `hatch run lint` | Passed: `All checks passed!` |
| Palfrey | `hatch run format-check` | Passed: `135 files already formatted` |
| Palfrey | `hatch run check-types` | Passed: `All checks passed!` |
| Palfrey | `hatch run docs-build` | Passed: Zensical build finished in `1.30s` |
| Palfrey | `hatch build` | Passed: `dist/palfrey-0.1.4.tar.gz`, `dist/palfrey-0.1.4-py3-none-any.whl` |
| Uvicorn | `scripts/check` through `scripts/test` | Passed: format, mypy, ruff |

## Initial Baseline Benchmark

Command:

```bash
hatch run python -m benchmarks.run --enable-phases
```

Benchmark harness: `benchmarks/run.py`; app target: `benchmarks.apps:app`.

Runner metadata:

- Python: `3.13.12`
- OS: `Darwin`
- CPU: `arm`
- Runner loop metadata: `asyncio`
- Spawned server command uses `--http httptools --loop uvloop --ws websockets --no-access-log`

Single-sample results:

| Scenario | Server | Operations | Duration (s) | Ops/s | Ratio |
| --- | --- | ---: | ---: | ---: | ---: |
| HTTP | Uvicorn | 2,000 | 0.0536 | 37,295.31 | baseline |
| HTTP | Palfrey | 2,000 | 0.0729 | 27,432.74 | 0.736x |
| WebSocket | Uvicorn | 1,000 | 0.0603 | 16,589.40 | baseline |
| WebSocket | Palfrey | 1,000 | 0.0362 | 27,597.75 | 1.664x |

Caveats:

- This is one local run, not a statistically significant result.
- It covers only empty HTTP response and WebSocket echo workloads in the local benchmark app.
- It does not cover startup latency, first request latency, tail latency, CPU/RSS, slow clients, large bodies, large headers, streaming throughput, graceful shutdown duration, or protocol error rates.
- The harness reports runner loop metadata separately from spawned server loop arguments; the final benchmark suite should record effective child-process runtime configuration explicitly.

## Uvicorn Subsystem Inventory

This is the Phase 1 reference inventory. Status values are not assigned here; they belong in the Phase 2 parity matrix.

| ID prefix | Subsystem | Uvicorn implementation evidence | Uvicorn tests/docs evidence | Palfrey comparison owners |
| --- | --- | --- | --- | --- |
| LIF | Server lifecycle | `uvicorn.server.Server`, `ServerState`, `Server.serve`, `startup`, `main_loop`, `on_tick`, `shutdown`, `_wait_tasks_to_complete`, `handle_exit`; `uvicorn._subprocess.get_subprocess` | `tests/test_server.py`, `tests/test_main.py`, `tests/test_subprocess.py`, `tests/supervisors/test_signal.py`, `docs/server-behavior.md` | `palfrey.server.PalfreyServer`, `ServerState`, `palfrey.runtime.run_config`, `tests/server/*`, `tests/runtime/*` |
| ASGI | ASGI interface and scopes | `uvicorn.config.Config.load`, `asgi_version`, ASGI2/ASGI3/WSGI middleware wrapping, HTTP/WebSocket/lifespan scope creation | `tests/test_config.py`, `tests/protocols/test_http.py`, `tests/test_lifespan.py`, `docs/concepts/asgi.md` | `palfrey.config.PalfreyConfig`, `palfrey.adapters`, `palfrey.lifespan.LifespanManager`, `palfrey.protocols.http`, `palfrey.protocols.websocket` |
| HTTP | HTTP/1.1 protocol behavior | `uvicorn.protocols.http.h11_impl.H11Protocol`, `httptools_impl.HttpToolsProtocol`, `RequestResponseCycle`, `flow_control.FlowControl`, `service_unavailable` | `tests/protocols/test_http.py`, `tests/benchmarks/test_http.py`, `docs/server-behavior.md` | `palfrey.protocols.http`, `palfrey.server._handle_connection`, `tests/protocols/test_http_*`, `tests/server/test_http_backpressure.py` |
| WS | WebSocket behavior | `websockets_sansio_impl.WebSocketsSansIOProtocol`, `wsproto_impl.WSProtocol`, deprecated `websockets_impl.WebSocketProtocol`, `websockets/auto.py` | `tests/protocols/test_websocket.py`, `tests/benchmarks/test_ws.py`, `docs/concepts/websockets.md` | `palfrey.protocols.websocket.handle_websocket`, `tests/protocols/test_websocket_*`, `tests/integration/test_websocket_integration.py` |
| LIFE | Lifespan protocol | `uvicorn.lifespan.on.LifespanOn`, `uvicorn.lifespan.off.LifespanOff`; startup/shutdown event queue, state, failed/unsupported handling | `tests/test_lifespan.py`, `docs/concepts/lifespan.md` | `palfrey.lifespan.LifespanManager`, `tests/runtime/test_lifespan.py`, `tests/server/test_server_serve_compat_extra.py` |
| CFG | Configuration | `uvicorn.config.Config`, `create_ssl_context`, protocol class resolution, reload path normalization, env fallback for workers and forwarded IPs | `tests/test_config.py`, `docs/settings.md` | `palfrey.config.PalfreyConfig`, `palfrey.runtime.run`, `tests/config/*`, `tests/runtime/test_runtime_api_compat.py` |
| CLI | CLI behavior | `uvicorn.main.main`, `uvicorn.main.run`, Click options for binding, reload, workers, loop, HTTP, WS, lifespan, SSL, logging, proxy headers, resource limits, factory mode | `tests/test_cli.py`, `docs/settings.md`, `README.md` | `palfrey.cli.main`, `palfrey.runtime.run`, `tests/cli/*`, `docs/en/docs/reference/cli.md` |
| SOCK | Socket/network binding | `Config.bind_socket`, server startup with host/port, UDS, FD, inherited sockets; subprocess socket passing | `tests/test_config.py`, `tests/test_subprocess.py`, `docs/settings.md` | `PalfreyConfig.bind_socket`, `PalfreyServer.serve`, `tests/config/test_config_bind_socket_compat.py`, `tests/server/test_socket_options.py` |
| TLS | TLS/SSL | `Config.create_ssl_context`, SSL CLI/programmatic options, `ssl_context_factory` support | `tests/test_ssl.py`, `docs/settings.md` | `palfrey.config.create_ssl_context`, `PalfreyServer._create_ssl_context`, `tests/config/*`, `tests/runtime/test_runtime_api_compat.py` |
| PROXY | Proxy headers | `uvicorn.middleware.proxy_headers.ProxyHeadersMiddleware`, `_TrustedHosts`, duplicate header handling, trusted chain selection | `tests/middleware/test_proxy_headers.py`, `docs/settings.md` | `palfrey.middleware.proxy_headers.ProxyHeadersMiddleware`, `tests/middleware/test_proxy_headers*` |
| LOG | Logging and observability | `uvicorn.logging.DefaultFormatter`, `AccessFormatter`, `TRACE_LOG_LEVEL`, `LOGGING_CONFIG`, `MessageLoggerMiddleware`, access log wiring | `tests/middleware/test_logging.py`, `tests/middleware/test_message_logger.py`, `docs/concepts/logging.md`, `docs/settings.md` | `palfrey.logging_config`, `palfrey.middleware.message_logger`, `tests/runtime/test_logging_config*`, `tests/middleware/test_message_logger*` |
| REL | Reload behavior | `BaseReload`, `StatReload`, `WatchFilesReload`, file filters, signal shutdown, child restart | `tests/supervisors/test_reload.py`, `docs/settings.md` | `palfrey.supervisors.reload.ReloadSupervisor`, `tests/supervisors/test_reload*` |
| WRK | Worker behavior | `uvicorn.supervisors.multiprocess.Multiprocess`, `_subprocess`, worker healthcheck, signal routing, child restart | `tests/supervisors/test_multiprocess.py`, `tests/supervisors/test_signal.py`, `tests/test_subprocess.py`, `docs/settings.md` | `palfrey.supervisors.workers.WorkerSupervisor`, `WorkerProcess`, `palfrey.workers.PalfreyWorker`, `tests/supervisors/test_workers*`, `tests/runtime/test_gunicorn_workers_compat.py` |
| LIMIT | Resource limits and overload | HTTP protocol `limit_concurrency`, `limit_max_requests`, jitter, keep-alive timeout, graceful shutdown timeout, server connection/task draining | `tests/protocols/test_http.py`, `tests/test_server.py`, `docs/server-behavior.md`, `docs/settings.md` | `palfrey.server.PalfreyServer`, `palfrey.protocols.http`, `tests/server/test_server_behavior_compat.py`, `tests/server/test_server_edge_cases.py` |
| PLAT | Platform behavior | Conditional coverage rules for Windows/Linux/macOS; Unix socket availability; asyncio/uvloop factory behavior | `pyproject.toml`, `tests/custom_loop_utils.py`, `tests/test_config.py`, `tests/supervisors/*` | `palfrey.loops`, `palfrey.server` socket guards, `tests/loops/*`, `tests/server/test_socket_options.py` |
| BENCH | Reference benchmarks | `tests/benchmarks/http.py`, `tests/benchmarks/test_http.py`, `tests/benchmarks/ws.py`, `tests/benchmarks/test_ws.py` | benchmark-marked protocol-level tests under Uvicorn | `benchmarks/run.py`, `benchmarks/apps.py`, `tests/benchmarks/*` |

## Required Behavior Inventory By Subsystem

Server lifecycle:

- Configuration loading, app import, factory mode.
- Lifespan auto/on/off, startup success/failure, shutdown success/failure.
- Graceful and forced shutdown, signal handling, repeated interrupt behavior.
- Active connection and task draining, cancellation after graceful timeout.
- Server state, started flag, max request shutdown, worker startup/termination.

ASGI behavior:

- ASGI2 and ASGI3 detection.
- HTTP, WebSocket, and lifespan scopes.
- Scope fields: `type`, `asgi`, `http_version`, `method`, `path`, `raw_path`, `query_string`, `root_path`, `scheme`, `headers`, `client`, `server`, `state`, and extensions.
- Lifespan state propagation and copy/ownership behavior.

HTTP protocol behavior:

- h11 and httptools request parsing.
- Malformed request lines and headers, huge headers, duplicate headers.
- Content-Length and Transfer-Encoding handling, chunked response emission.
- Request body streaming, read pausing/resuming, write backpressure.
- HEAD, HTTP/1.0, keep-alive, close, pipelining, Expect: 100-continue.
- ASGI message order validation, invalid status/header handling, app exceptions.
- Disconnect semantics before, during, and after response completion.

WebSocket behavior:

- Upgrade validation, handshake accept/reject, HTTP response during handshake.
- WebSocket scope fields, subprotocol negotiation, per-message-deflate behavior.
- Text, binary, fragmented, ping/pong, close frames, close codes and reasons.
- Client disconnect, server shutdown close code, app exceptions, invalid ASGI message order.
- Backend differences between wsproto, websockets-sansio, and deprecated websockets path.
- Oversized frames and malformed frames.

Lifespan behavior:

- Auto mode unsupported handling versus on-mode failure.
- Startup/shutdown complete and failed messages.
- Malformed transition detection.
- Application exceptions during lifespan.
- Lifespan state and context isolation.

Configuration and CLI behavior:

- Defaults, programmatic options, CLI options, `.env`, env var fallback, precedence.
- Invalid values and invalid combinations.
- Loop, HTTP, WebSocket, lifespan, interface, logging, reload, workers, limits, SSL, proxy headers, root path, host/port/UDS/FD.
- Version/help output, exit codes, warning/error messages.

Socket, TLS, proxy, logging, reload, worker, resource, and platform behavior:

- IPv4, IPv6, UDS, FD, inherited sockets, port conflicts, backlog, socket ownership and cleanup.
- TLS cert/key/password/CA/ciphers/factory behavior and HTTPS scope scheme.
- Trusted proxy chain parsing, duplicate forwarded headers, malformed values, WebSocket scheme mapping.
- Startup/shutdown/error/access/trace logs, colors, custom log configs, disabled access logs.
- Stat reload and watchfiles reload include/exclude behavior, rapid changes, child restart and cleanup.
- Multiprocess worker spawn, readiness, healthchecks, signals, child death/hang, restart and termination.
- Concurrency limits, queueing/rejection behavior, keep-alive under load, slow clients, leaks.
- macOS/Linux/Windows differences, default asyncio loop, uvloop support, signal and Unix socket limitations.

## Proposed Phase 2 Parity Matrix Structure

Store as `docs/audits/uvicorn-parity-matrix.md` or split by subsystem under `docs/audits/parity/`.

| ID | Subsystem | Uvicorn Behavior | Uvicorn Evidence | Palfrey Behavior | Palfrey Evidence | Status | Risk | Required Action |
| -- | --------- | ---------------- | ---------------- | ---------------- | ---------------- | ------ | ---- | --------------- |
| HTTP-001 | HTTP | Example behavior | File/test/doc refs | Observed Palfrey behavior | File/test/command refs | `UNVERIFIED` | High/Med/Low | Next action |

Allowed statuses:

- `PARITY_PROVEN`
- `PALFREY_SUPERIOR`
- `PARTIAL`
- `MISSING`
- `INTENTIONAL_DIFFERENCE`
- `NOT_APPLICABLE`
- `UNVERIFIED`

Phase 2 rules:

- Use stable IDs by subsystem prefix.
- No `PARITY_PROVEN` without executable Palfrey evidence tied to Uvicorn evidence.
- No `PALFREY_SUPERIOR` without parity evidence plus performance or semantic improvement evidence.
- Mark unknowns `UNVERIFIED`; do not infer from matching names.
- Include command, platform, Python, protocol backend, and event loop evidence for each executable claim.

## Prioritized Palfrey Risk Areas

1. HTTP/1.1 behavior under edge cases and load.
   Evidence: Uvicorn HTTP tests cover malformed/huge headers, pipelining, chunking, body streaming, disconnect-after-response, 100-continue, invalid ASGI message ordering, and concurrency limits in `tests/protocols/test_http.py`. Palfrey has many HTTP compatibility tests, but the single local benchmark showed HTTP throughput behind the reference in this run. This should be the first convergence subsystem.

2. Benchmark breadth and statistical confidence.
   Evidence: `benchmarks/run.py` currently covers a narrow HTTP/WebSocket echo workload. The campaign requires startup, first request, tail latency, CPU/RSS, slow client, large header/body, streaming, shutdown, keep-alive, and WebSocket latency/throughput matrices. Current baseline is useful but insufficient.

3. WebSocket backend parity across wsproto, websockets-sansio, and deprecated websockets behavior.
   Evidence: Uvicorn has backend-parametrized tests in `tests/protocols/test_websocket.py`. Palfrey has broad WebSocket coverage in `tests/protocols/test_websocket_behavior_compat.py` and `test_websocket_coverage_extra.py`, but a traceability table has not yet mapped each reference behavior.

4. Lifespan failure and state transition semantics.
   Evidence: Uvicorn tests startup/shutdown failed messages, auto-mode unsupported behavior, state mutation, and invalid transitions in `tests/test_lifespan.py`. Palfrey has lifespan coverage, but parity IDs need executable mapping.

5. Reload/watchfiles platform behavior.
   Evidence: Uvicorn marks several reload tests as flaky or non-Linux-specific. Palfrey reload behavior uses its own supervisor and canonical child argv builder. Platform matrix remains incomplete.

6. Multiprocess worker health and signal behavior.
   Evidence: Uvicorn has `Multiprocess`, worker healthcheck, and signal tests. Palfrey has `WorkerSupervisor`, but process death, hang, replacement, signal forwarding, and socket sharing need matrix-level accounting.

7. Proxy header chain parsing.
   Evidence: Uvicorn tests duplicate `X-Forwarded-For`, duplicate proto, IPv4/IPv6, networks, literals, ports, malformed values, and WebSocket scheme mapping. Palfrey has proxy tests, but every chain rule needs direct matrix mapping.

8. HTTP/2 and HTTP/3 scope expansion.
   Evidence: Palfrey supports opt-in h2/h3 while Uvicorn reference is HTTP/1.1/WebSocket-focused. These are Palfrey-specific features and must be excluded from Uvicorn parity claims or documented as out-of-reference extensions.

9. Public documentation claims.
   Evidence: existing docs include migration/reference material. Final claims must wait until matrix statuses are not `UNVERIFIED`, `PARTIAL`, or `MISSING`.

## Recommended Next Subsystem

Next subsystem: HTTP/1.1 request/response protocol behavior.

Reason:

- It is the highest shared hot path for correctness and performance.
- Uvicorn has dense reference coverage in `tests/protocols/test_http.py`.
- Palfrey has corresponding owners in `palfrey/protocols/http.py`, `palfrey/server.py`, and `tests/protocols/test_http_*`.
- The initial benchmark showed HTTP as the first measurable risk area in this run.

Recommended next slice:

1. Create `docs/audits/parity/http-1.1-matrix.md`.
2. Extract Uvicorn `tests/protocols/test_http.py` into behavior IDs without porting code yet.
3. Map each behavior to existing Palfrey tests or mark `UNVERIFIED`.
4. Run targeted Palfrey HTTP tests and the corresponding Uvicorn protocol tests.
5. Only then implement missing or divergent behavior.

## STOP Handoff

Completed:

- Read the campaign prompt.
- Confirmed `.sisyphus/` is absent and unused.
- Recorded repository state, branches, commits, package metadata, commands, CI, entry points, docs layout.
- Ran Palfrey authoritative Hatch validation.
- Ran Uvicorn documented validation wrapper.
- Ran Palfrey quality, docs, package build, and local benchmark baseline.
- Built Uvicorn subsystem inventory for Phase 1.
- Identified Palfrey owner files and test areas for next convergence work.
- Produced proposed Phase 2 matrix shape and prioritized risks.

Commands executed:

```bash
sed -n '1,220p' <home>/.codex/skills/repo-exploration/SKILL.md
sed -n '1,1340p' <home>/.codex/attachments/224b0021-cbdd-47a0-88b1-999c500303ee/pasted-text.txt
git status --short --branch
test ! -e .sisyphus
git rev-parse --abbrev-ref HEAD
git rev-parse HEAD
python3 --version
command -v hatch
command -v uv
sed -n '1,230p' pyproject.toml
sed -n '1,260p' <uvicorn-reference-repo>/pyproject.toml
hatch run test:test
scripts/test
hatch run lint
hatch run format-check
hatch run check-types
hatch run docs-build
hatch build
hatch run python -m benchmarks.run --enable-phases
rg -n "..." uvicorn/... tests/... docs/...
rg -n "..." palfrey/... tests/... docs/en/docs/...
```

Unresolved questions:

- Should the Phase 2 matrix live as one markdown file or as one file per subsystem?
- Should Uvicorn's deprecated `websockets_impl.py` be treated as out-of-scope because Uvicorn coverage omits it, or still as compatibility inventory because it remains in source?
- What is the accepted dedicated benchmark environment for the final performance campaign?
- Which Python version matrix should be mandatory for local proof versus CI proof?
- Should Palfrey HTTP/2 and HTTP/3 be tracked in a separate "Palfrey extension" matrix rather than Uvicorn parity?

Do not proceed to release bump or release documentation until the final program acceptance criteria are satisfied.
