import struct
from ctypes import *

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


class UARTTSI():
    @staticmethod
    def align_word(addr: int) -> int:
        """
        Align an address to a word boundary, rounding up.
        
        Args:
            addr (int): Address to align
        """
        return (addr + 3) & ~3
    
    def __init__(self, port: str, baudrate: int, cflush_addr: int | str = 0x02010200) -> None:
        """
        Initialize the UARTTSI object.
        
        Args:
            port (str): Serial port to connect to
            baudrate (int): Baudrate to use
        """
        self.ser = SerialImpl(port, baudrate)
        
        if isinstance(cflush_addr, str):
            cflush_addr = int(cflush_addr, 16)
        
        self.cflush_addr = cflush_addr
    
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
        
        self.ser.write(
            struct.pack("<I", command)
            + struct.pack("<Q", addr)
            + struct.pack("<Q", tsi_size))
    
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
        if flush_cache:
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
        if flush_cache:
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
        if flush_cache:
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
        if flush_cache:
            self.flush_cache_lines(addr, self.align_word(len(data)))
        self._write_bytes(addr, data)

    def write_word(self, addr: int, data: int, flush_cache: bool = False) -> None:
        """
        Write a 32 bit word to the UART TSI.
        
        Args:
            addr (int): Address to write to
            data (bytes): Data to write
        """
        if flush_cache:
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
        if flush_cache:
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
                if (section.header.get("sh_type") == "SHT_PROGBITS"
                    and section.header.get("sh_addr") > 0):

                    data = section.data()

                    chunk_size = 1024

                    print("loading section {0} of size {1} at {2:#x}".format(
                        section.name, len(data), section.header["sh_addr"]))
                    
                    for i in track(range(0, len(data), chunk_size), description="loading {0} ".format(section.name).ljust(20)):
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
