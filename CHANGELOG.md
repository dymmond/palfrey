# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-02-17

### Added

- Added loop strategy modules (`auto`, `asyncio`, `uvloop`, `none`) and runtime mapping.
- Added middleware modules for proxy headers and ASGI message logging.
- Added deeper HTTP parsing behavior, including chunked request-body support and `100-continue`.
- Added stricter WebSocket handshake/frame validation and fragmented frame handling.
- Added expanded test suite domains (`config`, `loops`, `middleware`, `protocols`, `runtime`, `server`, `supervisors`, `cli`) with substantially broader coverage.
- Added richer docs organization under `docs/en/docs` with concept/reference/operations sections and runnable `../../../docs_src/` examples.
- Added importer parity behaviors aligned with Uvicorn: dotted attribute traversal and non-masked nested import failures.
- Added Click error surface hardening so expected startup/import failures render clean `Error:` output without traceback noise.
- Added parity-focused test suites modeled from Uvicorn coverage patterns, increasing Palfrey test functions beyond the local Uvicorn test-function count baseline.

### Changed

- Updated docs navigation and content structure for release-grade organization.
- Increased coverage gate target to 85%.
- Updated semantic version from `0.2.0` to `0.3.0`.
- Updated runtime reload/worker interaction to match Uvicorn expectation that `workers` is ignored when reload is enabled.
- Updated docs build script to use MkDocs strict mode.
- Updated server access-log request line formatting to include query string and HTTP version.

### Fixed

- Corrected worker/env default normalization to follow Uvicorn-style expectations (`WEB_CONCURRENCY`, `FORWARDED_ALLOW_IPS`).
- Corrected default-response header precedence so configured custom `server`/`date` headers suppress default injection.
- Corrected logging config file-path handling for JSON, YAML/YML, and INI/fileConfig parity branches.

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
