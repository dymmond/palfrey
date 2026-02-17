# Parity Matrix

This matrix lists Palfrey behaviors grounded in explicit Uvicorn/Click sources.

| Area | Palfrey Status | Uvicorn Docs Source | Uvicorn Source Paths | Click Source |
| --- | --- | --- | --- | --- |
| CLI command surface | Implemented with matching option names and value domains | "Settings" ([uvicorn.dev/settings](https://uvicorn.dev/settings/)) | `uvicorn/main.py` | `src/click/core.py` |
| App import + factory semantics | Implemented (`module:attr`, `--factory`) | "Settings" (Application) | `uvicorn/config.py`, `uvicorn/main.py` | `src/click/core.py` |
| Loop setup modes (`none`, `auto`, `asyncio`, `uvloop`) | Implemented | "Settings" (Implementation) | `uvicorn/config.py` (`LOOP_SETUPS`) |  |
| HTTP implementation option values (`auto`, `h11`, `httptools`) | Implemented option parity | "Settings" (Implementation) | `uvicorn/config.py` (`HTTP_PROTOCOLS`) |  |
| WebSocket implementation option values (`auto`, `none`, `websockets`, `wsproto`) | Implemented option parity | "Settings" + "Concepts: WebSockets" ([uvicorn.dev/concepts/websockets](https://uvicorn.dev/concepts/websockets/)) | `uvicorn/config.py` (`WS_PROTOCOLS`) |  |
| Lifespan modes (`auto`, `on`, `off`) | Implemented | "Concepts: Lifespan" ([uvicorn.dev/concepts/lifespan](https://uvicorn.dev/concepts/lifespan/)) | `uvicorn/config.py`, `uvicorn/server.py` |  |
| Proxy headers behavior | Implemented middleware | "Deployment" (Proxies and forwarded headers) ([uvicorn.dev/deployment](https://uvicorn.dev/deployment/)) | `uvicorn/middleware/proxy_headers.py` |  |
| ASGI message logger behavior | Implemented middleware | n/a (source-driven) | `uvicorn/middleware/message_logger.py` |  |
| Worker supervision behavior | Implemented | "Deployment" | `uvicorn/supervisors/multiprocess.py`, `uvicorn/supervisors/process.py` |  |
| Reload supervision behavior and options | Implemented | "Settings" (Development) | `uvicorn/supervisors/basereload.py`, `uvicorn/supervisors/statreload.py`, `uvicorn/supervisors/watchfilesreload.py` |  |
| TLS option surface | Implemented option parity | "Settings" (HTTPS) | `uvicorn/main.py`, `uvicorn/config.py` |  |
| Logging option surface | Implemented option parity | "Settings" (Logging) | `uvicorn/main.py`, `uvicorn/config.py` |  |
| Interface adapters (`asgi3`, `asgi2`, `wsgi`) | Implemented | "Settings" (Application Interface) | `uvicorn/config.py` |  |
| Keep-alive + header defaults | Implemented | "Server Behavior" ([uvicorn.dev/server-behavior](https://uvicorn.dev/server-behavior/)) | `uvicorn/server.py`, `uvicorn/protocols/http/*` |  |

## Uvicorn Test Pattern Sources Consulted

- `tests/test_cli.py`
- `tests/test_config.py`
- `tests/protocols/test_http.py`
- `tests/protocols/test_websocket.py`
- `tests/middleware/test_proxy_headers.py`
- `tests/supervisors/test_multiprocess.py`

## Click Documentation and Source Consulted

- Docs: [Options](https://click.palletsprojects.com/en/stable/options/)
- Docs: [Commands and Groups](https://click.palletsprojects.com/en/stable/commands-and-groups/)
- Source: `src/click/core.py`

## Scope Notes

- Palfrey is a clean-room runtime and does not import Uvicorn at runtime.
- Rows above indicate feature/option parity, not byte-for-byte implementation identity.
