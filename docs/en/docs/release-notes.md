# Release Notes

This page provides release navigation and policy.

## Source of truth

Detailed release history is maintained in:

- [`CHANGELOG.md`](https://github.com/dymmond/palfrey/blob/main/CHANGELOG.md)

## Versioning policy

Palfrey follows semantic versioning:

- MAJOR: breaking behavior changes
- MINOR: backward-compatible features
- PATCH: backward-compatible fixes

## Recommended reading order after each release

1. release summary
2. behavior changes
3. migration notes (if any)
4. operational impact notes

## Upgrade checklist

- review changelog entries for your current-to-target range
- run staging smoke tests with production-like config
- validate logs/metrics/health checks after deploy

## Non-technical summary

Release notes answer one question: "What changed, and what should my team do about it?"
