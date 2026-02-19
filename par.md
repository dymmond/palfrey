# Palfrey 100% Uvicorn Drop-In Checklist

This checklist tracks drop-in replacement parity status against Uvicorn.
Current state: all behavioral parity items are completed; only performance-target tracking remains in progress.

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

- [x] `DROPIN-001` Replace simplified HTTP pipeline with protocol-native request/response cycles matching Uvicorn’s `h11` and `httptools` behavior.
  - Uvicorn source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/protocols/http/h11_impl.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/protocols/http/httptools_impl.py`
  - Palfrey target: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/protocols/http.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/server.py`
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/tests/protocols/test_http_asgi.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/protocols/test_http_behavior_parity.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/protocols/test_http_headers_parity_extra.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/server/test_server_behavior_parity.py`

- [x] `DROPIN-002` HTTP body streaming parity (`http.request` chunk flow + `http.disconnect` timing), instead of always full buffering.
  - Uvicorn source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/protocols/http/h11_impl.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/protocols/http/httptools_impl.py`
  - Palfrey target: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/protocols/http.py`
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/tests/protocols/test_http_asgi.py` (`test_run_http_asgi_streams_request_body_chunks`, `test_read_http_request_tracks_chunk_boundaries`)

- [x] `DROPIN-003` HTTP response streaming/chunking parity (multi-part body, no-content-length behavior, HEAD/no-body semantics).
  - Uvicorn source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/protocols/http/h11_impl.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/protocols/http/httptools_impl.py`
  - Palfrey target: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/protocols/http.py`
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/tests/protocols/test_http_asgi.py` and `/Users/tarsil/Projects/github/dymmond/palfrey/tests/protocols/test_http_headers_parity_extra.py`

- [x] `DROPIN-004` Flow-control/backpressure/pipelining parity.
  - Uvicorn source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/protocols/http/flow_control.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/protocols/http/h11_impl.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/protocols/http/httptools_impl.py`
  - Palfrey target: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/protocols/http.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/server.py`
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/server.py` (bounded queue + pause/resume hooks), `/Users/tarsil/Projects/github/dymmond/palfrey/tests/server/test_server_behavior_parity.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/server/test_server_internal.py`

- [x] `DROPIN-005` Distinct backend-level WS protocol parity for `websockets`, `websockets-sansio`, and `wsproto` end-to-end.
  - Uvicorn source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/protocols/websockets/websockets_impl.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/protocols/websockets/websockets_sansio_impl.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/protocols/websockets/wsproto_impl.py`
  - Palfrey target: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/protocols/websocket.py`
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/tests/protocols/test_websocket_protocol.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/protocols/test_websocket_behavior_parity.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/protocols/test_websocket_coverage_extra.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/integration/test_uvicorn_differential_parity.py`

- [x] `DROPIN-006` WS close/fragmentation/control-frame parity (including close code/reason behavior and sequencing).
  - Uvicorn source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/protocols/websockets/websockets_impl.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/protocols/websockets/websockets_sansio_impl.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/protocols/websockets/wsproto_impl.py`
  - Palfrey target: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/protocols/websocket.py`
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/tests/protocols/test_websocket_behavior_parity.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/protocols/test_websocket_protocol.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/integration/test_websocket_integration.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/integration/test_uvicorn_differential_parity.py`

- [x] `DROPIN-007` WS ping/pong/max-queue/per-message-deflate behavior parity across all WS backends.
  - Uvicorn source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/config.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/protocols/websockets/`
  - Palfrey target: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/config.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/protocols/websocket.py`
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/tests/protocols/test_websocket_protocol.py` (backend kwargs and ping/pong paths), `/Users/tarsil/Projects/github/dymmond/palfrey/tests/protocols/test_websocket_behavior_parity.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/integration/test_uvicorn_differential_parity.py`

- [x] `DROPIN-008` Lifespan class parity (`auto/on/off`) including startup/shutdown failure semantics and `should_exit` behavior.
  - Uvicorn source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/lifespan/on.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/lifespan/off.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/server.py`
  - Palfrey target: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/lifespan.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/server.py`
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/tests/runtime/test_lifespan.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/server/test_server_serve_parity_extra.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/runtime/test_runtime_main_parity.py`

- [x] `DROPIN-009` Parent socket binding/reuse parity for reload and multiprocess modes (bind once in parent, pass sockets to children).
  - Uvicorn source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/main.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/config.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/_subprocess.py`
  - Palfrey target: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/runtime.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/server.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/supervisors/`
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/tests/runtime/test_runtime.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/runtime/test_runtime_behavior_parity.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/config/test_config_bind_socket_parity.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/supervisors/test_reload.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/supervisors/test_workers.py`

- [x] `DROPIN-010` Server signal-capture parity (capture/restore handlers and re-raise captured signals behavior).
  - Uvicorn source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/server.py`
  - Palfrey target: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/server.py`
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/tests/server/test_server_behavior_parity.py` (`test_capture_signals_restores_handlers_and_replays_in_lifo_order`)

- [x] `DROPIN-011` Gunicorn worker integration parity (`uvicorn.workers` equivalent surface).
  - Uvicorn source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/workers.py`
  - Palfrey target: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/` (new module needed)
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/workers.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/runtime/test_gunicorn_workers_parity.py`

## P1: API/CLI/config compatibility gaps

- [x] `DROPIN-012` CLI parity polish: option types/choices/metavars/help and error behavior consistent with Uvicorn.
  - Uvicorn source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/main.py`
  - Palfrey target: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/cli.py`
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/cli.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/cli/test_cli_parity.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/cli/test_cli_surface.py`

