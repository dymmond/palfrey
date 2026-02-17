# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-02-17

### Added

- Implemented Palfrey clean-room runtime modules for ASGI serving.
- Added Click-based CLI with Uvicorn-compatible option names and behavior mapping.
- Added HTTP/1.1 and WebSocket protocol handling, including lifespan event support.
- Added reload supervisor and multi-worker process supervision.
- Added optional Rust acceleration crate for header and request-head parsing.
- Added benchmark harness for Palfrey vs Uvicorn comparisons.
- Added unit and integration tests using pytest and pytest-cov.
- Added mkdocs-material documentation including parity matrix and release process.
- Added CI workflows enforcing lint, Ty checks, coverage-gated tests, and docs builds.

### Changed

- Reworked tooling configuration to use Ty instead of mypy.
- Updated project metadata, scripts, and build configuration for OSS release readiness.

### Fixed

- N/A for this release cycle.
