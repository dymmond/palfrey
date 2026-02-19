# Palfrey 100% Uvicorn Drop-In Checklist

This checklist tracks what is still missing for literal 100% drop-in replacement parity.

Status legend:
- `[ ]` Missing
- `[~]` In progress
- `[x]` Completed

## Baseline already completed

- [x] `FOUNDATION-001` WS auto backend dispatch baseline.
- [x] `FOUNDATION-002` Server tick loop baseline (`default_headers`, notify callback, max-requests check).
- [x] `FOUNDATION-003` Graceful shutdown baseline (connection/task drain, timeout cancel path).
- [x] `FOUNDATION-004` Multiprocess supervisor baseline (healthcheck + signal matrix).
- [x] `FOUNDATION-005` Reload supervisor baseline (restart behavior and mtime reset).
- [x] `FOUNDATION-006` UVICORN env var compatibility baseline in CLI.
- [x] `FOUNDATION-007` Logging formatter baseline (`DefaultFormatter`/`AccessFormatter`).
- [x] `FOUNDATION-008` UDS permission baseline.
- [x] `FOUNDATION-009` Concurrency-limit baseline in live path.

## P0: Remaining hard blockers for literal drop-in

- [~] `DROPIN-001` Replace simplified HTTP pipeline with protocol-native request/response cycles matching Uvicorn’s `h11` and `httptools` behavior.
  - Uvicorn source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/protocols/http/h11_impl.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/protocols/http/httptools_impl.py`
  - Palfrey target: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/protocols/http.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/server.py`
  - Progress in this pass: request/response ASGI cycle semantics now mirror Uvicorn behavior for message ordering, completion, and 500 fallback.
  - Remaining: transport-level protocol object parity (full pipelining/flow-control lifecycle at `asyncio.Protocol` level).

- [x] `DROPIN-002` HTTP body streaming parity (`http.request` chunk flow + `http.disconnect` timing), instead of always full buffering.
  - Uvicorn source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/protocols/http/h11_impl.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/protocols/http/httptools_impl.py`
  - Palfrey target: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/protocols/http.py`
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/tests/protocols/test_http_asgi.py` (`test_run_http_asgi_streams_request_body_chunks`, `test_read_http_request_tracks_chunk_boundaries`)

- [x] `DROPIN-003` HTTP response streaming/chunking parity (multi-part body, no-content-length behavior, HEAD/no-body semantics).
  - Uvicorn source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/protocols/http/h11_impl.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/protocols/http/httptools_impl.py`
  - Palfrey target: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/protocols/http.py`
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/tests/protocols/test_http_asgi.py` and `/Users/tarsil/Projects/github/dymmond/palfrey/tests/protocols/test_http_headers_parity_extra.py`

- [~] `DROPIN-004` Flow-control/backpressure/pipelining parity.
  - Uvicorn source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/protocols/http/flow_control.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/protocols/http/h11_impl.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/protocols/http/httptools_impl.py`
  - Palfrey target: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/protocols/http.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/server.py`
  - Progress in this pass: added bounded pipelined request queueing with reader pause/resume backpressure hooks in `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/server.py`.
  - Remaining: full transport-callback parity with `FlowControl` pause/resume at protocol-event granularity.

- [~] `DROPIN-005` Distinct backend-level WS protocol parity for `websockets`, `websockets-sansio`, and `wsproto` end-to-end.
  - Uvicorn source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/protocols/websockets/websockets_impl.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/protocols/websockets/websockets_sansio_impl.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/protocols/websockets/wsproto_impl.py`
  - Palfrey target: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/protocols/websocket.py`
  - Progress in this pass: expanded backend-path coverage for frame parsing, handshake map validation, and core backend EOF/flow-control behavior.
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/tests/protocols/test_websocket_behavior_parity.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/protocols/test_websocket_coverage_extra.py`
  - Remaining: transport-level behavior and extension negotiation still need strict differential verification backend-by-backend.

- [~] `DROPIN-006` WS close/fragmentation/control-frame parity (including close code/reason behavior and sequencing).
  - Uvicorn source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/protocols/websockets/websockets_impl.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/protocols/websockets/websockets_sansio_impl.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/protocols/websockets/wsproto_impl.py`
  - Palfrey target: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/protocols/websocket.py`
  - Progress in this pass: added explicit close/EOF code-path assertions (`1005` vs `1006`) and fragmented frame parser edge-case coverage.
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/tests/protocols/test_websocket_behavior_parity.py`
  - Remaining: cross-backend close sequencing parity under concurrent send/close races.

