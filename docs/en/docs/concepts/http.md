# HTTP

Palfrey implements HTTP/1.1 request parsing and ASGI HTTP scope execution.

## Implemented behavior

- Request-line and header parsing with size limits.
- `Content-Length` request body handling.
- `Transfer-Encoding: chunked` request body handling.
- `Expect: 100-continue` interim response support.
- Connection keep-alive decision handling (`Connection` headers + HTTP version).
- Default `server` and `date` headers, with config toggles.

## Related tests

- `tests/protocols/test_http_parser.py`
- `tests/protocols/test_http_response.py`
- `tests/integration/test_http_integration.py`
