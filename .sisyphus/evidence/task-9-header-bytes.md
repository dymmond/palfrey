# Task 9 Manual QA — Header Bytes Pipeline

Scenario: Start Palfrey with a scope-header echo app, send custom headers, verify bytes are preserved in `scope["headers"]`.

Command:

```bash
hatch run python -m palfrey tests.fixtures.header_echo_app:app --host 127.0.0.1 --port 18903
curl -H "X-Custom: TestValue" -H "X-Binary: café" http://127.0.0.1:18903
```

Response body (`hex(name):hex(value)` for each `scope["headers"]` tuple):

```
686f7374:3132372e302e302e313a3138393033
757365722d6167656e74:6375726c2f382e372e31
616363657074:2a2f2a
782d637573746f6d:5465737456616c7565
782d62696e617279:636166c3a9
```

Decoded evidence:

- `782d637573746f6d` → `x-custom`, value `5465737456616c7565` → `TestValue`
- `782d62696e617279` → `x-binary`, value `636166c3a9` → UTF-8 bytes for `café`

Result: headers are lowercased and carried as bytes through request parsing into ASGI scope.
