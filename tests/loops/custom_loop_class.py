from __future__ import annotations

import asyncio


class CustomLoop(asyncio.SelectorEventLoop):
    """Test-only selector event loop subclass."""
