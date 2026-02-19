# Reload

Reload mode is a development-only process supervisor that restarts the server on file changes.

## Typical command

```python
{!> ../../../docs_src/operations/reload_dev.py !}
```

Equivalent CLI:

```bash
palfrey main:app --reload --reload-dir src --reload-include '*.py'
```

## Controls

- `--reload`
- `--reload-dir` (repeatable)
- `--reload-include` (repeatable)
- `--reload-exclude` (repeatable)
- `--reload-delay`

## Common pattern examples

## Monorepo service folder only

```bash
palfrey main:app --reload --reload-dir services/api
```

## Include templates and Python, exclude generated files

```bash
palfrey main:app \
  --reload \
  --reload-include '*.py' \
  --reload-include '*.jinja2' \
  --reload-exclude '.venv/*' \
  --reload-exclude 'dist/*'
```

## Troubleshooting

- no reload events: check watched path and file patterns
- too many restarts: tune include/exclude and delay
- CPU overhead: narrow watch scope

## Non-technical summary

Reload mode is a productivity feature for development, not a production reliability feature.
