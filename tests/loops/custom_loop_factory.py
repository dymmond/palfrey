"""Test fixture module for custom loop setup import-string resolution."""

CALLED = False


def setup_loop() -> None:
    """Mark that custom loop setup was invoked."""

    global CALLED
    CALLED = True
