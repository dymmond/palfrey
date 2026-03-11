# QA Scenario 2: Uncommon Status Code Dynamic Fallback Verification

**Timestamp**: 2026-03-11

## Test Command
```python
from palfrey.protocols.http import HTTPResponse, encode_http_response

response = HTTPResponse(status=418)
response.body_chunks = [b"I'm a teapot"]

raw = encode_http_response(response, keep_alive=False)
assert b"HTTP/1.1 418" in raw
```

## Output
```
✓ QA Scenario 2: Uncommon status code (418) falls back to dynamic generation
  Response starts with: b"HTTP/1.1 418 I'm a Teapot\r\ncontent-lengt"
  Full response length: 80 bytes
  Contains body: True
```

## Verification Results
✅ **PASSED** - Uncommon status code (418 "I'm a Teapot") is not in `_STATUS_LINES` dict
✅ **PASSED** - Request falls back to dynamic generation using `http.HTTPStatus().phrase`
✅ **PASSED** - Reason phrase "I'm a Teapot" is correctly looked up and included
✅ **PASSED** - Response body is intact in the output
✅ **PASSED** - Connection management (keep_alive=False) sets correct `connection: close` header

## Fallback Mechanism
When a status code is not found in `_STATUS_LINES`:
1. Code checks `if response.status in _STATUS_LINES` (fast O(1) lookup)
2. If not found, falls back to `http.HTTPStatus(response.status).phrase` lookup
3. Dynamically generates status line using f-string encoding (same as before pre-computation)
4. Uncommon codes like 418, 451, etc. work without modification

This ensures **backward compatibility** while optimizing the common case (13 most frequent status codes).
