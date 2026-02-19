# Logging

Palfrey supports built-in logging and external logging configuration files.

## Supported levels

- `critical`
- `error`
- `warning`
- `info`
- `debug`
- `trace`

CLI examples:

```bash
palfrey myapp.main:app --log-level info
palfrey myapp.main:app --log-level debug --access-log
```

## Configuration inputs

- JSON/YAML file for `logging.config.dictConfig`
- INI-style file for `logging.config.fileConfig`

Programmatic JSON config example:

```python
{!> ../../../docs_src/reference/logging_json.py !}
```

Equivalent CLI:

```bash
palfrey myapp.main:app --log-config logging.json
```

## Access log control

```bash
palfrey myapp.main:app --no-access-log
```

## Practical production guidance

- include request IDs/trace IDs in app or middleware logs
- use structured logs for machine processing
- keep access and error logs distinct
- validate log ingestion after each release

## Common logging issues

- wrong path passed to `--log-config`
- YAML config without `PyYAML`
- level mismatch between root logger and named loggers

## Plain-language summary

Good logs are how teams reconstruct what happened during incidents.
Treat logging configuration as production-critical code.
