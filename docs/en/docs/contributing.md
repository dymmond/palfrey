# Contributing

## Local setup

```bash
pip install hatch
scripts/install
```

## Quality gates

```bash
hatch run lint
hatch run format-check
hatch run check-types
hatch run test-cov
hatch run docs-build
```

## Benchmark and Rust extension

```bash
hatch run rust-build
hatch run benchmark
```

## Test structure

See [Testing Strategy](testing/testing-strategy.md) for test domains and mapping.
