# Release Process

This process keeps releases auditable and predictable.

## 1. Validate locally

Run all quality gates:

```bash
task lint
task format-check
task check-types
task test
hatch run docs-build
```

## 2. Prepare version and changelog

- bump version with semantic versioning rules
- update `CHANGELOG.md`
- verify docs mention new user-visible behavior

## 3. Cut release

1. create tag `vX.Y.Z`
2. push tag
3. run publish workflow

## 4. Post-release verification

- install released artifact in clean environment
- run startup smoke tests
- verify docs links and release note references

## 5. If issues are found

- patch forward with next patch release
- document root cause and mitigation in changelog
- avoid rewriting published artifacts

## Non-technical summary

A release process is a safety system.
It reduces the chance that urgent fixes introduce new outages.
