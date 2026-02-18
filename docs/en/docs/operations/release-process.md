# Release Process

This process is designed for predictable and auditable open-source releases.

## 1. Pre-release checks

```bash
task lint
task format-check
task check-types
task test
hatch run docs-build
```

## 2. Version and changelog

- Update version in `pyproject.toml` using semantic versioning.
- Add release entries to `CHANGELOG.md`.
- Ensure notable behavior changes are documented.

## 3. Tag and publish

1. Create signed tag `vX.Y.Z`.
2. Push tag to origin.
3. Publish package artifacts from CI/release workflow.

## 4. Post-release validation

- install published artifact in a clean environment
- run basic startup and protocol smoke checks
- verify docs and release notes links

## 5. Roll-forward policy

If release issues are found:

- patch forward with `X.Y.(Z+1)`
- document root cause and mitigation in changelog
- avoid force-changing published artifacts
