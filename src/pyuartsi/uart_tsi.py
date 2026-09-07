"""Core Tethered Serial Interface protocol implementation.

The module exposes :class:`UARTTSI` for device memory access and ELF loading.
Transport-specific behavior lives in :mod:`pyuartsi.transport` so the protocol
can be tested without serial hardware.
"""

from __future__ import annotations

import logging
import struct
from collections.abc import Iterator
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

    # Compatibility spellings retained for the original public class.
    write = WRITE
    exit = EXIT


class Command(IntEnum):
    """UART TSI wire command identifiers."""

    READ = 0
    WRITE = 1

    # Compatibility spellings retained for existing callers.
    read = READ
    write = WRITE


class BaudRate(IntEnum):
    """Termios baud-rate constants retained for API compatibility."""

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


# Backward-compatible names. New code should use the CapWords class names above.
FESVR_SYSCALLS = FESVRSyscall
Baudrate = BaudRate


class UARTTSI:
    """Read and write device memory using the UART TSI protocol.

    The object owns its transport and should be closed explicitly or used as a
    context manager.
    """

    def __init__(
        self,
        port: str,
        baudrate: int,
        cflush_addr: int | str = DEFAULT_CACHE_FLUSH_ADDRESS,
        *,
        timeout: float | None = 10.0,
        write_timeout: float | None = 10.0,
        transport: Transport | None = None,
    ) -> None:
        """Initialize a UART TSI connection.

        Args:
            port: Serial device name. Ignored when ``transport`` is supplied.
            baudrate: Serial baud rate. Ignored when ``transport`` is supplied.
            cflush_addr: Cache-control address as an integer or hexadecimal text.
            timeout: Maximum seconds for a serial read, or ``None`` to block.
            write_timeout: Maximum seconds for a write, or ``None`` to block.
            transport: Optional byte transport, primarily for embedding and tests.

        Raises:
            ValueError: If an address or timeout is invalid.
            TransportError: If the default serial transport cannot be opened.
        """
        if isinstance(cflush_addr, str):
            cflush_addr = int(cflush_addr, 0)
        self._validate_address(cflush_addr)
        if timeout is not None and timeout < 0:
            raise ValueError("timeout must be non-negative or None")
        if write_timeout is not None and write_timeout < 0:
            raise ValueError("write_timeout must be non-negative or None")

        self.cflush_addr = cflush_addr
        self._transport = transport or SerialTransport(
            port,
            baudrate,
            timeout=timeout,
            write_timeout=write_timeout,
        )
        self._closed = False

    def __enter__(self) -> UARTTSI:
        """Return this open connection for use in a ``with`` statement."""
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the connection when leaving a ``with`` statement."""
        self.close()

    @staticmethod
    def align_word(value: int) -> int:
        """Round a non-negative integer up to a four-byte boundary.

        Args:
            value: Integer to align.

        Returns:
            The aligned integer.

        Raises:
            ValueError: If ``value`` is negative.
        """
        if value < 0:
            raise ValueError("value must be non-negative")
        return (value + WORD_BYTES - 1) & ~(WORD_BYTES - 1)

    @staticmethod
    def _validate_address(address: int) -> None:
        if not 0 <= address <= MAX_ADDRESS:
            raise ValueError("address must fit in an unsigned 64-bit integer")

    @staticmethod
    def _validate_size(size: int) -> None:
        if size < 0:
            raise ValueError("size must be non-negative")

    @classmethod
    def _validate_range(cls, address: int, size: int) -> None:
        cls._validate_address(address)
        cls._validate_size(size)
        if size > 0 and address > MAX_ADDRESS - (size - 1):
            raise ValueError("address range exceeds unsigned 64-bit memory")

    def _ensure_open(self) -> None:
        if self._closed:
            raise ProtocolError("UARTTSI connection is closed")

    def _write_header(self, command: Command, address: int, size: int) -> None:
        self._ensure_open()
        self._validate_range(address, size)
        if size == 0:
            raise ValueError("wire operations must contain at least one byte")
        tsi_size = self.align_word(size) // WORD_BYTES - 1
        if tsi_size > MAX_ADDRESS:
            raise ValueError("size exceeds the UART TSI wire format")
        self._transport.write_all(_HEADER.pack(command, address, tsi_size))

    def _read_payload(self, size: int) -> bytes:
        padded_size = self.align_word(size)
        return self._transport.read_exact(padded_size)[:size]

    def _write_payload(self, data: bytes) -> None:
        padding = self.align_word(len(data)) - len(data)
        self._transport.write_all(data + b"\xff" * padding)

    def _read_bytes(self, address: int, size: int) -> bytes:
        self._write_header(Command.READ, address, size)
        return self._read_payload(size)

    def _write_bytes(self, address: int, data: bytes) -> None:
        self._write_header(Command.WRITE, address, len(data))
        self._write_payload(data)

    def close(self) -> None:
        """Close the owned transport.

        Repeated calls have no effect.

        Raises:
            TransportError: If the transport cannot be closed.
        """
        if not self._closed:
            self._transport.close()
            self._closed = True

    def flush_cache_lines(self, address: int, size: int) -> None:
        """Request a cache flush for every line covering a memory range.

        Args:
            address: First device address covered by the range.
            size: Number of bytes covered by the range.

        Raises:
            ValueError: If the address or size is invalid.
            ProtocolError: If the connection is closed.
        """
        self._validate_range(address, size)
        if size == 0:
            return

        line_address = address & ~(CACHE_LINE_BYTES - 1)
        end_address = address + size
        while line_address < end_address:
            self._write_bytes(self.cflush_addr, _LONG_WORD.pack(line_address))
            line_address += CACHE_LINE_BYTES

    def read_bytes(self, address: int, size: int, flush_cache: bool = False) -> bytes:
        """Read bytes from device memory.

        Args:
            address: Device address to read.
            size: Number of bytes to read.
            flush_cache: Whether to flush covered cache lines before reading.

        Returns:
            Bytes returned by the device.

        Raises:
            ValueError: If the address or size is invalid.
            ProtocolError: If the connection is closed.
            TransportError: If transport communication fails.
        """
        self._validate_range(address, size)
        if size == 0:
            return b""
        if flush_cache:
            self.flush_cache_lines(address, size)
        return self._read_bytes(address, size)

    def read_word(self, address: int, flush_cache: bool = False) -> int:
        """Read an unsigned 32-bit little-endian word.

        Args:
            address: Device address to read.
            flush_cache: Whether to flush the covered cache line first.

        Returns:
            Unsigned word returned by the device.
        """
        return int.from_bytes(
            self.read_bytes(address, _WORD.size, flush_cache),
            byteorder="little",
        )

    def read_longword(self, address: int, flush_cache: bool = False) -> int:
        """Read an unsigned 64-bit little-endian word.

        Args:
            address: Device address to read.
            flush_cache: Whether to flush the covered cache line first.

        Returns:
            Unsigned long word returned by the device.
        """
        return int.from_bytes(
            self.read_bytes(address, _LONG_WORD.size, flush_cache),
            byteorder="little",
        )

    def write_bytes(self, address: int, data: bytes, flush_cache: bool = False) -> None:
        """Write bytes to device memory.

        Args:
            address: Device address to write.
            data: Bytes to transmit.
            flush_cache: Whether to flush covered cache lines before writing.

        Raises:
            ValueError: If the address is invalid.
            ProtocolError: If the connection is closed.
            TransportError: If transport communication fails.
        """
        self._validate_range(address, len(data))
        if not data:
            return
        if flush_cache:
            self.flush_cache_lines(address, len(data))
        self._write_bytes(address, data)

    def write_word(self, address: int, data: int, flush_cache: bool = False) -> None:
        """Write an unsigned 32-bit little-endian word.

        Args:
            address: Device address to write.
            data: Unsigned integer to transmit.
            flush_cache: Whether to flush the covered cache line first.

        Raises:
            ValueError: If ``data`` does not fit in 32 bits.
        """
        try:
            payload = _WORD.pack(data)
        except struct.error as error:
            raise ValueError("data must fit in an unsigned 32-bit integer") from error
        self.write_bytes(address, payload, flush_cache)

    def write_longword(
        self, address: int, data: int, flush_cache: bool = False
    ) -> None:
        """Write an unsigned 64-bit little-endian word.

        Args:
            address: Device address to write.
            data: Unsigned integer to transmit.
            flush_cache: Whether to flush the covered cache line first.

        Raises:
            ValueError: If ``data`` does not fit in 64 bits.
        """
        try:
            payload = _LONG_WORD.pack(data)
        except struct.error as error:
            raise ValueError("data must fit in an unsigned 64-bit integer") from error
        self.write_bytes(address, payload, flush_cache)

    def load_elf(
        self,
        filename: str | PathLike[str],
        check: bool = False,
        *,
        show_progress: bool = False,
        chunk_size: int = DEFAULT_CHUNK_BYTES,
    ) -> None:
        """Load allocated ELF sections into device memory.

        Args:
            filename: ELF file to load.
            check: Whether to read back and verify each transmitted chunk.
            show_progress: Whether to render progress bars on the terminal.
            chunk_size: Maximum bytes to transmit in one operation.

        Raises:
            ELFVerificationError: If read-back data differs from the ELF file.
            ValueError: If ``chunk_size`` is not positive.
            OSError: If the ELF file cannot be opened.
        """
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
                offsets: Iterator[int] | range
                base_offsets = range(0, len(data), chunk_size)
                if show_progress:
                    offsets = iter(
                        track(
                            base_offsets,
                            description=f"loading {section.name} ".ljust(20),
                        )
                    )
                else:
                    offsets = base_offsets

                for offset in offsets:
                    expected = data[offset : offset + chunk_size]
                    address = section_address + offset
                    self.write_bytes(address, expected)
                    if check:
                        actual = self.read_bytes(address, len(expected))
                        if actual != expected:
                            raise ELFVerificationError(address, expected, actual)

    def get_htif_base(self, filename: str | PathLike[str]) -> int:
        """Return the ELF ``.htif`` section address or the standard default.

        Args:
            filename: ELF file to inspect.

        Returns:
            Address of ``.htif``, or ``0x80000000`` if it is absent.

        Raises:
            OSError: If the ELF file cannot be opened.
        """
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
