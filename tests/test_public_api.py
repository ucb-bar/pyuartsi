"""Tests for the deliberate package export surface."""

import pyuartsi


def test_public_api_is_explicit() -> None:
    assert set(pyuartsi.__all__) == {
        "BaudRate",
        "Baudrate",
        "Command",
        "ELFVerificationError",
        "FESVR_SYSCALLS",
        "FESVRSyscall",
        "ProtocolError",
        "PyUARTSIError",
        "TransportError",
        "TransportTimeoutError",
        "UARTTSI",
    }
    assert "CDLL" not in dir(pyuartsi)
    assert pyuartsi.Baudrate is pyuartsi.BaudRate
    assert pyuartsi.FESVR_SYSCALLS is pyuartsi.FESVRSyscall
