"""Command-line interface for PyUARTSI."""

import argparse
import logging
from collections.abc import Sequence
from importlib.metadata import version

from .exceptions import PyUARTSIError
from .fesvr import run_fesvr
from .uart_tsi import DEFAULT_CACHE_FLUSH_ADDRESS, MAX_ADDRESS, UARTTSI, WORD_BYTES

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


def _initial_writes(value: str) -> list[tuple[int, int]]:
    """Parse semicolon-separated ``ADDRESS=VALUE`` arguments."""
    writes = []
    try:
        for item in value.split(";"):
            address_text, data_text = item.split("=", maxsplit=1)
            writes.append((_integer(address_text.strip()), _integer(data_text.strip())))
    except (ValueError, argparse.ArgumentTypeError) as error:
        raise argparse.ArgumentTypeError(
            "expected ADDRESS=VALUE entries separated by semicolons"
        ) from error
    return writes


def _initial_reads(value: str) -> list[range]:
    """Parse addresses and inclusive word ranges separated by semicolons."""
    reads = []
    try:
        for item in value.split(";"):
            bounds = [_integer(part.strip()) for part in item.split("~")]
            if len(bounds) == 1:
                start = end = bounds[0]
            elif len(bounds) == 2:
                start, end = bounds
            else:
                raise ValueError
            if not 0 <= start <= end <= MAX_ADDRESS - (WORD_BYTES - 1):
                raise ValueError
            if (end - start) % WORD_BYTES:
                raise ValueError
            reads.append(range(start, end + 1, WORD_BYTES))
    except (ValueError, argparse.ArgumentTypeError) as error:
        raise argparse.ArgumentTypeError(
            "expected ADDRESS or inclusive START~END word ranges separated by "
            "semicolons"
        ) from error
    return reads


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
        action="extend",
        type=_initial_writes,
        metavar="ADDRESS=VALUE[;...]",
        help="write one or more initial 32-bit values",
    )
    parser.add_argument(
        "--init-read",
        "--init_read",
        dest="init_read",
        action="extend",
        type=_initial_reads,
        metavar="ADDRESS[;...]",
        help="read addresses or inclusive START~END word ranges",
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


def main(argv: Sequence[str] | None = None) -> int:
    """Run the PyUARTSI command-line interface."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.self_check and not args.load:
        parser.error("--self-check requires --load")
    if (args.load or args.fesvr) and not args.elf:
        parser.error("--load and --fesvr require --elf")
    if not any(
        (
            args.init_write,
            args.init_read,
            args.load,
            args.hart0_msip,
            args.fesvr,
        )
    ):
        parser.error("select at least one read, write, load, MSIP, or FESVR action")
    if args.timeout < 0:
        parser.error("--timeout must be non-negative")

    logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.INFO)
    try:
        with UARTTSI(
            args.port,
            args.baud_rate,
            args.cache_flush_address,
            timeout=args.timeout,
            write_timeout=args.timeout,
        ) as tsi:
            if args.load:
                tsi.load_elf(
                    args.elf,
                    args.self_check,
                    show_progress=True,
                )

            for address, data in args.init_write or ():
                tsi.write_word(address, data)
                print(f"W: {address:#x} <= {data:#x}")

            if args.hart0_msip:
                tsi.write_longword(BOOT_ADDRESS, BOOT_VALUE)
                tsi.write_word(HART0_MSIP_ADDRESS, HART0_MSIP_VALUE)
                print("Wrote to the hart 0 MSIP register")

            for addresses in args.init_read or ():
                for address in addresses:
                    data = tsi.read_word(address)
                    print(f"R: {address:#x} => {data:#x}")

            if args.fesvr:
                return run_fesvr(tsi, args.elf)
    except (OSError, PyUARTSIError, ValueError) as error:
        parser.exit(1, f"pyuartsi: error: {error}\n")
    return 0
