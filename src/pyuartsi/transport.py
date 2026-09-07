"""Transport abstractions for UART TSI communication."""

from __future__ import annotations

from typing import Protocol

import serial

from .exceptions import TransportError, TransportTimeoutError


class Transport(Protocol):
    """Describe the byte transport required by :class:`UARTTSI`."""

    def read_exact(self, size: int) -> bytes:
        """Read exactly ``size`` bytes or raise a transport error."""

    def write_all(self, data: bytes) -> None:
        """Write every byte in ``data`` or raise a transport error."""

    def close(self) -> None:
        """Release resources owned by the transport."""


class SerialTransport:
    """Implement the TSI transport with pyserial."""

    def __init__(
        self,
        port: str,
        baudrate: int,
        *,
        timeout: float | None = 10.0,
        write_timeout: float | None = 10.0,
    ) -> None:
        """Open and prepare a serial port.

        Args:
            port: Serial device name, such as ``COM20`` or ``/dev/ttyUSB0``.
            baudrate: Serial baud rate.
            timeout: Maximum seconds for each serial read, or ``None`` to block.
            write_timeout: Maximum seconds for each write, or ``None`` to block.

        Raises:
            TransportError: If the serial port cannot be opened or prepared.
        """
        try:
            self._serial = serial.Serial(
                port=port,
                baudrate=baudrate,
                timeout=timeout,
                write_timeout=write_timeout,
            )
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()
        except serial.SerialException as error:
            raise TransportError(
                f"could not open serial port {port!r}: {error}"
            ) from error

    def read_exact(self, size: int) -> bytes:
        """Read exactly ``size`` bytes.

        Args:
            size: Number of bytes to read.

        Returns:
            Bytes read from the serial port.

        Raises:
            TransportTimeoutError: If the configured timeout expires.
            TransportError: If pyserial reports another read failure.
        """
        data = bytearray()
        try:
            while len(data) < size:
                chunk = self._serial.read(size - len(data))
                if not chunk:
                    raise TransportTimeoutError(
                        f"timed out after receiving {len(data)} of {size} bytes"
                    )
                data.extend(chunk)
        except serial.SerialException as error:
            raise TransportError(f"serial read failed: {error}") from error
        return bytes(data)

    def write_all(self, data: bytes) -> None:
        """Write all bytes to the serial port.

        Args:
            data: Bytes to transmit.

        Raises:
            TransportTimeoutError: If the configured write timeout expires.
            TransportError: If pyserial reports another write failure.
        """
        offset = 0
        try:
            while offset < len(data):
                written = self._serial.write(data[offset:])
                if written is None or written == 0:
                    raise TransportTimeoutError(
                        f"timed out after writing {offset} of {len(data)} bytes"
                    )
                offset += written
        except serial.SerialTimeoutException as error:
            raise TransportTimeoutError(f"serial write timed out: {error}") from error
        except serial.SerialException as error:
            raise TransportError(f"serial write failed: {error}") from error

    def close(self) -> None:
        """Close the serial port."""
        try:
            self._serial.close()
        except serial.SerialException as error:
            raise TransportError(f"could not close serial port: {error}") from error
