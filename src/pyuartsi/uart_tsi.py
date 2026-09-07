"""UART Tethered Serial Interface protocol implementation."""

from __future__ import annotations

import logging
import struct
from enum import IntEnum
from os import PathLike
from pathlib import Path
from types import TracebackType

from elftools.elf.elffile import ELFFile
from rich.progress import track

from .exceptions import ELFVerificationError, ProtocolError
from .transport import SerialTransport, Transport

LOGGER = logging.getLogger(__name__)

WORD_BYTES = 4
CACHE_LINE_BYTES = 64
DEFAULT_CACHE_FLUSH_ADDRESS = 0x02010200
DEFAULT_HTIF_BASE = 0x80000000
DEFAULT_CHUNK_BYTES = 1024
MAX_ADDRESS = (1 << 64) - 1

_HEADER = struct.Struct("<IQQ")
_WORD = struct.Struct("<I")
_LONG_WORD = struct.Struct("<Q")


class FESVRSyscall(IntEnum):
    """Supported FESVR syscall identifiers."""

    LEGACY_EXIT = 1
    WRITE = 64
    EXIT = 93

    write = WRITE
    exit = EXIT


class Command(IntEnum):
    """UART TSI wire command identifiers."""

    READ = 0
    WRITE = 1

    read = READ
    write = WRITE


class BaudRate(IntEnum):
    """Serial baud-rate constants."""

    B57600 = 0o10001
    B115200 = 0o10002
    B230400 = 0o10003
    B460800 = 0o10004
    B500000 = 0o10005
    B576000 = 0o10006
    B921600 = 0o10007
    B1000000 = 0o10010
    B1152000 = 0o10011
    B1500000 = 0o10012
    B2000000 = 0o10013
    B2500000 = 0o10014
    B3000000 = 0o10015
    B3500000 = 0o10016
    B4000000 = 0o10017


FESVR_SYSCALLS = FESVRSyscall
Baudrate = BaudRate