- [~] `DROPIN-007` WS ping/pong/max-queue/per-message-deflate behavior parity across all WS backends.
  - Uvicorn source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/config.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/protocols/websockets/`
  - Palfrey target: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/config.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/protocols/websocket.py`
  - Progress in this pass: added ping/pong high-watermark drain behavior coverage in core backend path.
  - Remaining: backend-level max-queue and per-message-deflate differential parity still needs end-to-end verification.

- [x] `DROPIN-008` Lifespan class parity (`auto/on/off`) including startup/shutdown failure semantics and `should_exit` behavior.
  - Uvicorn source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/lifespan/on.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/lifespan/off.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/server.py`
  - Palfrey target: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/lifespan.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/server.py`
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/tests/runtime/test_lifespan.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/server/test_server_serve_parity_extra.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/runtime/test_runtime_main_parity.py`

- [~] `DROPIN-009` Parent socket binding/reuse parity for reload and multiprocess modes (bind once in parent, pass sockets to children).
  - Uvicorn source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/main.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/config.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/_subprocess.py`
  - Palfrey target: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/runtime.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/server.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/supervisors/`
  - Progress in this pass: parent now binds once via `PalfreyConfig.bind_socket()` and passes sockets to reload/worker children (`--fd` + `pass_fds` for reload, direct socket list for multiprocess workers).
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/tests/runtime/test_runtime.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/runtime/test_runtime_behavior_parity.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/config/test_config_bind_socket_parity.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/supervisors/test_reload.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/supervisors/test_workers.py`
  - Remaining: close remaining platform-specific edge cases to match Uvicorn subprocess/socket lifecycle semantics exactly.

- [x] `DROPIN-010` Server signal-capture parity (capture/restore handlers and re-raise captured signals behavior).
  - Uvicorn source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/server.py`
  - Palfrey target: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/server.py`
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/tests/server/test_server_behavior_parity.py` (`test_capture_signals_restores_handlers_and_replays_in_lifo_order`)

- [x] `DROPIN-011` Gunicorn worker integration parity (`uvicorn.workers` equivalent surface).
  - Uvicorn source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/workers.py`
  - Palfrey target: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/` (new module needed)
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/workers.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/runtime/test_gunicorn_workers_parity.py`

## P1: API/CLI/config compatibility gaps

