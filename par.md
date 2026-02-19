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
  - Uvicorn source: `<uvicorn-reference-repo>/uvicorn/protocols/http/h11_impl.py`, `<uvicorn-reference-repo>/uvicorn/protocols/http/httptools_impl.py`
  - Palfrey target: `<palfrey-repo>/palfrey/protocols/http.py`, `<palfrey-repo>/palfrey/server.py`
  - Proof: `<palfrey-repo>/tests/protocols/test_http_asgi.py`, `<palfrey-repo>/tests/protocols/test_http_behavior_parity.py`, `<palfrey-repo>/tests/protocols/test_http_headers_parity_extra.py`, `<palfrey-repo>/tests/server/test_server_behavior_parity.py`

- [x] `DROPIN-002` HTTP body streaming parity (`http.request` chunk flow + `http.disconnect` timing), instead of always full buffering.
  - Uvicorn source: `<uvicorn-reference-repo>/uvicorn/protocols/http/h11_impl.py`, `<uvicorn-reference-repo>/uvicorn/protocols/http/httptools_impl.py`
  - Palfrey target: `<palfrey-repo>/palfrey/protocols/http.py`
  - Proof: `<palfrey-repo>/tests/protocols/test_http_asgi.py` (`test_run_http_asgi_streams_request_body_chunks`, `test_read_http_request_tracks_chunk_boundaries`)

- [x] `DROPIN-003` HTTP response streaming/chunking parity (multi-part body, no-content-length behavior, HEAD/no-body semantics).
  - Uvicorn source: `<uvicorn-reference-repo>/uvicorn/protocols/http/h11_impl.py`, `<uvicorn-reference-repo>/uvicorn/protocols/http/httptools_impl.py`
  - Palfrey target: `<palfrey-repo>/palfrey/protocols/http.py`
  - Proof: `<palfrey-repo>/tests/protocols/test_http_asgi.py` and `<palfrey-repo>/tests/protocols/test_http_headers_parity_extra.py`

- [x] `DROPIN-004` Flow-control/backpressure/pipelining parity.
  - Uvicorn source: `<uvicorn-reference-repo>/uvicorn/protocols/http/flow_control.py`, `<uvicorn-reference-repo>/uvicorn/protocols/http/h11_impl.py`, `<uvicorn-reference-repo>/uvicorn/protocols/http/httptools_impl.py`
  - Palfrey target: `<palfrey-repo>/palfrey/protocols/http.py`, `<palfrey-repo>/palfrey/server.py`
  - Proof: `<palfrey-repo>/palfrey/server.py` (bounded queue + pause/resume hooks), `<palfrey-repo>/tests/server/test_server_behavior_parity.py`, `<palfrey-repo>/tests/server/test_server_internal.py`

- [x] `DROPIN-005` Distinct backend-level WS protocol parity for `websockets`, `websockets-sansio`, and `wsproto` end-to-end.
  - Uvicorn source: `<uvicorn-reference-repo>/uvicorn/protocols/websockets/websockets_impl.py`, `<uvicorn-reference-repo>/uvicorn/protocols/websockets/websockets_sansio_impl.py`, `<uvicorn-reference-repo>/uvicorn/protocols/websockets/wsproto_impl.py`
  - Palfrey target: `<palfrey-repo>/palfrey/protocols/websocket.py`
  - Proof: `<palfrey-repo>/tests/protocols/test_websocket_protocol.py`, `<palfrey-repo>/tests/protocols/test_websocket_behavior_parity.py`, `<palfrey-repo>/tests/protocols/test_websocket_coverage_extra.py`, `<palfrey-repo>/tests/integration/test_uvicorn_differential_parity.py`

- [x] `DROPIN-006` WS close/fragmentation/control-frame parity (including close code/reason behavior and sequencing).
  - Uvicorn source: `<uvicorn-reference-repo>/uvicorn/protocols/websockets/websockets_impl.py`, `<uvicorn-reference-repo>/uvicorn/protocols/websockets/websockets_sansio_impl.py`, `<uvicorn-reference-repo>/uvicorn/protocols/websockets/wsproto_impl.py`
  - Palfrey target: `<palfrey-repo>/palfrey/protocols/websocket.py`
  - Proof: `<palfrey-repo>/tests/protocols/test_websocket_behavior_parity.py`, `<palfrey-repo>/tests/protocols/test_websocket_protocol.py`, `<palfrey-repo>/tests/integration/test_websocket_integration.py`, `<palfrey-repo>/tests/integration/test_uvicorn_differential_parity.py`

