import struct
from ctypes import *
from .tsi import TSI, Command

from pyftdi.ftdi import Ftdi
from pyftdi.spi import *

class SPITSI(TSI):
    def list_devices():
        Ftdi.show_devices()

    def __init__(self, url: str = 'ftdi:///1', freq: int = 10E6, cflush_addr: int | str = 0x02010200) -> None:
        """
        Initialize the SPITSI object.
        
        Args:
            url (str): Serial port to connect to
            freq (int): SPI Frequency to use
        """
        spi = SpiController()
        spi.configure(url)
        self.spi = spi.get_port(cs=0, freq=freq, mode=0)
        
        super().__init__(cflush_addr)
    
    def _create_header(self, command: Command, addr: int, size: int = 0) -> bytes:
        """
        Write a header to the SPI TSI.
        
        Args:
            command (Command): Command to send
            addr (int): Address to read/write
            size (int): Number of bytes to read/write
        """
        # conver size to TSI size (number of words - 1)
        tsi_size = max(self.align_word(size) // 4 - 1, 0)
        
        return struct.pack("<I", command) + struct.pack("<Q", addr) + struct.pack("<Q", tsi_size)
    
    def _read_bytes(self, addr: int, size: int) -> bytes:
        n_padding = self.align_word(size) - size
        cmd = self._create_header(Command.read, addr, size)
        readlen = size + n_padding + 16

        buffer = self.spi.exchange(cmd, readlen=readlen)
        data_start_idx = buffer.index(0x88) + 1
        return buffer[data_start_idx:data_start_idx+size]

    def _write_bytes(self, addr: int, data: bytes) -> None:
        size = len(data)
        n_padding = self.align_word(len(data)) - len(data)

        cmd = self._create_header(Command.write, addr, size)
        cmd += data
        cmd += b'\xFF' * (n_padding + 2)

        self.spi.exchange(cmd)