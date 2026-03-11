# Task 8 Large Body Streaming Evidence

Manual verification run used a temporary app serving a `70000`-byte body with explicit `Content-Length`.

Observed response headers from curl:

```
HTTP/1.1 200 OK
content-type: application/octet-stream
content-length: 70000
date: Wed, 11 Mar 2026 13:58:01 GMT
server: palfrey
connection: keep-alive
```

Implementation evidence:

- `palfrey/protocols/http.py` now exposes `encode_http_response_chunks()` to stream status line, headers, and body parts as an iterable of bytes.
- `palfrey/server.py::_write_response()` now prefers `writer.writelines(payload_chunks)` and falls back to iterative `writer.write(chunk)` when `writelines` is unavailable (test doubles).
- New test `test_encode_http_response_chunks_large_body_preserves_chunk_reference` asserts original large body chunk object identity is preserved in streamed parts (no full-body join copy in the write path).