- [x] `DROPIN-007` WS ping/pong/max-queue/per-message-deflate behavior parity across all WS backends.
  - Uvicorn source: `<uvicorn-reference-repo>/uvicorn/config.py`, `<uvicorn-reference-repo>/uvicorn/protocols/websockets/`
  - Palfrey target: `<palfrey-repo>/palfrey/config.py`, `<palfrey-repo>/palfrey/protocols/websocket.py`
  - Proof: `<palfrey-repo>/tests/protocols/test_websocket_protocol.py` (backend kwargs and ping/pong paths), `<palfrey-repo>/tests/protocols/test_websocket_behavior_parity.py`, `<palfrey-repo>/tests/integration/test_uvicorn_differential_parity.py`

- [x] `DROPIN-008` Lifespan class parity (`auto/on/off`) including startup/shutdown failure semantics and `should_exit` behavior.
  - Uvicorn source: `<uvicorn-reference-repo>/uvicorn/lifespan/on.py`, `<uvicorn-reference-repo>/uvicorn/lifespan/off.py`, `<uvicorn-reference-repo>/uvicorn/server.py`
  - Palfrey target: `<palfrey-repo>/palfrey/lifespan.py`, `<palfrey-repo>/palfrey/server.py`
  - Proof: `<palfrey-repo>/tests/runtime/test_lifespan.py`, `<palfrey-repo>/tests/server/test_server_serve_parity_extra.py`, `<palfrey-repo>/tests/runtime/test_runtime_main_parity.py`

- [x] `DROPIN-009` Parent socket binding/reuse parity for reload and multiprocess modes (bind once in parent, pass sockets to children).
  - Uvicorn source: `<uvicorn-reference-repo>/uvicorn/main.py`, `<uvicorn-reference-repo>/uvicorn/config.py`, `<uvicorn-reference-repo>/uvicorn/_subprocess.py`
  - Palfrey target: `<palfrey-repo>/palfrey/runtime.py`, `<palfrey-repo>/palfrey/server.py`, `<palfrey-repo>/palfrey/supervisors/`
  - Proof: `<palfrey-repo>/tests/runtime/test_runtime.py`, `<palfrey-repo>/tests/runtime/test_runtime_behavior_parity.py`, `<palfrey-repo>/tests/config/test_config_bind_socket_parity.py`, `<palfrey-repo>/tests/supervisors/test_reload.py`, `<palfrey-repo>/tests/supervisors/test_workers.py`

- [x] `DROPIN-010` Server signal-capture parity (capture/restore handlers and re-raise captured signals behavior).
  - Uvicorn source: `<uvicorn-reference-repo>/uvicorn/server.py`
  - Palfrey target: `<palfrey-repo>/palfrey/server.py`
  - Proof: `<palfrey-repo>/tests/server/test_server_behavior_parity.py` (`test_capture_signals_restores_handlers_and_replays_in_lifo_order`)

- [x] `DROPIN-011` Gunicorn worker integration parity (`uvicorn.workers` equivalent surface).
  - Uvicorn source: `<uvicorn-reference-repo>/uvicorn/workers.py`
  - Palfrey target: `<palfrey-repo>/palfrey/` (new module needed)
  - Proof: `<palfrey-repo>/palfrey/workers.py`, `<palfrey-repo>/tests/runtime/test_gunicorn_workers_parity.py`

## P1: API/CLI/config compatibility gaps

- [x] `DROPIN-012` CLI parity polish: option types/choices/metavars/help and error behavior consistent with Uvicorn.
  - Uvicorn source: `<uvicorn-reference-repo>/uvicorn/main.py`
  - Palfrey target: `<palfrey-repo>/palfrey/cli.py`
  - Proof: `<palfrey-repo>/palfrey/cli.py`, `<palfrey-repo>/tests/cli/test_cli_parity.py`, `<palfrey-repo>/tests/cli/test_cli_surface.py`

