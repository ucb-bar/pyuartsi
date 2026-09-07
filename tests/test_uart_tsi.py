import struct
from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO, ClassVar

import pytest
from conftest import FakeTransport
from pytest import MonkeyPatch

import pyuartsi.uart_tsi as uart_module
from pyuartsi import UARTTSI, ELFVerificationError, ProtocolError


def make_tsi(transport: FakeTransport) -> UARTTSI:
    return UARTTSI("unused", 115_200, transport=transport)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0, 0), (1, 4), (4, 4), (5, 8)],
)
def test_align_word(value: int, expected: int) -> None:
    assert UARTTSI.align_word(value) == expected


def test_align_word_rejects_negative_values() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        UARTTSI.align_word(-1)


def test_write_bytes_encodes_header_and_padding() -> None:
    transport = FakeTransport()
    tsi = make_tsi(transport)

    tsi.write_bytes(0x1234, b"abc")

    assert transport.writes == [
        struct.pack("<IQQ", 1, 0x1234, 0),
        b"abc\xff",
    ]


def test_read_bytes_decodes_padded_response() -> None:
    transport = FakeTransport(incoming=bytearray(b"abc\xff"))
    tsi = make_tsi(transport)

    assert tsi.read_bytes(0x1234, 3) == b"abc"
    assert transport.writes == [struct.pack("<IQQ", 0, 0x1234, 0)]


def test_empty_reads_and_writes_do_not_touch_transport() -> None:
    transport = FakeTransport()
    tsi = make_tsi(transport)

    assert tsi.read_bytes(0, 0) == b""
    tsi.write_bytes(0, b"")

    assert transport.writes == []


def test_word_operations_are_little_endian() -> None:
    transport = FakeTransport(incoming=bytearray(struct.pack("<IQ", 7, 9)))
    tsi = make_tsi(transport)

    assert tsi.read_word(0x1000) == 7
    assert tsi.read_longword(0x1004) == 9
    tsi.write_word(0x2000, 11)
    tsi.write_longword(0x2008, 13)

    assert transport.writes[-3:] == [
        struct.pack("<I", 11),
        struct.pack("<IQQ", 1, 0x2008, 1),
        struct.pack("<Q", 13),
    ]


def test_word_operations_validate_integer_ranges() -> None:
    tsi = make_tsi(FakeTransport())

    with pytest.raises(ValueError, match="32-bit"):
        tsi.write_word(0, 1 << 32)
    with pytest.raises(ValueError, match="64-bit"):
        tsi.write_longword(0, -1)


def test_cache_flush_covers_address_zero_and_crossed_lines() -> None:
    transport = FakeTransport()
    tsi = make_tsi(transport)

    tsi.flush_cache_lines(0, 65)

    assert transport.writes == [
        struct.pack("<IQQ", 1, tsi.cflush_addr, 1),
        struct.pack("<Q", 0),
        struct.pack("<IQQ", 1, tsi.cflush_addr, 1),
        struct.pack("<Q", 64),
    ]


def test_ranges_and_timeouts_are_validated() -> None:
    tsi = make_tsi(FakeTransport())

    with pytest.raises(ValueError, match="address"):
        tsi.read_bytes(-1, 1)
    with pytest.raises(ValueError, match="size"):
        tsi.read_bytes(0, -1)
    with pytest.raises(ValueError, match="range"):
        tsi.flush_cache_lines((1 << 64) - 1, 2)
    with pytest.raises(ValueError, match="range"):
        tsi.read_bytes((1 << 64) - 1, 2)
    with pytest.raises(ValueError, match="range"):
        tsi.write_bytes((1 << 64) - 1, b"ab")
    with pytest.raises(ValueError, match="timeout"):
        UARTTSI("unused", 1, timeout=-1, transport=FakeTransport())


def test_context_manager_closes_once_and_rejects_later_operations() -> None:
    transport = FakeTransport()

    with make_tsi(transport) as tsi:
        assert transport.close_count == 0

    tsi.close()
    assert transport.close_count == 1
    with pytest.raises(ProtocolError, match="closed"):
        tsi.read_bytes(0, 1)


class FakeSection:
    def __init__(self, name: str, address: object, payload: bytes) -> None:
        self.name = name
        self.header: dict[str, object] = {
            "sh_type": "SHT_PROGBITS",
            "sh_addr": address,
        }
        self._payload = payload

    def data(self) -> bytes:
        return self._payload


class FakeELFFile:
    sections: ClassVar[list[FakeSection]] = []

    def __init__(self, _stream: BinaryIO) -> None:
        pass

    def iter_sections(self) -> Iterator[FakeSection]:
        yield from self.sections


def install_fake_elf(monkeypatch: MonkeyPatch, sections: list[FakeSection]) -> None:
    FakeELFFile.sections = sections
    monkeypatch.setattr(uart_module, "ELFFile", FakeELFFile)


def test_load_elf_chunks_and_verifies(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    elf_path = tmp_path / "program.elf"
    elf_path.write_bytes(b"")
    install_fake_elf(monkeypatch, [FakeSection(".text", 0x1000, b"abcdefgh")])
    transport = FakeTransport(incoming=bytearray(b"abcdefgh"))
    tsi = make_tsi(transport)

    tsi.load_elf(elf_path, check=True, chunk_size=4)

    payloads = [write for write in transport.writes if len(write) <= 8]
    assert payloads == [b"abcd", b"efgh"]


def test_load_elf_raises_on_verification_mismatch(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    elf_path = tmp_path / "program.elf"
    elf_path.write_bytes(b"")
    install_fake_elf(monkeypatch, [FakeSection(".text", 0x1000, b"abcd")])
    tsi = make_tsi(FakeTransport(incoming=bytearray(b"bad!")))

    with pytest.raises(ELFVerificationError) as error_info:
        tsi.load_elf(elf_path, check=True)

    assert error_info.value.address == 0x1000
    assert error_info.value.expected == b"abcd"
    assert error_info.value.actual == b"bad!"


def test_load_elf_skips_non_addressed_sections(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    elf_path = tmp_path / "program.elf"
    elf_path.write_bytes(b"")
    install_fake_elf(monkeypatch, [FakeSection(".debug", None, b"ignored")])
    transport = FakeTransport()

    make_tsi(transport).load_elf(elf_path)

    assert transport.writes == []


def test_load_elf_rejects_invalid_chunk_size(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="positive"):
        make_tsi(FakeTransport()).load_elf(tmp_path / "missing", chunk_size=0)


def test_get_htif_base_uses_section_or_default(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    elf_path = tmp_path / "program.elf"
    elf_path.write_bytes(b"")
    tsi = make_tsi(FakeTransport())

    install_fake_elf(monkeypatch, [FakeSection(".htif", 0x9000, b"")])
    assert tsi.get_htif_base(elf_path) == 0x9000

    install_fake_elf(monkeypatch, [])
    assert tsi.get_htif_base(elf_path) == uart_module.DEFAULT_HTIF_BASE
