# Platform Notes

This page calls out platform-specific behavior that teams should document in runbooks.

## Linux

- strong support for common production deployment patterns
- UNIX socket workflows are typically available
- signal handling model is generally full-featured

## macOS

- useful for development and performance comparison
- verify parity with Linux before production assumptions

## Windows

- some UNIX socket and signal APIs differ from Unix platforms
- prefer host/port bind modes unless UNIX socket support is validated
- validate service manager/signal behavior in native Windows CI

## Cross-platform checklist

- run tests on each supported platform
- keep startup commands platform-aware
- avoid assumptions about unavailable socket/signal APIs
- keep CI matrix aligned with production targets

## Non-technical summary

Different operating systems expose different low-level capabilities.
Portable operations require validating assumptions per platform.
