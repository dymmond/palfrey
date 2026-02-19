# Observability

Observability makes runtime behavior visible enough to debug quickly.

## Three pillars to implement

- logs
- metrics
- traces (or at minimum request IDs)

## Logging baseline

- structured logs in production
- request IDs in every app log line
- access logs enabled where auditability is required

## Metrics baseline

Track at least:

- request rate
- error rate
- p50/p95/p99 latency
- active connections
- worker restarts

## Tracing/request correlation

If full tracing is unavailable, add request ID middleware and propagate ID in headers/logs.

## Alerting priorities

- sustained error-rate increase
- latency SLO violation
- repeated worker crash loops
- health endpoint failures

## Non-technical summary

Observability is how teams answer three incident questions quickly:

- what is broken
- how bad it is
- where to act first
