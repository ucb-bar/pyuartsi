"""Exceptions raised by PyUARTSI."""


class PyUARTSIError(Exception):
    """Base class for errors raised by PyUARTSI."""


class ProtocolError(PyUARTSIError):
    """Indicate invalid or unsupported TSI protocol data."""


class TransportError(PyUARTSIError):
    """Indicate a failure while communicating with the serial transport."""


class TransportTimeoutError(TransportError, TimeoutError):
    """Indicate that a transport operation did not finish before its timeout."""


class ELFVerificationError(PyUARTSIError):
    """Indicate that data read from the device differs from an ELF section."""

    def __init__(self, address: int, expected: bytes, actual: bytes) -> None:
        """Initialize an ELF verification failure.

        Args:
            address: Device address at which the mismatch occurred.
            expected: Bytes obtained from the ELF file.
            actual: Bytes read back from the device.
        """
        self.address = address
        self.expected = expected
        self.actual = actual
        super().__init__(f"ELF verification failed at address {address:#x}")
