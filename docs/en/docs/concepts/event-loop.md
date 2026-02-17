# Event Loop

Palfrey loop modes follow Uvicorn's documented option values:

- `none`
- `auto`
- `asyncio`
- `uvloop`

## Behavior

- `uvloop`: installs uvloop policy; raises import error if unavailable.
- `auto`: tries uvloop first, otherwise uses asyncio defaults.
- `asyncio` / `none`: keep default asyncio loop policy.

## Source mapping

- Uvicorn docs: **Settings** (Implementation section)
- Uvicorn source: `uvicorn/config.py` (`LOOP_SETUPS`)
