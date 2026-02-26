# Release Notes

## 0.1.3

#### Added

* **Single-Chunk Optimization:** Implemented logic to automatically inject `Content-Length` headers for single-chunk ASGI responses, significantly reducing the overhead of HTTP chunked transfer framing for standard API calls.
* **In-Flight Chunk Framing:** Refactored the HTTP/1.1 response engine to apply byte-framing (hex size + CRLF) during the transmission phase, enabling true streaming without post-processing delays.
* **Legacy WSGI Support:** Added the mandatory `write()` callable return to `start_response` in the `WSGIAdapter` to ensure compatibility with older synchronous Python web frameworks.

#### Changed

* **Zero-Copy Serialization:** Overhauled `encode_http_response` and `_serialize_http_request` to use C-level byte concatenation (`b"".join`), eliminating the high memory and CPU cost of intermediate Unicode string allocations.
* **Synchronous Slot Tracking:** Converted request concurrency tracking from `asyncio.Lock` to a high-performance synchronous counter, removing a task-scheduling bottleneck on every incoming request.
* **Protocol Accuracy:** Updated `_build_wsgi_environ` to decode query strings via `latin-1` per PEP 3333, preventing server crashes on raw or non-ASCII byte sequences in URLs.

#### Fixed

* **WSGI Compliance:** Re-mapped `wsgi.errors` to `sys.stderr` and ensured `REMOTE_ADDR` fallbacks are provided to prevent `KeyError` crashes in standard WSGI frameworks like Django.
* **HEAD Request Handling:** Fixed a `500 Internal Server Error` where `HEAD` requests would fail validation due to missing body content; the state machine now correctly suppresses body validation for the `HEAD` method.
* **State Machine Integrity:** Enforced strict ASGI event sequencing in the HTTP handler, preventing common violations such as sending body data before response start or duplicate header transmission.

#### Security

* **Memory Exhaustion Protection:** Replaced unbounded in-memory request buffering with `tempfile.SpooledTemporaryFile` in the `WSGIAdapter`, automatically spilling payloads exceeding 1MB to disk to prevent OOM (Out Of Memory) attacks.

## 0.1.2

### Highlights

- Startup logs now follow the familiar style flow while keeping Palfrey wording.
- Runtime mode details are emitted at startup so operators can verify effective protocol choices immediately.
- Listener endpoint logs are clearer across TCP, IPv6, UNIX sockets, and HTTP/3 startup paths.

### Added

- Startup runtime summary:
    - `loop` backend in use
    - effective `http` backend
    - effective `ws` backend
    - configured lifespan mode
    - selected application interface mode

### Changed

- Startup endpoint lines now use normalized URL-like output where possible.
- IPv6 startup targets are formatted with brackets for readability and copy/paste correctness.
- Duplicate startup endpoint lines are deduplicated when multiple server objects expose the same listener.

### Operational impact

- Better startup observability for local development, containers, and production logs.
- Faster validation of effective runtime behavior during deploys and rollouts.
- No breaking CLI changes and no default behavior changes to protocol selection.

## 0.1.1

### Fixed

- Reload child process spawning now uses a canonical Palfrey command path when the parent process was started by a non-Palfrey wrapper CLI.
- `--fd` handling during reload restarts is now deduplicated and reapplied safely, avoiding repeated invalid option propagation.
- Runtime reload supervisor invocation now passes full config context when building child argv, improving reliability across launch environments.

### Operational impact

- Reload mode is now stable in embedded/wrapper launch flows where process argv does not directly represent a native Palfrey invocation.
- No change to default protocol modes or runtime defaults.

## 0.1.0

This is the first public release of Palfrey.

Palfrey launches as a clean-room ASGI server with familiar runtime ergonomics, strong operational controls,
and an upgrade path beyond HTTP/1.1 through opt-in HTTP/2 and HTTP/3 modes.

### Highlights

- Uvicorn-style CLI surface with Click.
- Production-ready HTTP/1.1 + WebSocket + lifespan runtime.
- Process models for single-process, worker mode, reload mode, and Gunicorn worker integration.
- Opt-in HTTP/2 (`--http h2`) support.
- Opt-in HTTP/3/QUIC (`--http h3`) support.
- Structured, expanded documentation across getting started, reference, guides, and operations.

### Core Capabilities Included

- Protocols:
  - HTTP/1.1 (`h11`, `httptools`)
  - WebSockets (`websockets`, `websockets-sansio`, `wsproto`)
  - Lifespan startup/shutdown
  - HTTP/2 (opt-in)
  - HTTP/3 (opt-in)
- Runtime controls:
  - keep-alive, concurrency limits, request limits, graceful shutdown
  - proxy header trust controls
  - TLS and logging configuration
- Deployment options:
  - host/port, UDS, FD binding (where applicable)
  - multi-worker process model
  - Gunicorn integration via `palfrey.workers.PalfreyWorker`

### Installation Profiles

- Minimal:
  - `pip install palfrey`
- Standard extras:
  - `pip install "palfrey[standard]"`
- HTTP/2:
  - `pip install "palfrey[http2]"`
- HTTP/3:
  - `pip install "palfrey[http3]"`

### First-Release Operational Notes

- Defaults stay stable and conservative:
  - `--http auto` remains HTTP/1.1 backend selection.
- HTTP/3 mode requirements:
  - requires `--ssl-certfile` and `--ssl-keyfile`
  - runs over UDP/QUIC
  - does not use `--fd` or `--uds`
  - websocket runtime is disabled in HTTP/3 mode

### Quick Start Commands

```bash
palfrey main:app --host 127.0.0.1 --port 8000
```

```bash
palfrey main:app --http h2 --host 127.0.0.1 --port 8000
```

```bash
palfrey main:app --http h3 --ws none --host 127.0.0.1 --port 8443 --ssl-certfile cert.pem --ssl-keyfile key.pem
```
