# Contributing

PyUARTSI uses Python 3.10 as its minimum supported interpreter and tests every
supported minor release through Python 3.14. Install uv, clone the repository,
and create the locked development environment:

```console
uv sync --locked
```

Before opening a pull request, run the same checks used by CI:

```console
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
uv build --no-sources
```

Use `uv run ruff format .` to apply formatting. Add tests for every behavior
change. Tests marked `hardware` require a connected target and are excluded
from the default deterministic unit-test suite.

Run the non-destructive hardware read smoke test only after choosing a safe
target address:

```console
PYUARTSI_TEST_PORT=/dev/ttyUSB0 \
PYUARTSI_TEST_ADDRESS=0x80000000 \
uv run pytest -o addopts="--strict-config --strict-markers" -m hardware
```

On PowerShell, set the same environment variables with `$env:` before running
the pytest command.

CI also resolves the declared lower bounds with uv's `lowest-direct` strategy
on Python 3.10. This makes every runtime minimum an exercised compatibility
claim rather than an arbitrary metadata value.

Runtime requirements belong in `[project.dependencies]`. Test, lint, and type
checker requirements belong in the corresponding PEP 735 dependency group.
Update dependencies with `uv add` and commit the resulting `uv.lock` change.

Public API changes require documentation and a changelog entry. Preserve a
compatibility alias or use a deprecation cycle when practical.