- [~] `DROPIN-012` CLI parity polish: option types/choices/metavars/help and error behavior consistent with Uvicorn.
  - Uvicorn source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/main.py`
  - Palfrey target: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/cli.py`
  - Progress in this pass: aligned remaining option help/default surface for reload/watch flags, proxy/trust flags, SSL flags, header flag text, and existing Uvicorn-style metavars/choices for `--loop`, `--http`, `--ws`, `--lifespan`, `--interface`, and `--log-level`.
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/tests/cli/test_cli_surface.py`
  - Remaining: align remaining help text and edge-case error output details one-to-one.

- [~] `DROPIN-013` Python API parity for `run(...)` signatures and semantics (including custom protocol classes and loop factory import strings).
  - Uvicorn source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/main.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/config.py`
  - Palfrey target: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/runtime.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/config.py`
  - Progress in this pass: expanded `palfrey.runtime.run()` to an explicit Uvicorn-style argument surface and added forwarding/normalization parity tests; added `PalfreyConfig.get_loop_factory()` and `setup_event_loop()` compatibility behavior; added concrete/custom HTTP+WS protocol-class acceptance in `PalfreyConfig.load()` and runtime API forwarding.
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/runtime.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/runtime/test_runtime_api_parity.py`
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/config.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/config/test_config_loop_factory_parity.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/config/test_config_load_parity.py`
  - Remaining: transport-layer execution still does not instantiate arbitrary custom protocol classes end-to-end like Uvicorn’s asyncio.Protocol architecture.

- [~] `DROPIN-014` `Config.load()` parity: interface auto-detection, app factory error paths, middleware wrapping order and conditions.
  - Uvicorn source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/config.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/middleware/`
  - Palfrey target: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/importer.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/adapters.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/middleware/`
  - Progress in this pass: added `PalfreyConfig.load()` compatibility path and aligned middleware wrapping order (`MessageLogger` before `ProxyHeaders` wrapping).
  - Progress in this pass: added loop-factory compatibility APIs on config (`get_loop_factory` / removed `setup_event_loop` behavior), mirroring Uvicorn config API surface.
  - Progress in this pass: server startup path now calls `config.load()` first (matching Uvicorn flow), so import/factory/SSL/protocol-class load behavior is centralized in config load semantics.
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/config.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/importer.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/config/test_config_load_parity.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/importer/test_importer.py`
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/tests/config/test_config_loop_factory_parity.py`
  - Remaining: full lifecycle-class parity (`lifespan_class` object behavior) and strict one-to-one `Config.load()` error/output details.

- [~] `DROPIN-015` Default logging-config parity (`LOGGING_CONFIG`-style dict and logger hierarchy behavior).
  - Uvicorn source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/config.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/logging.py`
  - Palfrey target: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/logging_config.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/config.py`
  - Progress in this pass: added Uvicorn-style `LOGGING_CONFIG` default payload in config, wired CLI/runtime to use that payload when `log_config` is omitted, and aligned formatter `use_colors` override behavior for dict log configs.
  - Progress in this pass: `configure_logging()` still applies log-level overrides and access-log disabling even when `log_config` is provided.
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/config.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/logging_config.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/cli.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/runtime.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/runtime/test_logging_config_parity.py`
  - Remaining: complete strict end-to-end equivalence checks for edge-case logger hierarchy behavior under custom external log configs.

- [~] `DROPIN-016` SSL context creation and startup failure semantics parity.
  - Uvicorn source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/config.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/server.py`
  - Palfrey target: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/server.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/config.py`
  - Progress in this pass: introduced shared `create_ssl_context()` behavior and `Config.load()` SSL initialization path, with certfile requirement checks and parity tests.
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/config.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/server.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/config/test_config_load_parity.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/server/test_server_internal.py`
  - Remaining: tighten startup-exit semantics so all SSL initialization failures match Uvicorn process-exit behavior exactly.

- [~] `DROPIN-017` `bind_socket`-equivalent behavior parity (host/port/uds/fd logs, inheritable socket handling).
  - Uvicorn source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/config.py`
  - Palfrey target: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/runtime.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/server.py`
  - Progress in this pass: added `PalfreyConfig.bind_socket()` with host/port, uds, and fd branches; inheritable socket handling; runtime integration in reload/workers paths.
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/tests/config/test_config_bind_socket_parity.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/runtime/test_runtime.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/runtime/test_runtime_behavior_parity.py`
  - Remaining: finalize exact startup logging/error surface details for strict one-to-one behavior.

