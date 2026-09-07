import io
import struct
from collections import deque
from os import PathLike
from typing import cast

import pytest

from pyuartsi import UARTTSI, ProtocolError
from pyuartsi.fesvr import run_fesvr


class FakeTSI:
    def __init__(self, pointers: list[int], memory: dict[int, bytes]) -> None:
        self._pointers = deque(pointers)
        self._memory = memory
        self.writes: list[tuple[int, int, bool]] = []

    def get_htif_base(self, filename: str | PathLike[str]) -> int:
        del filename
        return 0x80000000

    def read_longword(self, address: int, flush_cache: bool = False) -> int:
        del address, flush_cache
        return self._pointers.popleft()

    def read_bytes(
        self,
        address: int,
        size: int,
        flush_cache: bool = False,
    ) -> bytes:
        del flush_cache
        return self._memory[address][:size]

    def write_longword(
        self,
        address: int,
        data: int,
        flush_cache: bool = False,
    ) -> None:
        self.writes.append((address, data, flush_cache))


def as_uart_tsi(fake: FakeTSI) -> UARTTSI:
    return cast(UARTTSI, fake)


def test_write_request_is_forwarded_and_acknowledged() -> None:
    request_address = 0x80001000
    exit_address = 0x80002000
    stdout = io.BytesIO()
    fake = FakeTSI(
        [request_address, exit_address],
        {
            request_address: struct.pack("<4Q", 64, 1, 0x80003000, 5),
            0x80003000: b"hello",
            exit_address: struct.pack("<4Q", 93, 7, 0, 0),
        },
    )

    assert run_fesvr(as_uart_tsi(fake), "program.elf", stdout=stdout) == 7
    assert stdout.getvalue() == b"hello"
    assert fake.writes[-2:] == [
        (0x80000000, 0, False),
        (0x80000008, 1, True),
    ]


def test_malloc_request_is_acknowledged_before_force_exit() -> None:
    fake = FakeTSI([3, 1], {})

    assert run_fesvr(as_uart_tsi(fake), "program.elf", stdout=io.BytesIO()) == 1
    assert (0x80000008, 1, True) in fake.writes


@pytest.mark.parametrize(
    ("request_data", "message"),
    [
        (struct.pack("<4Q", 64, 10, 0, 0), "file descriptor"),
        (struct.pack("<4Q", 999, 0, 0, 0), "syscall"),
    ],
)
def test_unsupported_requests_raise_protocol_errors(
    request_data: bytes,
    message: str,
) -> None:
    address = 0x80001000
    fake = FakeTSI([address], {address: request_data})

    with pytest.raises(ProtocolError, match=message):
        run_fesvr(as_uart_tsi(fake), "program.elf", stdout=io.BytesIO())


def test_invalid_request_pointer_raises_protocol_error() -> None:
    fake = FakeTSI([0x100], {})

    with pytest.raises(ProtocolError, match="pointer"):
        run_fesvr(as_uart_tsi(fake), "program.elf", stdout=io.BytesIO())
