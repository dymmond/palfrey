CALLED = False


def setup_loop() -> None:
    """Mark that custom loop setup was invoked."""

    global CALLED
    CALLED = True
