# Parity Matrix

This matrix records Palfrey behavior mapped to Uvicorn/Click sources.

| Capability | Palfrey status | Uvicorn docs source | Uvicorn repo source |
| --- | --- | --- | --- |
| CLI option names and argument surface | Implemented with matching option names | "Settings" ([uvicorn.dev/settings](https://uvicorn.dev/settings/)) | `uvicorn/main.py` |
| Host/port/UDS/fd binding | Implemented | "Settings" (Socket Binding) | `uvicorn/main.py`, `uvicorn/config.py`, `uvicorn/server.py` |
| Reload mode and watch controls | Implemented (polling reloader) | "Settings" (Development) | `uvicorn/main.py`, `uvicorn/supervisors/statreload.py`, `uvicorn/supervisors/watchfilesreload.py` |
| Worker process supervision | Implemented | "Deployment" ([uvicorn.dev/deployment](https://uvicorn.dev/deployment/)) | `uvicorn/main.py`, `uvicorn/supervisors/multiprocess.py` |
| HTTP protocol selection flags | Implemented flag parity (`auto`, `h11`, `httptools`) | "Settings" (Implementation) | `uvicorn/main.py`, `uvicorn/config.py`, `uvicorn/protocols/http/h11_impl.py`, `uvicorn/protocols/http/httptools_impl.py` |
| WebSocket protocol selection flags | Implemented flag parity (`auto`, `none`, `websockets`, `wsproto`) | "Concepts: WebSockets" ([uvicorn.dev/concepts/websockets](https://uvicorn.dev/concepts/websockets/)) | `uvicorn/main.py`, `uvicorn/config.py`, `uvicorn/protocols/websockets/websockets_impl.py` |
| Lifespan modes (`auto`, `on`, `off`) | Implemented | "Concepts: Lifespan" ([uvicorn.dev/concepts/lifespan](https://uvicorn.dev/concepts/lifespan/)) | `uvicorn/main.py`, `uvicorn/config.py`, `uvicorn/server.py` |
| Logging/TLS/proxy headers options | Implemented | "Settings" (Logging, HTTPS), "Deployment" (Proxies) | `uvicorn/main.py`, `uvicorn/config.py`, `uvicorn/middleware/proxy_headers.py` |
| Interface modes (`asgi3`, `asgi2`, `wsgi`) | Implemented with adapters | "Settings" (Application Interface) | `uvicorn/main.py`, `uvicorn/config.py` |
| Click command semantics | Implemented with Click command/options decorators | Click docs: "Options", "Commands and Groups" ([click.palletsprojects.com](https://click.palletsprojects.com/en/stable/options/)) | Click repo: `src/click/core.py` |

## Notes

- Palfrey is a clean-room runtime and does not import Uvicorn.
- Features in this matrix are constrained to confirmed source references only.
