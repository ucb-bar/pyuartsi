"""Minimal front-end server proxy for programs accessed through UART TSI."""

import struct
import sys
from os import PathLike
from typing import BinaryIO, TextIO, cast

from .exceptions import ProtocolError
from .uart_tsi import UARTTSI, FESVRSyscall

_REQUEST = struct.Struct("<4Q")
_FORCE_EXIT_POINTERS = {1, 0x10000, 0x13030}
_MALLOC_POINTER = 3
DEFAULT_RAM_BASE = 0x80000000


def _acknowledge(tsi: UARTTSI, tohost: int, fromhost: int) -> None:
    tsi.write_longword(tohost, 0)
    tsi.write_longword(fromhost, 1, flush_cache=True)


def _binary_stream(stream: TextIO) -> BinaryIO:
    binary_stream = getattr(stream, "buffer", None)
    if binary_stream is None:
        raise ProtocolError("standard stream does not expose a binary buffer")
    return cast(BinaryIO, binary_stream)


def run_fesvr(
    tsi: UARTTSI,
    filename: str | PathLike[str],
    stdout: BinaryIO | None = None,
    stderr: BinaryIO | None = None,
) -> int:
    """Serve FESVR requests until the device returns an exit status."""
    if stdout is None:
        stdout = _binary_stream(sys.stdout)
    if stderr is None:
        stderr = _binary_stream(sys.stderr)
    htif_base = tsi.get_htif_base(filename)
    tohost = htif_base
    fromhost = htif_base + 8
    tsi.write_longword(tohost, 0)

    while True:
        request_pointer = tsi.read_longword(tohost, flush_cache=True)
        if request_pointer == 0:
            continue
        if request_pointer in _FORCE_EXIT_POINTERS:
            return 1
        if request_pointer == _MALLOC_POINTER:
            _acknowledge(tsi, tohost, fromhost)
            continue
        if request_pointer < DEFAULT_RAM_BASE:
            raise ProtocolError(f"invalid FESVR request pointer: {request_pointer:#x}")

        request_data = tsi.read_bytes(
            request_pointer,
            _REQUEST.size,
            flush_cache=True,
        )
        syscall_id, argument_0, argument_1, argument_2 = _REQUEST.unpack(request_data)

        if syscall_id == FESVRSyscall.WRITE:
            output = {1: stdout, 2: stderr}.get(argument_0)
            if output is None:
                raise ProtocolError(f"unsupported FESVR file descriptor: {argument_0}")
            output.write(tsi.read_bytes(argument_1, argument_2, flush_cache=True))
            output.flush()
            _acknowledge(tsi, tohost, fromhost)
        elif syscall_id in {FESVRSyscall.LEGACY_EXIT, FESVRSyscall.EXIT}:
            _acknowledge(tsi, tohost, fromhost)
            return int(argument_0)
        else:
            raise ProtocolError(f"unsupported FESVR syscall: {syscall_id}")
