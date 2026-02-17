# Release Process

## 1. Run required gates

```bash
hatch run lint
hatch run check-types
hatch run test-cov
hatch run docs-build
```

## 2. Update release metadata

- Bump `palfrey/__init__.py` version using semantic versioning.
- Add release notes to `CHANGELOG.md`.

## 3. Publish

- Tag the release (`vX.Y.Z` or `X.Y.Z` according to project policy).
- Push tag and verify GitHub Actions publish workflow.

## 4. Verify artifacts

- Package available on distribution channel.
- Docs build/deployment healthy.
- Benchmark docs updated for the release.
