# Task 8 Keep-Alive / Chunked Regression Evidence

Manual curl verification against a temporary local app:

## Keep-Alive headers

`/small` response:

```
HTTP/1.1 200 OK
content-type: text/plain
content-length: 2
date: Wed, 11 Mar 2026 13:58:01 GMT
server: palfrey
connection: keep-alive
```

`/empty` response:

```
HTTP/1.1 204 No Content
date: Wed, 11 Mar 2026 13:58:01 GMT
server: palfrey
content-length: 0
connection: keep-alive
```

## Chunked framing

`/chunked` raw response:

```
HTTP/1.1 200 OK
content-type: text/plain
transfer-encoding: chunked
date: Wed, 11 Mar 2026 13:58:01 GMT
server: palfrey
connection: keep-alive

3
abc
3
def
0
```

Automated regression coverage:

- `test_encode_http_response_chunks_chunked_frames_are_individual_parts`
- `test_write_response_streams_with_writelines_and_preserves_keep_alive_header`
