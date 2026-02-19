# Guide: Troubleshooting

Use this page as a fast diagnosis flow.

## Step 1: Capture context first

Always capture:

- exact startup command
- Palfrey and Python version (`palfrey --version`)
- platform
- error logs with timestamps

## Step 2: Identify failure class

## Startup/import failures

Symptoms:

- process exits immediately
- import/module/factory errors

Actions:

- verify `APP` target
- verify working directory or use `--app-dir`
- verify virtual environment dependencies

## Bind/socket failures

Symptoms:

- address in use
- socket path errors

Actions:

- free conflicting process/port
- verify socket permissions/path

## Request/runtime failures

Symptoms:

- 4xx/5xx responses
- slow responses under load

Actions:

- inspect app exception logs
- check concurrency/timeout settings
- verify dependency health (DB/cache/API)

## WebSocket failures

Symptoms:

- handshake rejection
- connection closes immediately

Actions:

- verify upgrade headers end-to-end
- verify proxy websocket forwarding
- test direct server connection

## Reload/worker behavior surprises

Symptoms:

- reload not triggered
- unexpected worker exits

Actions:

- validate include/exclude patterns
- verify process model (`reload` vs `workers`)
- inspect healthcheck and recycle settings

## Reference probe app

```python
{!> ../../../docs_src/guides/troubleshooting_healthcheck.py !}
```

## Incident handoff template

- what happened
- when it started
- impact scope
- current mitigation
- next investigation step

## Plain-language summary

Troubleshooting speed improves when teams classify the problem first, then debug inside the correct category.
