# Error Catalog

This page maps common startup/runtime failures to likely causes and actions.

## Import and app resolution

## `Unable to import module '...'`

Likely causes:

- wrong `module:attribute` target
- wrong working directory
- missing dependency/module in environment

Actions:

- verify import target spelling
- run with `--app-dir` when needed
- confirm active virtual environment

## Factory and callable errors

## app factory returns invalid object

Likely causes:

- `--factory` used on non-factory target
- factory returns non-ASGI callable

Actions:

- validate target manually in Python shell
- confirm signature and return value

## Protocol and handshake errors

## websocket handshake failed

Likely causes:

- missing upgrade headers
- proxy not forwarding websocket upgrade
- unsupported/misconfigured ws backend mode

Actions:

- test direct connection bypassing proxy
- verify proxy websocket forwarding settings
- verify selected `--ws` backend dependencies

## Networking and bind errors

## address already in use

Likely causes:

- existing process bound to host/port
- orphan process from previous run

Actions:

- identify and stop conflicting process
- choose a free port

## UNIX socket not supported

Likely causes:

- platform lacks UNIX socket support

Actions:

- use host/port bind mode instead

## Runtime and shutdown behavior

## graceful shutdown timeout exceeded

Likely causes:

- long-running handlers not finishing
- external dependencies hanging

Actions:

- raise timeout or optimize handler shutdown path
- add instrumentation around shutdown duration

## Log configuration load errors

Likely causes:

- invalid file format/content
- missing YAML dependency for `.yaml` file

Actions:

- validate config file
- install required parsing dependency

## Plain-language summary

Most runtime failures are configuration mismatches, not code defects.
Capture command, version, and logs first; then narrow by category.
