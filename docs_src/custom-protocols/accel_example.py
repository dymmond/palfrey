import os

# Acceleration shim pattern
try:
    # Try to import from the compiled Rust extension
    from palfrey_rust import fast_my_logic as _fast_my_logic

    HAS_RUST_EXTENSION = True
except ImportError:
    HAS_RUST_EXTENSION = False
    _fast_my_logic = None


def my_logic(data: bytes) -> bytes:
    """
    Example of a performance-critical function with a Rust accelerator.

    If the Rust extension is available and not disabled by environment,
    it uses the optimized implementation. Otherwise, it falls back to
    pure Python.
    """
    if HAS_RUST_EXTENSION and _fast_my_logic is not None and not os.getenv("PALFREY_NO_RUST"):
        return _fast_my_logic(data)

    # Pure Python fallback
    return data.lower().strip()