class UARTTSI:
    """Access device memory through UART TSI and own the transport."""

    def __init__(
        self,
        port: str,
        baudrate: int,
        cflush_addr: int | str = DEFAULT_CACHE_FLUSH_ADDRESS,
        timeout: float | None = 10.0,
        write_timeout: float | None = 10.0,
        transport: Transport | None = None,
    ) -> None:
        """Initialize the connection, optionally with a supplied transport."""
        if isinstance(cflush_addr, str):
            cflush_addr = int(cflush_addr, 0)
        self._validate_address(cflush_addr)
        if timeout is not None and timeout < 0:
            raise ValueError("timeout must be non-negative or None")
        if write_timeout is not None and write_timeout < 0:
            raise ValueError("write_timeout must be non-negative or None")

        self.cflush_addr = cflush_addr
        self._transport = (
            transport
            if transport is not None
            else SerialTransport(
                port,
                baudrate,
                timeout=timeout,
                write_timeout=write_timeout,
            )
        )
        self._closed = False

    def __enter__(self) -> UARTTSI:
        """Return this open connection for use in a ``with`` statement."""
        return self

    def __exit__(
        self,
        _exception_type: type[BaseException] | None,
        _exception: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        """Close the connection when leaving a ``with`` statement."""
        self.close()

    @staticmethod
    def align_word(value: int) -> int:
        """Round a non-negative integer up to a four-byte boundary."""
        if value < 0:
            raise ValueError("value must be non-negative")
        return (value + WORD_BYTES - 1) & ~(WORD_BYTES - 1)

    @staticmethod
    def _validate_address(address: int) -> None:
        if not 0 <= address <= MAX_ADDRESS:
            raise ValueError("address must fit in an unsigned 64-bit integer")

    @classmethod
    def _validate_range(cls, address: int, size: int) -> None:
        cls._validate_address(address)
        if size < 0:
            raise ValueError("size must be non-negative")
        if size > 0 and address > MAX_ADDRESS - (size - 1):
            raise ValueError("address range exceeds unsigned 64-bit memory")

    def _write_header(self, command: Command, address: int, size: int) -> None:
        if self._closed:
            raise ProtocolError("UARTTSI connection is closed")
        self._validate_range(address, size)
        if size == 0:
            raise ValueError("wire operations must contain at least one byte")
        tsi_size = self.align_word(size) // WORD_BYTES - 1
        if tsi_size > MAX_ADDRESS:
            raise ValueError("size exceeds the UART TSI wire format")
        self._transport.write_all(_HEADER.pack(command, address, tsi_size))

    def _read_bytes(self, address: int, size: int) -> bytes:
        self._write_header(Command.READ, address, size)
        return self._transport.read_exact(self.align_word(size))[:size]

    def _write_bytes(self, address: int, data: bytes) -> None:
        self._write_header(Command.WRITE, address, len(data))
        padding = self.align_word(len(data)) - len(data)
        self._transport.write_all(data + b"\xff" * padding)

    def close(self) -> None:
        """Close the transport; repeated calls have no effect."""
        if not self._closed:
            self._transport.close()
            self._closed = True

    def flush_cache_lines(self, address: int, size: int) -> None:
        """Flush every cache line covering the requested memory range."""
        self._validate_range(address, size)
        if size == 0:
            return

        line_address = address & ~(CACHE_LINE_BYTES - 1)
        end_address = address + size
        while line_address < end_address:
            self._write_bytes(self.cflush_addr, _LONG_WORD.pack(line_address))
            line_address += CACHE_LINE_BYTES

    def read_bytes(self, address: int, size: int, flush_cache: bool = False) -> bytes:
        """Read ``size`` bytes from device memory at ``address``."""
        self._validate_range(address, size)
        if size == 0:
            return b""
        if flush_cache:
            self.flush_cache_lines(address, size)
        return self._read_bytes(address, size)

    def read_word(self, address: int, flush_cache: bool = False) -> int:
        """Read an unsigned 32-bit little-endian word."""
        return int.from_bytes(
            self.read_bytes(address, _WORD.size, flush_cache),
            byteorder="little",
        )

    def read_longword(self, address: int, flush_cache: bool = False) -> int:
        """Read an unsigned 64-bit little-endian word."""
        return int.from_bytes(
            self.read_bytes(address, _LONG_WORD.size, flush_cache),
            byteorder="little",
        )

    def write_bytes(self, address: int, data: bytes, flush_cache: bool = False) -> None:
        """Write bytes to device memory at ``address``."""
        self._validate_range(address, len(data))
        if not data:
            return
        if flush_cache:
            self.flush_cache_lines(address, len(data))
        self._write_bytes(address, data)

    def write_word(self, address: int, data: int, flush_cache: bool = False) -> None:
        """Write an unsigned 32-bit little-endian word."""
        try:
            payload = _WORD.pack(data)
        except struct.error as error:
            raise ValueError("data must fit in an unsigned 32-bit integer") from error
        self.write_bytes(address, payload, flush_cache)

    def write_longword(
        self, address: int, data: int, flush_cache: bool = False
    ) -> None:
        """Write an unsigned 64-bit little-endian word."""
        try:
            payload = _LONG_WORD.pack(data)
        except struct.error as error:
            raise ValueError("data must fit in an unsigned 64-bit integer") from error
        self.write_bytes(address, payload, flush_cache)

    def load_elf(
        self,
        filename: str | PathLike[str],
        check: bool = False,
        show_progress: bool = False,
        chunk_size: int = DEFAULT_CHUNK_BYTES,
    ) -> None:
        """Load addressable ELF sections, optionally verifying each chunk."""
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")

        with Path(filename).open("rb") as stream:
            elf_file = ELFFile(stream)  # type: ignore[no-untyped-call]
            for section in elf_file.iter_sections():  # type: ignore[no-untyped-call]
                section_address = section.header.get("sh_addr")
                if (
                    section.header.get("sh_type") != "SHT_PROGBITS"
                    or not isinstance(section_address, int)
                    or section_address <= 0
                ):
                    continue

                data = section.data()
                LOGGER.info(
                    "Loading section %s (%d bytes) at %#x",
                    section.name,
                    len(data),
                    section_address,
                )
                base_offsets = range(0, len(data), chunk_size)
                offsets = (
                    track(
                        base_offsets,
                        description=f"loading {section.name} ".ljust(20),
                    )
                    if show_progress
                    else base_offsets
                )

                for offset in offsets:
                    expected = data[offset : offset + chunk_size]
                    address = section_address + offset
                    self.write_bytes(address, expected)
                    if check:
                        actual = self.read_bytes(address, len(expected))
                        if actual != expected:
                            raise ELFVerificationError(address, expected, actual)

    def get_htif_base(self, filename: str | PathLike[str]) -> int:
        """Return the ELF ``.htif`` address or the standard default."""
        with Path(filename).open("rb") as stream:
            elf_file = ELFFile(stream)  # type: ignore[no-untyped-call]
            for section in elf_file.iter_sections():  # type: ignore[no-untyped-call]
                if section.name == ".htif":
                    section_address = section.header.get("sh_addr")
                    if isinstance(section_address, int):
                        self._validate_address(section_address)
                        return section_address
                    raise ProtocolError("ELF .htif section has no integer address")
        return DEFAULT_HTIF_BASE
