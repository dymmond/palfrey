# Parity Matrix

This matrix lists Palfrey behaviors grounded in explicit Uvicorn/Click sources.

| Area | Palfrey Status | Uvicorn Docs Source | Uvicorn Source Paths | Click Source |
| --- | --- | --- | --- | --- |
| CLI command surface | **Partial parity** (option surface largely aligned; startup lifecycle remains partial) | "Settings" ([uvicorn.dev/settings](https://uvicorn.dev/settings/)) | `uvicorn/main.py` | `src/click/core.py` |
| App import + factory semantics | **Partial parity** (includes dotted attrs and nested import-error propagation parity) | "Settings" (Application) | `uvicorn/importer.py`, `uvicorn/config.py`, `uvicorn/main.py` | `src/click/core.py` |
| Loop setup modes (`none`, `auto`, `asyncio`, `uvloop`) | Implemented | "Settings" (Implementation) | `uvicorn/config.py` (`LOOP_SETUPS`) |  |
| HTTP implementation option values (`auto`, `h11`, `httptools`) | **Partial parity** (value surface exists; backend implementations not equivalent) | "Settings" (Implementation) | `uvicorn/config.py` (`HTTP_PROTOCOLS`), `uvicorn/protocols/http/h11_impl.py`, `uvicorn/protocols/http/httptools_impl.py` |  |
| WebSocket implementation option values | **Partial parity** (value surface implemented, backend mapping differs) | "Settings" + "Concepts: WebSockets" ([uvicorn.dev/concepts/websockets](https://uvicorn.dev/concepts/websockets/)) | `uvicorn/config.py` (`WS_PROTOCOLS`), `uvicorn/protocols/websockets/*` |  |
| Lifespan modes (`auto`, `on`, `off`) | **Partial parity** | "Concepts: Lifespan" ([uvicorn.dev/concepts/lifespan](https://uvicorn.dev/concepts/lifespan/)) | `uvicorn/lifespan/on.py`, `uvicorn/lifespan/off.py`, `uvicorn/server.py` |  |
| Proxy headers behavior | Implemented middleware | "Deployment" (Proxies and forwarded headers) ([uvicorn.dev/deployment](https://uvicorn.dev/deployment/)) | `uvicorn/middleware/proxy_headers.py` |  |
| ASGI message logger behavior | Implemented middleware | n/a (source-driven) | `uvicorn/middleware/message_logger.py` |  |
| Worker supervision behavior | **Partial parity** | "Deployment" | `uvicorn/supervisors/multiprocess.py`, `uvicorn/_subprocess.py` |  |
| Reload supervision behavior and options | **Partial parity** | "Settings" (Development) | `uvicorn/supervisors/basereload.py`, `uvicorn/supervisors/statreload.py`, `uvicorn/supervisors/watchfilesreload.py` |  |
| TLS option surface | **Partial parity** | "Settings" (HTTPS) | `uvicorn/main.py`, `uvicorn/config.py` |  |
| Logging option surface | **Partial parity** | "Settings" (Logging) | `uvicorn/main.py`, `uvicorn/config.py`, `uvicorn/logging.py` |  |
| Interface adapters (`asgi3`, `asgi2`, `wsgi`) | Implemented | "Settings" (Application Interface) | `uvicorn/config.py`, `uvicorn/middleware/asgi2.py`, `uvicorn/middleware/wsgi.py` |  |
| Keep-alive + header defaults | **Partial parity** | "Server Behavior" ([uvicorn.dev/server-behavior](https://uvicorn.dev/server-behavior/)) | `uvicorn/server.py`, `uvicorn/protocols/http/*` |  |

## Uvicorn Test Pattern Sources Consulted

- `tests/test_cli.py`
- `tests/test_config.py`
- `tests/protocols/test_http.py`
- `tests/protocols/test_websocket.py`
- `tests/middleware/test_proxy_headers.py`
- `tests/supervisors/test_multiprocess.py`
- `tests/importer/test_importer.py`
- `tests/test_default_headers.py`
- `tests/test_server.py`

## Click Documentation and Source Consulted

- Docs: [Options](https://click.palletsprojects.com/en/stable/options/)
- Docs: [Commands and Groups](https://click.palletsprojects.com/en/stable/commands-and-groups/)
- Source: `src/click/core.py`

## Scope Notes

- Palfrey is a clean-room runtime and does not import Uvicorn at runtime.
- Rows above indicate current status as of this repository snapshot, not target status.

## Confirmed Gaps (Source-Mapped)

- Uvicorn maps `--http` to concrete protocol engines (`h11` / `httptools`) with distinct implementations.
  - Sources: `uvicorn/config.py`, `uvicorn/protocols/http/h11_impl.py`, `uvicorn/protocols/http/httptools_impl.py`.
- Uvicorn maps `--ws` to concrete protocol engines (`websockets`, `websockets-sansio`, `wsproto`) with distinct implementations.
  - Sources: `uvicorn/config.py`, `uvicorn/protocols/websockets/websockets_impl.py`, `uvicorn/protocols/websockets/websockets_sansio_impl.py`, `uvicorn/protocols/websockets/wsproto_impl.py`.
- Logging config formats: Uvicorn supports JSON, YAML/YML, and INI/fileConfig paths.
  - Source: `uvicorn/config.py` (`configure_logging` path handling).
