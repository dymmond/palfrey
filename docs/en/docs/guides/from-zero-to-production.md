# Guide: From Zero To Production

This is a full-path rollout guide from local app to managed production deployment.

## Phase 1: Local correctness

- Start with minimal app and deterministic command.
- Confirm health endpoint behavior.
- Add basic error-path checks.

Example probe app:

```python
{!> ../../../docs_src/guides/troubleshooting_healthcheck.py !}
```

## Phase 2: Development ergonomics

- Enable `--reload` for local iteration.
- Keep explicit include/exclude patterns in monorepos.
- Avoid using reload mode in production runbooks.

## Phase 3: Staging hardening

- Run behind reverse proxy with explicit trust config.
- Validate headers, scheme, client IP propagation.
- Set process limits/timeouts intentionally.

## Phase 4: Production process model

- Use worker mode for CPU scaling and fault isolation.
- Set `--limit-max-requests` if you want controlled worker recycling.
- Keep startup command and rollback command versioned.

## Phase 5: Post-deploy verification

- Verify `/healthz` and critical business endpoints.
- Verify logs/metrics ingestion.
- Run lightweight traffic replay or synthetic checks.

## Non-Technical rollout checklist

- Owner and rollback contact assigned.
- Canary scope and duration defined.
- Success criteria and abort criteria documented before deploy.
