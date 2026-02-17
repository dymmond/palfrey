# Lifespan

Palfrey supports ASGI lifespan startup/shutdown messaging.

## Modes

- `auto`
- `on`
- `off`

## Runtime behavior

When lifespan is enabled, Palfrey starts a dedicated lifespan manager task before accepting traffic and performs
coordinated shutdown after the listener closes.

## Related tests

- `tests/runtime/test_lifespan.py`
