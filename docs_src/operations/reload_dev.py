from __future__ import annotations

command = [
    "palfrey",
    "docs_src.getting_started.hello_world:app",
    "--reload",
    "--reload-dir",
    "./src",
    "--reload-include",
    "*.py",
]

print(" ".join(command))
