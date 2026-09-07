"""Opt-in smoke tests for a connected UART TSI target."""

from __future__ import annotations

import os

import pytest

from pyuartsi import UARTTSI


@pytest.mark.hardware
def test_read_configured_hardware_address() -> None:
    port = os.environ.get("PYUARTSI_TEST_PORT")
    address_text = os.environ.get("PYUARTSI_TEST_ADDRESS")
    if port is None or address_text is None:
        pytest.skip("set PYUARTSI_TEST_PORT and PYUARTSI_TEST_ADDRESS")

    baud_rate = int(os.environ.get("PYUARTSI_TEST_BAUD_RATE", "115200"), 0)
    timeout = float(os.environ.get("PYUARTSI_TEST_TIMEOUT", "10"))
    address = int(address_text, 0)

    with UARTTSI(port, baud_rate, timeout=timeout) as tsi:
        value = tsi.read_word(address)

    assert 0 <= value < 1 << 32
