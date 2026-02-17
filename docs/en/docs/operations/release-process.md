# Release Process

## 1. Run quality gates

```bash
hatch run lint
hatch run check-types
hatch run test-cov
hatch run docs-build
```

## 2. Update version and changelog

- Bump `palfrey/__init__.py` semantic version.
- Add release notes to `CHANGELOG.md`.

## 3. Publish

- Create and push release tag.
- Confirm CI workflows are green.
- Trigger publish workflow for package/docs deployment.
