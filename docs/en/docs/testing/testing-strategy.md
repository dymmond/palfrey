# Testing Strategy

Palfrey test layout follows Uvicorn-style focus areas and expands by subsystem.

## Test domains

- `tests/config/`: configuration defaults and validation
- `tests/loops/`: loop setup behavior
- `tests/middleware/`: proxy headers and ASGI message logging middleware
- `tests/importer/`: app loading, factory support, interface adaptation
- `tests/protocols/`: HTTP/WebSocket parser and response behavior
- `tests/runtime/`: runtime orchestration and lifespan manager behavior
- `tests/supervisors/`: reload and worker supervision internals
- `tests/server/`: server internal capacity/address helpers
- `tests/integration/`: subprocess-level HTTP and WebSocket roundtrips

## Source mapping

- Uvicorn tests root: `tests/` in [Kludex/uvicorn](https://github.com/Kludex/uvicorn/tree/main/tests)
- Examples mirrored from:
  - `tests/test_cli.py`
  - `tests/test_config.py`
  - `tests/protocols/test_http.py`
  - `tests/protocols/test_websocket.py`
  - `tests/middleware/test_proxy_headers.py`
  - `tests/supervisors/test_multiprocess.py`
