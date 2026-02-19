# Capacity Planning

Capacity planning prevents guesswork and avoids scaling by panic.

## Inputs you need

- expected requests/sec and websocket concurrency
- payload size profiles
- target latency SLO
- available CPU/memory budget

## Baseline process

1. run representative load tests
2. capture throughput and p95/p99 latency
3. inspect CPU and memory saturation points
4. test failure and recovery behavior

## Tuning levers in Palfrey

- worker count
- concurrency limit
- keep-alive timeout
- protocol backend mode choices

## Planning workflow example

```python
{!> ../../../docs_src/operations/benchmark_plan.py !}
```

## Practical guardrails

- change one variable at a time
- keep benchmark command + environment details in version control
- prefer repeatable tests over single "hero" numbers

## Non-technical summary

Capacity planning is budgeting for runtime behavior before incidents force emergency changes.
