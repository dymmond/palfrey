from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BenchmarkCommand:
    """Represents one benchmark invocation."""

    target: str
    requests: int
    concurrency: int

    def render(self) -> str:
        """Render command line suitable for local runs."""
        return f"python -m benchmarks.run --target {self.target} --requests {self.requests} --concurrency {self.concurrency}"


print(BenchmarkCommand(target="palfrey", requests=100_000, concurrency=200).render())
