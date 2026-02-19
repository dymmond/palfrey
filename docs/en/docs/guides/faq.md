# FAQ

## Is Palfrey a drop-in replacement for Uvicorn?

Palfrey is built for Uvicorn-compatible operational behavior and CLI shape in covered paths.
Use staging validation for your exact workload and options.

## Should I use reload and workers together?

Treat them as separate modes:

- reload for development
- workers for production scale

## Which loop should I use?

Default to `--loop auto` unless you need strict platform-specific reproducibility.

## Which websocket mode should I use?

Start with default mode unless you have a measured reason to pin a specific backend.

## How do I run behind a reverse proxy?

Enable `--proxy-headers` and set `--forwarded-allow-ips` to trusted proxy sources.

## How do I improve performance safely?

- benchmark your own workload
- change one runtime variable at a time
- keep benchmark commands and environment details versioned

## How do I run Palfrey in Python code?

Use programmatic startup patterns from quickstart/reference pages.

## Where do I report bugs?

Use the project issue tracker with reproducible command, environment, and traceback details.

## Non-technical summary

FAQ answers are decision shortcuts.
Use them to pick a safe default, then validate in your own environment.
