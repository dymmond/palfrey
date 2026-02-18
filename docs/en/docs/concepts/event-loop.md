# Event Loop

The event loop decides how asynchronous work is scheduled.

## Why it matters

- Throughput under concurrent load.
- Latency stability.
- Compatibility with target platform/runtime.

## Loop Modes

Palfrey exposes these loop modes:

- `auto`: prefer `uvloop` when available, otherwise use default asyncio.
- `asyncio`: always use default asyncio policy.
- `uvloop`: require uvloop and install uvloop policy.
- `none`: do not modify loop policy.

CLI examples:

```bash
palfrey myapp.main:app --loop auto
palfrey myapp.main:app --loop uvloop
palfrey myapp.main:app --loop asyncio
```

## Choosing For Teams

- Start with `auto` unless policy/compliance says otherwise.
- Use explicit `asyncio` when debugging environment-specific loop behavior.
- Use explicit `uvloop` when you require deterministic uvloop usage.

## Non-Technical explanation

Think of the loop as the dispatcher deciding which conversation proceeds next.
A better dispatcher can handle more conversations smoothly with the same hardware.

## Engineering caution

- Benchmark on your own workload before freezing loop choice.
- Validate behavior on each deployment target OS and Python version.
- Keep loop configuration explicit in production startup scripts.
