# Logging

Palfrey supports default logging and external logging config files.

## Log levels

Supported runtime levels:

- `critical`
- `error`
- `warning`
- `info`
- `debug`
- `trace`

## Quick examples

```bash
palfrey myapp.main:app --log-level info
palfrey myapp.main:app --log-level trace --access-log
```

## JSON/dictConfig setup

```python
{!> ../../../docs_src/reference/logging_json.py !}
```

Then run:

```bash
palfrey myapp.main:app --log-config logging.json
```

## File formats

- `.json` and `.yaml/.yml` are loaded as dictionary configs.
- Other files are treated as `logging.fileConfig` inputs.

## Access logs

Access logs can be toggled independently:

```bash
palfrey myapp.main:app --no-access-log
```

## Operator notes

- Keep application logs structured in production for searchability.
- Ensure request IDs/trace IDs are included by your application or middleware.
- Treat log format changes as deployment-impacting changes and validate with downstream collectors.
