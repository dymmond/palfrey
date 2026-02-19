# Contributing

Thank you for contributing to Palfrey.

Contributions are welcome across code, docs, tests, benchmarks, and issue triage.

## Ways to help

- report bugs with clear reproduction steps
- improve docs and examples
- add tests for uncovered behavior
- improve performance with reproducible benchmarks
- review pull requests and discussions

## Before opening work

Start with a discussion or issue when possible, especially for behavior changes.

Please include:

- platform and Python version
- exact command used
- full traceback/log output
- minimal reproduction code

## Development setup

```bash
git clone https://github.com/dymmond/palfrey
cd palfrey
pip install hatch
hatch env create
hatch env create test
hatch env create docs
```

## Quality gates

Run before opening a PR:

```bash
task lint
task format-check
task check-types
task test
hatch run docs-build
```

## Tests

```bash
hatch run test:test
```

Single test example:

```bash
hatch run test:test tests/protocols/test_websocket_protocol.py
```

## Documentation workflow

Docs live under `docs/en/docs`.
Runnable examples live under `docs_src` and are included in docs pages.

Build docs:

```bash
hatch run docs-build
```

## Pull request checklist

- behavior is covered by tests
- docs are updated for user-visible changes
- benchmark claims include reproducible commands/results
- changelog entry added when appropriate

## Code review expectations

Focus areas:

- correctness and regressions
- compatibility behavior
- operational safety
- clarity and maintainability

## Community standards

- be respectful and precise
- assume good intent
- keep feedback actionable

## Non-technical summary

Contribution quality matters more than contribution size.
Small, well-tested improvements are highly valuable.
