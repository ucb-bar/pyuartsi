import struct
from ctypes import *  # noqa: F401, F403

import serial
from elftools.elf.elffile import ELFFile
from rich.progress import track


class FESVR_SYSCALLS:
    _exit = 1
    write = 64
    exit = 93

class Command:
    read = 0
    write = 1

class TSI():
    @staticmethod
    def align_word(addr: int) -> int:
        """
        Align an address to a word boundary, rounding up.

        Args:
            addr (int): Address to align
        """
        return (addr + 3) & ~3

    def __init__(self, cflush_addr: int | str = 0x02010200) -> None:
        """
        Initialize the common TSI parameters.

        Args:
            cflush_addr (int | str): Cache flush address, set to 0 to disable
        """

        if isinstance(cflush_addr, str):
            cflush_addr = int(cflush_addr, 16)

        self.cflush_addr = cflush_addr

    # Functions
    def _read_bytes(self, addr: int, size: int) -> bytes:
        raise RuntimeError('_read_bytes function unimplemented')
        
    def _write_bytes(self, addr: int, data: bytes) -> None:
        raise RuntimeError('_write_bytes function unimplemented')

    def flush_cache_lines(self, addr: int, size: int) -> None:
        """
        Flush cache lines to memory.

        Args:
            addr (int): Address to flush
            size (int): Number of bytes to flush
        """
        if not addr:
            return

        cblock_bytes = 64
        base = addr & ~(cblock_bytes - 1)

        while base < addr + size:
            buffer = struct.pack("<Q", base)
            self._write_bytes(self.cflush_addr, buffer)
            base += cblock_bytes

    def read_bytes(self, addr: int, size: int, flush_cache: bool = False) -> bytes:
        """
        Read a chunk of data from the UART TSI.

        Args:
            addr (int): Address to read from
            size (int): Number of bytes to read
        """
        if flush_cache and self.cflush_addr != 0:
            self.flush_cache_lines(addr, self.align_word(size))
        buffer = self._read_bytes(addr, size)

        return buffer

    def read_word(self, addr: int, flush_cache: bool = False) -> int:
        """
        Read a 32 bit word from the UART TSI.

        Args:
            addr (int): Address to read from
        """
        size = 4
        if flush_cache and self.cflush_addr != 0:
            self.flush_cache_lines(addr, size)
        self._write_header(Command.read, addr, size)
        buffer = self.ser.read(size)
        value = struct.unpack("<I", buffer)[0]

        return value

    def read_longword(self, addr: int, flush_cache: bool = False) -> int:
        """
        Read a 64 bit word from the UART TSI.

        Args:
            addr (int): Address to read from
        """
        size = 8
        if flush_cache and self.cflush_addr != 0:
            self.flush_cache_lines(addr, size)
        self._write_header(Command.read, addr, size)
        buffer = self.ser.read(size)
        value = struct.unpack("<Q", buffer)[0]

        return value

    def write_bytes(self, addr: int, data: bytes, flush_cache: bool = False) -> None:
        """
        Write a chunk of data to the UART TSI.

        Args:
            addr (int): Address to write to
            data (bytes): Data to write
        """
        if flush_cache and self.cflush_addr != 0:
            self.flush_cache_lines(addr, self.align_word(len(data)))
        self._write_bytes(addr, data)

    def write_word(self, addr: int, data: int, flush_cache: bool = False) -> None:
        """
        Write a 32 bit word to the UART TSI.

        Args:
            addr (int): Address to write to
            data (bytes): Data to write
        """
        if flush_cache and self.cflush_addr != 0:
            self.flush_cache_lines(addr, 4)
        buffer = struct.pack("<I", data)
        self.write_bytes(addr, buffer)

    def write_longword(self, addr: int, data: int, flush_cache: bool = False) -> None:
        """
        Write a 64 bit word to the UART TSI.

        Args:
            addr (int): Address to write to
            data (bytes): Data to write
        """
        if flush_cache and self.cflush_addr != 0:
            self.flush_cache_lines(addr, 8)
        buffer = struct.pack("<Q", data)
        self.write_bytes(addr, buffer)

    def load_elf(self, filename: str, check: bool = False) -> None:
        """
        Load an ELF file to the UART TSI.

        Args:
            filename (str): ELF file to load
        """
        with open(filename, "rb") as f:
            elf_file = ELFFile(f)

            for section in elf_file.iter_sections():
                if (section.header.get("sh_addr") > 0):

                    data = section.data()

                    chunk_size = 1024

                    print("loading section {0} of size {1} at {2:#x}".format(
                        section.name, len(data), section.header["sh_addr"]))

                    for i in track(
                        range(0, len(data), chunk_size),
                        description="loading {0} ".format(section.name).ljust(20),
                    ):
                        loaded_size = min(chunk_size, len(data) - i)

                        # self.flush_cache_lines(section.header["sh_addr"] + i, loaded_size)
                        self.write_bytes(section.header["sh_addr"] + i, data[i:i + loaded_size])

                        if check:
                            # self.flush_cache_lines(section.header["sh_addr"] + i, loaded_size)
                            buffer = self.read_bytes(section.header["sh_addr"] + i, loaded_size)
                            if buffer[:loaded_size] != data[i:i + loaded_size]:
                                print("ERROR: data mismatch")
                                print("expected:", data[i:i + loaded_size])
                                print("got:", buffer[:loaded_size])

    def get_htif_base(self, filename: str) -> int:
        """
        Get the HTIF base address.

        Args:
            filename (str): ELF file to load

        Returns:
            int: HTIF base address
        """
        htif_base = 0x80000000

        with open(filename, "rb") as f:
            elf_file = ELFFile(f)

            for section in elf_file.iter_sections():
                if section.name == ".htif":
                    htif_base = section.header["sh_addr"]
                    break

        return htif_base