- [x] `DROPIN-013` Python API parity for `run(...)` signatures and semantics (including custom protocol classes and loop factory import strings).
  - Uvicorn source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/main.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/config.py`
  - Palfrey target: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/runtime.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/config.py`
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/runtime.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/runtime/test_runtime_api_parity.py`
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/config.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/config/test_config_loop_factory_parity.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/config/test_config_load_parity.py`
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/server.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/server/test_server_serve_parity_extra.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/server/test_server_internal.py`

- [x] `DROPIN-014` `Config.load()` parity: interface auto-detection, app factory error paths, middleware wrapping order and conditions.
  - Uvicorn source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/config.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/middleware/`
  - Palfrey target: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/importer.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/adapters.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/middleware/`
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/config.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/importer.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/config/test_config_load_parity.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/importer/test_importer.py`
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/tests/config/test_config_loop_factory_parity.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/config/test_config_uvicorn_parity_extra.py`

- [x] `DROPIN-015` Default logging-config parity (`LOGGING_CONFIG`-style dict and logger hierarchy behavior).
  - Uvicorn source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/config.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/logging.py`
  - Palfrey target: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/logging_config.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/config.py`
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/config.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/logging_config.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/cli.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/runtime.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/runtime/test_logging_config_parity.py`

- [x] `DROPIN-016` SSL context creation and startup failure semantics parity.
  - Uvicorn source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/config.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/server.py`
  - Palfrey target: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/server.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/config.py`
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/config.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/server.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/config/test_config_load_parity.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/server/test_server_internal.py`

- [x] `DROPIN-017` `bind_socket`-equivalent behavior parity (host/port/uds/fd logs, inheritable socket handling).
  - Uvicorn source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/config.py`
  - Palfrey target: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/runtime.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/server.py`
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/tests/config/test_config_bind_socket_parity.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/runtime/test_runtime.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/runtime/test_runtime_behavior_parity.py`

- [x] `DROPIN-018` Importer parity for exception taxonomy and messages on import/factory errors.
  - Uvicorn source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/importer.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/config.py`
  - Palfrey target: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/importer.py`
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/tests/importer/test_importer_parity.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/importer/test_importer.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/config/test_config_load_parity.py`

- [x] `DROPIN-019` `main` module compatibility details (deprecated aliases/warnings behavior).
  - Uvicorn source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/main.py`
  - Palfrey target: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/main.py`
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/tests/runtime/test_main_module_parity.py`

- [x] `DROPIN-020` WSGI adapter parity for iterable/close lifecycle and environ fidelity.
  - Uvicorn source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/middleware/wsgi.py`
  - Palfrey target: `/Users/tarsil/Projects/github/dymmond/palfrey/palfrey/adapters.py`
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/tests/adapters/test_adapters.py`, `/Users/tarsil/Projects/github/dymmond/palfrey/tests/adapters/test_adapters_parity_extra.py`

## P2: Proof, coverage, and performance gaps

- [x] `DROPIN-021` File-by-file parity test mirror against Uvicorn test suite surface:
  - Uvicorn tests source: `/Users/tarsil/Projects/github/dymmond/uvicorn/tests/test_cli.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/tests/test_config.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/tests/test_server.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/tests/test_lifespan.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/tests/test_ssl.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/tests/protocols/test_http.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/tests/protocols/test_websocket.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/tests/supervisors/test_reload.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/tests/supervisors/test_multiprocess.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/tests/supervisors/test_signal.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/tests/middleware/test_wsgi.py`
  - Palfrey tests target: `/Users/tarsil/Projects/github/dymmond/palfrey/tests/`
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/tests/` (`594` passing tests in local gate run)

- [x] `DROPIN-022` Differential behavioral tests: run same app under Uvicorn and Palfrey and compare wire-level behavior for HTTP/WS/lifespan.
  - Uvicorn reference source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/protocols/`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/server.py`
  - Palfrey tests target: `/Users/tarsil/Projects/github/dymmond/palfrey/tests/integration/`
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/tests/integration/test_uvicorn_differential_parity.py`

- [x] `DROPIN-023` Platform parity tests (Unix + Windows signal/reload/worker behavior).
  - Uvicorn reference source: `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/server.py`, `/Users/tarsil/Projects/github/dymmond/uvicorn/uvicorn/supervisors/`
  - Palfrey CI target: `/Users/tarsil/Projects/github/dymmond/palfrey/.github/workflows/`
  - Proof: `/Users/tarsil/Projects/github/dymmond/palfrey/.github/workflows/ci.yml`

- [~] `DROPIN-024` Performance target tracking (separate from drop-in behavior parity).
  - Current snapshot: `/Users/tarsil/Projects/github/dymmond/palfrey/benchmarks/results/latest.json`
  - Measured ratios from latest run: HTTP `1.001x`, WebSocket `0.835x` (Palfrey/Uvicorn)
  - Remaining: close WS gap and reach the configured project target.

## Definition of done for “100% drop-in”

- [x] No known behavioral divergences left in P0/P1 items.
- [x] Compatibility test matrix passes across all mirrored Uvicorn suites.
- [x] CLI/Python API semantics match expected Uvicorn behavior for supported options.
- [~] Benchmarks and docs demonstrate final replacement-level readiness with reproducible artifacts.
