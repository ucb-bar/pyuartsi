![PyUARTSI](https://raw.githubusercontent.com/ucb-bar/pyuartsi/main/assets/banner.png)

# PyUARTSI

PyUARTSI is a typed Python implementation of the UART-based Tethered Serial
Interface (TSI). It can read and write target memory, load ELF files, verify
loaded data, initialize hart 0, and proxy the supported FESVR calls.

PyUARTSI requires Python 3.10 or newer and runs on platforms supported by
[pyserial](https://pyserial.readthedocs.io/).

## Installation

Add PyUARTSI to a uv project:

```console
uv add pyuartsi
```

Or install it with pip:

```console
python -m pip install pyuartsi
```

## Command-line usage

The installed command and module entry point are equivalent:

```console
uv run pyuartsi --help
uv run python -m pyuartsi --help
```

Load and verify an ELF file:

```console
uv run pyuartsi --port COM20 --elf program.elf --load --self-check
```

Read and write target memory:

```console
uv run pyuartsi --port /dev/ttyUSB0 --init-read 0x02000000
uv run pyuartsi --port /dev/ttyUSB0 \
  --init-write 0x80000000=0xdeadbeef \
  --init-read 0x80000000
```

The default serial read and write timeout is 10 seconds. Use `--timeout` to
change it. Underscore spellings of legacy options remain available for
compatibility, but new scripts should use hyphenated options.

## Python API

Use the connection as a context manager so the serial port is always closed:

```python
from pyuartsi import UARTTSI

with UARTTSI("/dev/ttyUSB0", 115_200, timeout=10.0) as tsi:
    tsi.write_word(0x80000000, 0xDEADBEEF)
    assert tsi.read_word(0x80000000) == 0xDEADBEEF
```

All library-specific exceptions inherit from `PyUARTSIError`. Transport
timeouts raise `TransportTimeoutError`, protocol failures raise
`ProtocolError`, and ELF read-back mismatches raise `ELFVerificationError`.

## Development

The repository uses uv for the complete development workflow:

```console
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
uv build --no-sources
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the test matrix and contribution
workflow. Releases follow calendar versioning in the normalized
`YYYY.M.D` form and are recorded in [CHANGELOG.md](CHANGELOG.md).

## Current limitations

- Reset the device under test before launching a new program.
- The minimal FESVR proxy supports `write`, legacy exit, and exit calls.
- Hardware behavior depends on the target's UART TSI implementation.

Please report reproducible defects in the
[issue tracker](https://github.com/ucb-bar/pyuartsi/issues).

## Related implementations

- [C++ UART TSI](https://github.com/ucb-bar/testchipip/tree/master/uart_tsi)
- [Rust TSI](https://github.com/ucb-bar/tsi)