- [~] `DROPIN-018` Importer parity for exception taxonomy and messages on import/factory errors.
  - Uvicorn source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/importer.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/config.py`
  - Palfrey target: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/importer.py`
  - Progress in this pass: introduced `ImportFromStringError` compatibility class and aligned `_import_from_string()` error taxonomy/messages with Uvicorn semantics while preserving `AppImportError` compatibility.
  - Progress in this pass: aligned factory failure semantics so `factory=True` TypeError paths now surface Uvicorn-style `Error loading ASGI app factory: ...` from `Config.load()`.
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/tests/importer/test_importer_parity.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/importer/test_importer.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/config/test_config_load_parity.py`
  - Remaining: finish parity on any residual edge-case factory warning/error-message details.

- [x] `DROPIN-019` `main` module compatibility details (deprecated aliases/warnings behavior).
  - Uvicorn source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/main.py`
  - Palfrey target: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/main.py`
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/tests/runtime/test_main_module_parity.py`

- [x] `DROPIN-020` WSGI adapter parity for iterable/close lifecycle and environ fidelity.
  - Uvicorn source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/middleware/wsgi.py`
  - Palfrey target: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/adapters.py`
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/tests/adapters/test_adapters.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/adapters/test_adapters_parity_extra.py`

## P2: Proof, coverage, and performance gaps

- [~] `DROPIN-021` File-by-file parity test mirror against Uvicorn test suite surface:
  - Uvicorn tests source: `/Users/tarsil/Projects/github/dymmond/uvicorn/tests/test_cli.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/tests/test_config.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/tests/test_server.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/tests/test_lifespan.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/tests/test_ssl.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/tests/protocols/test_http.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/tests/protocols/test_websocket.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/tests/supervisors/test_reload.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/tests/supervisors/test_multiprocess.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/tests/supervisors/test_signal.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/tests/middleware/test_wsgi.py`
  - Palfrey tests target: `/Users/tarsil/Projects/github/dymmond/palfrey/tests/`
  - Progress in this pass: expanded mirrored coverage around config-load behavior, WSGI middleware parity, and websocket protocol branch matrix.

- [~] `DROPIN-022` Differential behavioral tests: run same app under Uvicorn and Palfrey and compare wire-level behavior for HTTP/WS/lifespan.
  - Uvicorn reference source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/protocols/`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/server.py`
  - Palfrey tests target: `/Users/tarsil/Projects/github/dymmond/palfrey/tests/integration/`
  - Progress in this pass: added differential subprocess tests for HTTP status/body/header behavior, websocket echo, websocket close code/reason, and lifespan-startup failure exit code (`uvicorn` vs `palfrey`) with automatic skip when Uvicorn is unavailable in the test environment.
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/tests/integration/test_uvicorn_differential_parity.py`
  - Remaining: extend matrix to broader header corner cases and backend-specific websocket extension negotiation.

- [~] `DROPIN-023` Platform parity tests (Unix + Windows signal/reload/worker behavior).
  - Uvicorn reference source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/server.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/supervisors/`
  - Palfrey CI target: `/Users/tarsil/Projects/github/dymmond/palfrey/.github/workflows/`
  - Progress in this pass: CI now runs portability smoke tests on `macos-latest` and `windows-latest` in addition to Linux coverage gates.
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/.github/workflows/ci.yml`
  - Remaining: add signal/reload/worker parity cases that are explicitly platform-discriminated (especially Windows process/signal semantics).

- [ ] `DROPIN-024` Performance target not met yet for strict replacement goals.
  - Current snapshot: `/Users/tarsil/Projects/github/dymmond/palfrey/benchmarks/results/latest.json`
  - Measured ratios from latest run: HTTP `1.001x`, WebSocket `0.835x` (Palfrey/Uvicorn)
  - Required next step: close WS gap and reach project target before claiming full replacement.

## Definition of done for “100% drop-in”

- [ ] No known behavioral divergences left in P0/P1 items.
- [ ] Compatibility test matrix passes across all mirrored Uvicorn suites.
- [ ] CLI/Python API semantics match expected Uvicorn behavior for supported options.
- [ ] Benchmarks and docs demonstrate final replacement-level readiness with reproducible artifacts.
