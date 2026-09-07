from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from types import TracebackType

import pytest
from pytest import CaptureFixture, MonkeyPatch

import pyuartsi.cli as cli
from pyuartsi import ProtocolError


class FakeUARTTSI:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def __enter__(self) -> FakeUARTTSI:
        return self

    def __exit__(
        self,
        _exception_type: type[BaseException] | None,
        _exception: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        self.calls.append(("close",))

    def load_elf(
        self,
        filename: str | Path,
        check: bool,
        show_progress: bool,
    ) -> None:
        self.calls.append(("load", filename, check, show_progress))

    def write_word(self, address: int, data: int) -> None:
        self.calls.append(("write_word", address, data))

    def write_longword(self, address: int, data: int) -> None:
        self.calls.append(("write_longword", address, data))

    def read_word(self, address: int) -> int:
        self.calls.append(("read_word", address))
        return 0xABCD


def invoke(arguments: Sequence[str]) -> int:
    return cli.main(arguments)


def install_tsi(monkeypatch: MonkeyPatch, tsi: FakeUARTTSI) -> None:
    def create_tsi(
        port: str,
        baudrate: int,
        cache_flush_address: int,
        timeout: float,
        write_timeout: float,
    ) -> FakeUARTTSI:
        del port, baudrate, cache_flush_address, timeout, write_timeout
        return tsi

    monkeypatch.setattr(cli, "UARTTSI", create_tsi)


@pytest.mark.parametrize(
    "arguments",
    [
        ["--port", "COM1"],
        ["--port", "COM1", "--self-check"],
        ["--port", "COM1", "--load"],
        ["--port", "COM1", "--init-read", "0", "--timeout", "-1"],
    ],
)
def test_invalid_argument_relationships_exit(arguments: list[str]) -> None:
    with pytest.raises(SystemExit) as error_info:
        invoke(arguments)
    assert error_info.value.code == 2


def test_initial_write_parser_reports_bad_values() -> None:
    with pytest.raises(SystemExit) as error_info:
        invoke(["--port", "COM1", "--init-write", "broken"])
    assert error_info.value.code == 2


def test_memory_and_msip_actions(
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    tsi = FakeUARTTSI()
    install_tsi(monkeypatch, tsi)

    result = invoke(
        [
            "--port",
            "COM1",
            "--init_write",
            "0x10=0x20",
            "--init_read",
            "0x10",
            "--hart0_msip",
        ]
    )

    assert result == 0
    assert tsi.calls == [
        ("write_word", 0x10, 0x20),
        ("write_longword", cli.BOOT_ADDRESS, cli.BOOT_VALUE),
        ("write_word", cli.HART0_MSIP_ADDRESS, cli.HART0_MSIP_VALUE),
        ("read_word", 0x10),
        ("close",),
    ]
    assert "0xabcd" in capsys.readouterr().out.lower()


def test_load_and_fesvr_actions(monkeypatch: MonkeyPatch) -> None:
    tsi = FakeUARTTSI()
    install_tsi(monkeypatch, tsi)

    def fake_fesvr(
        tsi: FakeUARTTSI,
        filename: str,
    ) -> int:
        tsi.calls.append(("fesvr", filename))
        return 7

    monkeypatch.setattr(cli, "run_fesvr", fake_fesvr)

    result = invoke(
        [
            "--port",
            "COM1",
            "--elf",
            "program.elf",
            "--load",
            "--self-check",
            "--fesvr",
        ]
    )

    assert result == 7
    assert tsi.calls == [
        ("load", "program.elf", True, True),
        ("fesvr", "program.elf"),
        ("close",),
    ]


def test_library_error_becomes_cli_exit(monkeypatch: MonkeyPatch) -> None:
    class FailingUARTTSI(FakeUARTTSI):
        def read_word(self, address: int) -> int:
            del address
            raise ProtocolError("test failure")

    install_tsi(monkeypatch, FailingUARTTSI())

    with pytest.raises(SystemExit) as error_info:
        invoke(["--port", "COM1", "--init-read", "0"])
    assert error_info.value.code == 1