- [x] `DROPIN-013` Python API parity for `run(...)` signatures and semantics (including custom protocol classes and loop factory import strings).
  - Uvicorn source: `<uvicorn-reference-repo>/uvicorn/main.py`, `<uvicorn-reference-repo>/uvicorn/config.py`
  - Palfrey target: `<palfrey-repo>/palfrey/runtime.py`, `<palfrey-repo>/palfrey/config.py`
  - Proof: `<palfrey-repo>/palfrey/runtime.py`, `<palfrey-repo>/tests/runtime/test_runtime_api_parity.py`
  - Proof: `<palfrey-repo>/palfrey/config.py`, `<palfrey-repo>/tests/config/test_config_loop_factory_parity.py`, `<palfrey-repo>/tests/config/test_config_load_parity.py`
  - Proof: `<palfrey-repo>/palfrey/server.py`, `<palfrey-repo>/tests/server/test_server_serve_parity_extra.py`, `<palfrey-repo>/tests/server/test_server_internal.py`

- [x] `DROPIN-014` `Config.load()` parity: interface auto-detection, app factory error paths, middleware wrapping order and conditions.
  - Uvicorn source: `<uvicorn-reference-repo>/uvicorn/config.py`, `<uvicorn-reference-repo>/uvicorn/middleware/`
  - Palfrey target: `<palfrey-repo>/palfrey/importer.py`, `<palfrey-repo>/palfrey/adapters.py`, `<palfrey-repo>/palfrey/middleware/`
  - Proof: `<palfrey-repo>/palfrey/config.py`, `<palfrey-repo>/palfrey/importer.py`, `<palfrey-repo>/tests/config/test_config_load_parity.py`, `<palfrey-repo>/tests/importer/test_importer.py`
  - Proof: `<palfrey-repo>/tests/config/test_config_loop_factory_parity.py`, `<palfrey-repo>/tests/config/test_config_uvicorn_parity_extra.py`

- [x] `DROPIN-015` Default logging-config parity (`LOGGING_CONFIG`-style dict and logger hierarchy behavior).
  - Uvicorn source: `<uvicorn-reference-repo>/uvicorn/config.py`, `<uvicorn-reference-repo>/uvicorn/logging.py`
  - Palfrey target: `<palfrey-repo>/palfrey/logging_config.py`, `<palfrey-repo>/palfrey/config.py`
  - Proof: `<palfrey-repo>/palfrey/config.py`, `<palfrey-repo>/palfrey/logging_config.py`, `<palfrey-repo>/palfrey/cli.py`, `<palfrey-repo>/palfrey/runtime.py`, `<palfrey-repo>/tests/runtime/test_logging_config_parity.py`

- [x] `DROPIN-016` SSL context creation and startup failure semantics parity.
  - Uvicorn source: `<uvicorn-reference-repo>/uvicorn/config.py`, `<uvicorn-reference-repo>/uvicorn/server.py`
  - Palfrey target: `<palfrey-repo>/palfrey/server.py`, `<palfrey-repo>/palfrey/config.py`
  - Proof: `<palfrey-repo>/palfrey/config.py`, `<palfrey-repo>/palfrey/server.py`, `<palfrey-repo>/tests/config/test_config_load_parity.py`, `<palfrey-repo>/tests/server/test_server_internal.py`

- [x] `DROPIN-017` `bind_socket`-equivalent behavior parity (host/port/uds/fd logs, inheritable socket handling).
  - Uvicorn source: `<uvicorn-reference-repo>/uvicorn/config.py`
  - Palfrey target: `<palfrey-repo>/palfrey/runtime.py`, `<palfrey-repo>/palfrey/server.py`
  - Proof: `<palfrey-repo>/tests/config/test_config_bind_socket_parity.py`, `<palfrey-repo>/tests/runtime/test_runtime.py`, `<palfrey-repo>/tests/runtime/test_runtime_behavior_parity.py`

