# Terms and Mental Models

This page is a shared vocabulary for engineering, platform, and product teams.

Each term has:

- plain-language meaning
- technical meaning
- why it matters operationally

## ASGI

Plain language:
A standard plug shape between Python web apps and Python servers.

Technical:
An async callable contract using `(scope, receive, send)` and protocol-specific message events.

Why it matters:
It lets teams change server/runtime implementation without rewriting application logic.

## Scope

Plain language:
The envelope describing one connection/request context.

Technical:
A dictionary containing metadata such as protocol, path, query string, headers, client/server addresses, and extensions.

Why it matters:
Middleware, auth, logging, and routing all depend on correct scope data.

## Event Loop

Plain language:
The scheduler deciding which async task gets CPU time next.

Technical:
The core asynchronous I/O runtime that drives coroutine execution and transport callbacks.

Why it matters:
Loop choice impacts latency, throughput, and platform compatibility.

## Lifespan

Plain language:
The app’s opening and closing checklist.

Technical:
ASGI startup/shutdown events (`lifespan.startup`, `lifespan.shutdown`) used to initialize and release resources.

Why it matters:
Reliable startup/shutdown prevents partial boot and dirty termination behavior.

## Worker

Plain language:
A separate server process handling traffic.

Technical:
One child process with its own memory space and event loop, supervised by a parent.

Why it matters:
Workers improve isolation and multi-core utilization.

## Reload Mode

Plain language:
Auto-restart server when source files change.

Technical:
A watcher process respawns the serving child on matching file system events.

Why it matters:
Great for local iteration, wrong for production.

## Backlog

Plain language:
How many incoming connections can wait before being accepted.

Technical:
Kernel-side listen queue limit.

Why it matters:
Small backlog can increase connection failures during spikes.

## Keep-Alive Timeout

Plain language:
How long to keep an idle client connection open for potential reuse.

Technical:
Maximum idle seconds before a persistent HTTP connection is closed.

Why it matters:
Balances resource usage and latency benefits from connection reuse.

## Concurrency Limit

Plain language:
Safety cap on in-flight work.

Technical:
Maximum active connections/tasks before returning `503 Service Unavailable`.

Why it matters:
Prevents collapse under overload; turns a crash into controlled shedding.

## Trusted Proxy Headers

Plain language:
Whether to believe metadata from upstream proxies.

Technical:
Interpret `X-Forwarded-*` only when source IP/range is trusted.

Why it matters:
Incorrect trust config can break security boundaries and audit data.

## Two Practical Mental Models

## Restaurant Model (Non-Technical)

- Palfrey: front-of-house coordinator
- your app: kitchen logic
- event loop: ticket scheduler
- workers: additional kitchens

## Pipeline Model (Technical)

1. socket accepts bytes
2. parser transforms bytes to protocol events
3. app emits ASGI messages
4. encoder writes response bytes
5. supervisor enforces lifecycle policies

## Why this page exists

Incident quality improves when everyone uses the same words for the same behaviors.
