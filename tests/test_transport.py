"""Tests for the pyserial transport adapter."""

from __future__ import annotations

from collections import deque

import pytest
import serial
from pytest import MonkeyPatch

from pyuartsi import TransportError, TransportTimeoutError
from pyuartsi.transport import SerialTransport


class FakeSerial:
    """Small pyserial-compatible test double."""

    def __init__(self, chunks: list[bytes] | None = None) -> None:
        self.chunks = deque(chunks or [])
        self.write_limit = 1_000_000
        self.writes: list[bytes] = []
        self.reset_input = False
        self.reset_output = False
        self.closed = False

    def reset_input_buffer(self) -> None:
        self.reset_input = True

    def reset_output_buffer(self) -> None:
        self.reset_output = True

    def read(self, size: int) -> bytes:
        del size
        return self.chunks.popleft() if self.chunks else b""

    def write(self, data: bytes) -> int:
        written = min(len(data), self.write_limit)
        self.writes.append(data[:written])
        return written

    def close(self) -> None:
        self.closed = True


def install_serial(monkeypatch: MonkeyPatch, fake: FakeSerial) -> None:
    """Make SerialTransport construct a configured fake."""
    monkeypatch.setattr(serial, "Serial", lambda **_kwargs: fake)


def test_serial_transport_reads_writes_and_closes(monkeypatch: MonkeyPatch) -> None:
    fake = FakeSerial([b"a", b"bc"])
    fake.write_limit = 2
    install_serial(monkeypatch, fake)
    transport = SerialTransport("COM1", 115_200)

    assert fake.reset_input and fake.reset_output
    assert transport.read_exact(3) == b"abc"
    transport.write_all(b"abcd")
    transport.close()

    assert fake.writes == [b"ab", b"cd"]
    assert fake.closed


def test_serial_read_timeout(monkeypatch: MonkeyPatch) -> None:
    install_serial(monkeypatch, FakeSerial())

    with pytest.raises(TransportTimeoutError, match="0 of 1"):
        SerialTransport("COM1", 115_200).read_exact(1)


def test_serial_write_timeout(monkeypatch: MonkeyPatch) -> None:
    fake = FakeSerial()
    fake.write_limit = 0
    install_serial(monkeypatch, fake)

    with pytest.raises(TransportTimeoutError, match="0 of 1"):
        SerialTransport("COM1", 115_200).write_all(b"a")


def test_serial_open_error_is_wrapped(monkeypatch: MonkeyPatch) -> None:
    def fail(**_kwargs: object) -> None:
        raise serial.SerialException("no device")

    monkeypatch.setattr(serial, "Serial", fail)

    with pytest.raises(TransportError, match="could not open"):
        SerialTransport("COM1", 115_200)
