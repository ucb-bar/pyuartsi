"""Command-line interface for PyUARTSI."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from importlib.metadata import version

from .exceptions import PyUARTSIError
from .fesvr import run_fesvr
from .uart_tsi import DEFAULT_CACHE_FLUSH_ADDRESS, UARTTSI

DEFAULT_BAUD_RATE = 115200
HART0_MSIP_ADDRESS = 0x02000000
HART0_MSIP_VALUE = 0x01
BOOT_ADDRESS = 0x1000
BOOT_VALUE = 0x80000000


def _integer(value: str) -> int:
    """Parse a decimal or prefixed integer for argparse."""
    try:
        return int(value, 0)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"invalid integer: {value!r}") from error


def _initial_write(value: str) -> tuple[int, int]:
    """Parse an ``ADDRESS=VALUE`` argument for argparse."""
    try:
        address_text, data_text = value.split("=", maxsplit=1)
        return _integer(address_text), _integer(data_text)
    except (ValueError, argparse.ArgumentTypeError) as error:
        raise argparse.ArgumentTypeError(
            "expected ADDRESS=VALUE using decimal or 0x-prefixed integers"
        ) from error


def build_parser() -> argparse.ArgumentParser:
    """Create the PyUARTSI argument parser."""
    parser = argparse.ArgumentParser(
        description="Access a target through the UART Tethered Serial Interface.",
        epilog=("example: pyuartsi --port COM20 --elf program.elf --load --self-check"),
    )
    parser.add_argument("--version", action="version", version=version("pyuartsi"))
    parser.add_argument("--port", required=True, help="serial port to connect to")
    parser.add_argument(
        "--baud-rate",
        "--baudrate",
        dest="baud_rate",
        type=int,
        default=DEFAULT_BAUD_RATE,
        help="serial baud rate (default: %(default)s)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="serial read/write timeout in seconds (default: %(default)s)",
    )
    parser.add_argument(
        "--init-write",
        "--init_write",
        dest="init_write",
        type=_initial_write,
        metavar="ADDRESS=VALUE",
        help="write an initial 32-bit value",
    )
    parser.add_argument(
        "--init-read",
        "--init_read",
        dest="init_read",
        type=_integer,
        metavar="ADDRESS",
        help="read an initial 32-bit value",
    )
    parser.add_argument("--elf", help="ELF file to load or serve")
    parser.add_argument("--load", action="store_true", help="load the ELF file")
    parser.add_argument(
        "--self-check",
        "--selfcheck",
        dest="self_check",
        action="store_true",
        help="read back and verify the loaded ELF file",
    )
    parser.add_argument(
        "--hart0-msip",
        "--hart0_msip",
        dest="hart0_msip",
        action="store_true",
        help="initialize the hart 0 software-interrupt register",
    )
    parser.add_argument(
        "--fesvr",
        action="store_true",
        help="serve the minimal FESVR interface",
    )
    parser.add_argument(
        "--cflush-addr",
        "--cflush_addr",
        dest="cache_flush_address",
        type=_integer,
        default=DEFAULT_CACHE_FLUSH_ADDRESS,
        metavar="ADDRESS",
        help="cache-control base address (default: %(default)#x)",
    )
    return parser


def _validate_arguments(
    parser: argparse.ArgumentParser,
    arguments: argparse.Namespace,
) -> None:
    if arguments.self_check and not arguments.load:
        parser.error("--self-check requires --load")
    if (arguments.load or arguments.fesvr) and not arguments.elf:
        parser.error("--load and --fesvr require --elf")
    if not any(
        (
            arguments.init_write,
            arguments.init_read is not None,
            arguments.load,
            arguments.hart0_msip,
            arguments.fesvr,
        )
    ):
        parser.error("select at least one read, write, load, MSIP, or FESVR action")
    if arguments.timeout < 0:
        parser.error("--timeout must be non-negative")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the PyUARTSI command-line interface.

    Args:
        argv: Optional argument sequence excluding the program name.

    Returns:
        A process exit status.
    """
    parser = build_parser()
    arguments = parser.parse_args(argv)
    _validate_arguments(parser, arguments)

    logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.INFO)
    try:
        with UARTTSI(
            arguments.port,
            arguments.baud_rate,
            arguments.cache_flush_address,
            timeout=arguments.timeout,
            write_timeout=arguments.timeout,
        ) as tsi:
            if arguments.load:
                tsi.load_elf(
                    arguments.elf,
                    arguments.self_check,
                    show_progress=True,
                )

            if arguments.init_write is not None:
                address, data = arguments.init_write
                tsi.write_word(address, data)
                print(f"W: {address:#x} <= {data:#x}")

            if arguments.hart0_msip:
                tsi.write_longword(BOOT_ADDRESS, BOOT_VALUE)
                tsi.write_word(HART0_MSIP_ADDRESS, HART0_MSIP_VALUE)
                print("Wrote to the hart 0 MSIP register")

            if arguments.init_read is not None:
                data = tsi.read_word(arguments.init_read)
                print(f"R: {arguments.init_read:#x} => {data:#x}")

            if arguments.fesvr:
                return run_fesvr(tsi, arguments.elf)
    except (OSError, PyUARTSIError, ValueError) as error:
        parser.exit(1, f"pyuartsi: error: {error}\n")
    return 0
