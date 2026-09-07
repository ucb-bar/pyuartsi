"""Python implementation of the UART Tethered Serial Interface.

The package exports :class:`UARTTSI` for device access, public protocol enums,
and exceptions callers can use for structured error handling.
"""

from .exceptions import (
    ELFVerificationError,
    ProtocolError,
    PyUARTSIError,
    TransportError,
    TransportTimeoutError,
)
from .uart_tsi import (
    FESVR_SYSCALLS,
    UARTTSI,
    BaudRate,
    Baudrate,
    Command,
    FESVRSyscall,
)

__all__ = (
    "FESVR_SYSCALLS",
    "UARTTSI",
    "BaudRate",
    "Baudrate",
    "Command",
    "ELFVerificationError",
    "FESVRSyscall",
    "ProtocolError",
    "PyUARTSIError",
    "TransportError",
    "TransportTimeoutError",
)
