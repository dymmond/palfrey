# Reload / Development Mode

Reload mode watches files and restarts the serving child process when matching files change.

## Typical command

```python
{!> ../../../docs_src/operations/reload_dev.py !}
```

Equivalent direct CLI:

```bash
palfrey myapp.main:app --reload --reload-dir src --reload-include '*.py'
```

## Pattern controls

- include patterns: `--reload-include`
- exclude patterns: `--reload-exclude`
- scan interval: `--reload-delay`

## Operational boundaries

- Reload mode is for development workflows.
- Worker mode and reload mode are different operational modes.
- Keep production startup scripts free of `--reload`.

## Troubleshooting reload

- verify watched directory is correct
- verify glob patterns match changed files
- verify process has permission to scan watched paths
