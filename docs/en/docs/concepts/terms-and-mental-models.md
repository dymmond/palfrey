# Terms and Mental Models

This page defines key terms in plain language first, then technical language.

## ASGI

- Plain language: A contract between your app and the server.
- Technical meaning: Async callable with `(scope, receive, send)` plus protocol-specific message flow.

## Scope

- Plain language: Context envelope for one connection.
- Technical meaning: Immutable-ish metadata dict with protocol type, path, headers, client/server endpoints.

## Event Loop

- Plain language: The runtime scheduler for async work.
- Technical meaning: Cooperative I/O loop that advances coroutines and network transports.

## Lifespan

- Plain language: Startup and shutdown hooks.
- Technical meaning: ASGI lifespan message channel (`lifespan.startup`, `lifespan.shutdown`).

## Worker

- Plain language: A separate process handling traffic.
- Technical meaning: Child process supervised by a parent, each with isolated memory and event loop.

## Reload Mode

- Plain language: Auto-restart when files change.
- Technical meaning: Parent watcher process re-spawns a child serving process on matching file changes.

## Proxy Headers

- Plain language: Upstream-provided client/scheme metadata.
- Technical meaning: `X-Forwarded-*` interpretation gated by trusted source list.

## Two Practical Mental Models

## Restaurant model (non-technical)

- Palfrey is front-of-house traffic control.
- Your app is the kitchen.
- Event loop is the order dispatcher.
- Workers are extra kitchens.

## Queue model (engineering)

- Socket accepts work.
- Parser transforms bytes to protocol events.
- App consumes/produces ASGI events.
- Encoder writes response bytes.
- Supervisor enforces process lifecycle.

## Why this matters

Using shared terminology reduces miscommunication between product, platform, and backend teams during incidents and deployments.
