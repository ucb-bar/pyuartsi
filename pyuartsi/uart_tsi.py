import struct
from ctypes import *  # noqa: F401, F403
from .tsi import TSI, Command

import serial

class Baudrate:
    B57600     = 0o10001
    B115200    = 0o10002
    B230400    = 0o10003
    B460800    = 0o10004
    B500000    = 0o10005
    B576000    = 0o10006
    B921600    = 0o10007
    B1000000   = 0o10010
    B1152000   = 0o10011
    B1500000   = 0o10012
    B2000000   = 0o10013
    B2500000   = 0o10014
    B3000000   = 0o10015
    B3500000   = 0o10016
    B4000000   = 0o10017


class SerialImpl:
    @staticmethod
    def int_to_baud(int_baud: int) -> int:
        """
        Convert an integer baudrate to a Baudrate enum.

        Args:
            int_baud (int): Baudrate to convert

        Returns:
            int: Baudrate enum
        """
        if int_baud == 57600:
            return Baudrate.B57600
        elif int_baud == 115200:
            return Baudrate.B115200
        else:
            raise ValueError("Invalid baudrate")

    def __init__(self, port: str, baudrate: int) -> None:
        self.port = port
        self.baudrate = baudrate
        self.fd = None

        # try:
        #     baud = UARTTSI.int_to_baud(baudrate)
        #     self.ser = cdll.LoadLibrary(os.path.join(os.getcwd(), "li bserial.so"))

        #     port_ptr = c_char_p(port.encode())
        #     self.fd = self.ser.serial_init(port_ptr, baud, 100)

        # except OSError:
        #     print("the faster C impl is not available, falling back to pyserial")
        #     self.ser = serial.Serial(port=self.port, baudrate=self.baudrate)

        self.ser = serial.Serial(port=self.port, baudrate=self.baudrate)

        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()

    def write(self, data: bytes) -> None:
        """
        Write data to the UART TSI.

        Args:
            data (bytes): Data to write
        """
        if self.fd is not None:
            raise NotImplementedError("C implementation not supported")
            # #data_ptr = c_char * len(data)
            # #self.ser.serial_write(self.fd, data_ptr.from_buffer(data), len(data))
            # self.ser.serial_write(self.fd, c_char_p(data), len(data))
            return

        self.ser.write(data)

    def read(self, len: int) -> bytes:
        """
        Read data from the UART TSI.

        Args:
            len (int): Number of bytes to read
        """
        if self.fd is not None:
            raise NotImplementedError("C implementation not supported")
            return b""

        return self.ser.read(len)


class UARTTSI(TSI):
    def __init__(self, port: str, baudrate: int, cflush_addr: int | str = 0x02010200) -> None:
        """
        Initialize the UARTTSI object.

        Args:
            port (str): Serial port to connect to
            baudrate (int): Baudrate to use
        """
        self.ser = SerialImpl(port, baudrate)
        super().__init__(cflush_addr)

    def _write_header(self, command: Command, addr: int, size: int = 0) -> None:
        """
        Write a header to the UART TSI.

        Args:
            command (Command): Command to send
            addr (int): Address to read/write
            size (int): Number of bytes to read/write
        """
        # conver size to TSI size (number of words - 1)
        tsi_size = max(self.align_word(size) // 4 - 1, 0)

        self.ser.write(struct.pack("<I", command) + struct.pack("<Q", addr) + struct.pack("<Q", tsi_size))

    def _read_payload(self, size: int) -> bytes:
        """
        Read a chunk of data from the UART TSI.

        Args:
            size (int): Number of bytes to read
        """
        # pad to next word boundary
        n_padding = self.align_word(size) - size

        buffer = self.ser.read(size + n_padding)
        return buffer[:size]

    def _write_payload(self, data: bytes) -> None:
        """
        Write chunks of data to the UART TSI.

        The data is padded to word boundaries.

        Args:
            data (bytes): Data to write
        """
        # pad to next word boundary
        n_padding = self.align_word(len(data)) - len(data)

        self.ser.write(data)
        self.ser.write(b'\xFF' * n_padding)

    def _read_bytes(self, addr: int, size: int) -> bytes:
        self._write_header(Command.read, addr, size)
        buffer = self._read_payload(size)

        return buffer

    def _write_bytes(self, addr: int, data: bytes) -> None:
        size = len(data)
        self._write_header(Command.write, addr, size)
        self._write_payload(data)
