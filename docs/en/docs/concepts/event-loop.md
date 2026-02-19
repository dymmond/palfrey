# Event Loop

The event loop drives all asynchronous behavior.

## Loop Modes in Palfrey

- `auto`: uses `uvloop` if available, else asyncio default
- `asyncio`: explicit default asyncio behavior
- `uvloop`: explicit uvloop behavior
- `none`: do not alter loop configuration

## How to choose

## For most teams

Use `--loop auto`.

## For strict reproducibility

Use explicit loop mode in production runbooks (`asyncio` or `uvloop`).

## For debugging platform issues

Use `--loop asyncio` to eliminate loop implementation variability.

## Verification checklist

- benchmark your own payloads and concurrency
- validate behavior on each target OS
- capture loop mode in incident reports

## Performance considerations

Loop choice can change:

- tail latency behavior
- CPU efficiency under concurrent I/O
- behavior of some third-party async libraries

## Plain-language explanation

Think of the loop as an air traffic controller for async operations.
Different controllers can improve throughput and smoothness under load.