- [x] `DROPIN-018` Importer parity for exception taxonomy and messages on import/factory errors.
  - Uvicorn source: `<uvicorn-reference-repo>/uvicorn/importer.py`, `<uvicorn-reference-repo>/uvicorn/config.py`
  - Palfrey target: `<palfrey-repo>/palfrey/importer.py`
  - Proof: `<palfrey-repo>/tests/importer/test_importer_parity.py`, `<palfrey-repo>/tests/importer/test_importer.py`, `<palfrey-repo>/tests/config/test_config_load_parity.py`

- [x] `DROPIN-019` `main` module compatibility details (deprecated aliases/warnings behavior).
  - Uvicorn source: `<uvicorn-reference-repo>/uvicorn/main.py`
  - Palfrey target: `<palfrey-repo>/palfrey/main.py`
  - Proof: `<palfrey-repo>/tests/runtime/test_main_module_parity.py`

- [x] `DROPIN-020` WSGI adapter parity for iterable/close lifecycle and environ fidelity.
  - Uvicorn source: `<uvicorn-reference-repo>/uvicorn/middleware/wsgi.py`
  - Palfrey target: `<palfrey-repo>/palfrey/adapters.py`
  - Proof: `<palfrey-repo>/tests/adapters/test_adapters.py`, `<palfrey-repo>/tests/adapters/test_adapters_parity_extra.py`

## P2: Proof, coverage, and performance gaps

- [x] `DROPIN-021` File-by-file parity test mirror against Uvicorn test suite surface:
  - Uvicorn tests source: `<uvicorn-reference-repo>/tests/test_cli.py`, `<uvicorn-reference-repo>/tests/test_config.py`, `<uvicorn-reference-repo>/tests/test_server.py`, `<uvicorn-reference-repo>/tests/test_lifespan.py`, `<uvicorn-reference-repo>/tests/test_ssl.py`, `<uvicorn-reference-repo>/tests/protocols/test_http.py`, `<uvicorn-reference-repo>/tests/protocols/test_websocket.py`, `<uvicorn-reference-repo>/tests/supervisors/test_reload.py`, `<uvicorn-reference-repo>/tests/supervisors/test_multiprocess.py`, `<uvicorn-reference-repo>/tests/supervisors/test_signal.py`, `<uvicorn-reference-repo>/tests/middleware/test_wsgi.py`
  - Palfrey tests target: `<palfrey-repo>/tests/`
  - Proof: `<palfrey-repo>/tests/` (`594` passing tests in local gate run)

- [x] `DROPIN-022` Differential behavioral tests: run same app under Uvicorn and Palfrey and compare wire-level behavior for HTTP/WS/lifespan.
  - Uvicorn reference source: `<uvicorn-reference-repo>/uvicorn/protocols/`, `<uvicorn-reference-repo>/uvicorn/server.py`
  - Palfrey tests target: `<palfrey-repo>/tests/integration/`
  - Proof: `<palfrey-repo>/tests/integration/test_uvicorn_differential_parity.py`

- [x] `DROPIN-023` Platform parity tests (Unix + Windows signal/reload/worker behavior).
  - Uvicorn reference source: `<uvicorn-reference-repo>/uvicorn/server.py`, `<uvicorn-reference-repo>/uvicorn/supervisors/`
  - Palfrey CI target: `<palfrey-repo>/.github/workflows/`
  - Proof: `<palfrey-repo>/.github/workflows/ci.yml`

- [~] `DROPIN-024` Performance target tracking (separate from drop-in behavior parity).
  - Current snapshot: `<palfrey-repo>/benchmarks/results/latest.json`
  - Measured ratios from latest run: HTTP `1.001x`, WebSocket `0.835x` (Palfrey/Uvicorn)
  - Remaining: close WS gap and reach the configured project target.

## Definition of done for “100% drop-in”

- [x] No known behavioral divergences left in P0/P1 items.
- [x] Compatibility test matrix passes across all mirrored Uvicorn suites.
- [x] CLI/Python API semantics match expected Uvicorn behavior for supported options.
- [~] Benchmarks and docs demonstrate final replacement-level readiness with reproducible artifacts.
