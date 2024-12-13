import struct
import time
from ctypes import *

from .uart_tsi import UARTTSI, FESVR_SYSCALLS


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Python port of UART-based TSI")
    parser.add_argument("--port", help="Serial port to connect to", required=True)
    parser.add_argument("--baudrate", type=int, help="Baudrate to use", default=115200)
    parser.add_argument("--init_write", help="Write an initial value to an address", type=str)
    parser.add_argument("--init_read", help="Read an initial value from an address", type=str)
    parser.add_argument("--elf", help="Specify ELF file to load", type=str)
    parser.add_argument("--load", help="Load the ELF file to target", action="store_true")
    parser.add_argument("--selfcheck", help="Run self-check to verify the loaded ELF program", action="store_true")
    parser.add_argument("--hart0_msip", help="Hart0 MSIP register", action="store_true")
    parser.add_argument("--fesvr", help="Run the FESVR interface", action="store_true")
    parser.add_argument("--cflush_addr", help="Cache control base address", type=str, default=0x02010200)

    # change message shown on --help
    parser.usage = """python -m pyuartsi [-h] --port PORT [--baudrate BAUDRATE] [--init_write INIT_WRITE] [--init_read INIT_READ]
                   [--elf ELF] [--load] [--selfcheck] [--hart0_msip] [--fesvr] [--cflush_addr CFLUSH_ADDR]
examples: python -m pyuartsi --port COM20 --elf <program.elf> --load --hart0_msip
          python -m pyuartsi --port /dev/ttyxx --init_read 0x02000000
          python -m pyuartsi --port /dev/ttyxx --init_write 0x80000000:0xdeadbeef --init_read 0x80000000
          python -m pyuartsi --port /dev/ttyxx --elf <program.elf> --load --hart0_msip --fesvr
          python -m pyuartsi --port /dev/ttyxx --baudrate 921600 --elf <program.elf> --load --selfcheck --hart0_msip --fesvr --cflush_addr 0x02010200
"""

    args = parser.parse_args()

    tsi = UARTTSI(args.port, args.baudrate, args.cflush_addr)

    if args.load:
        tsi.load_elf(args.elf, args.selfcheck)
    
    if args.init_write:
        addr, value = args.init_write.split("=")
        addr = int(addr, 16)
        value = int(value, 16)

        tsi.write_word(addr, value)
        print(f"W: {addr:#x} <= {value:#x}")
    
    if args.hart0_msip:
        tsi.write_longword(0x1000, 0x80000000)

        CLINT_BASE = 0x2000000
        tsi.write_word(CLINT_BASE, 0x01)
        print("Wrote to hart0 MSIP register")
    
    if args.init_read:
        addr = int(args.init_read, 16)
        value = tsi.read_word(addr)
        print(f"R: {addr:#x} => {value:#x}")

    if args.fesvr:
        print("Proxy FESVR started.")
        start_t = time.time()
        htif_base = tsi.get_htif_base(args.elf)
        # htif_base = 0x70000000

        print(f"Found HTIF section at {htif_base:#x}")
        
        tohost = htif_base + 0
        fromhost = htif_base + 8
        
        tsi.write_longword(tohost, 0)
        
        while True:
            t = time.time() - start_t

            request_ptr = tsi.read_longword(tohost, flush_cache=True)
            # tsi.write_longword(tohost, 0, flush_cache=True)
            
            if request_ptr == 0:
                continue
            
            if request_ptr == 1 or request_ptr == 0x10000 or request_ptr == 0x13030:
                print("DUT forcefuly exit")
                exit()
            
            if request_ptr == 3:
                print("malloc")
                continue
            # print("{0:2f}".format(t), "\treq ptr:", hex(request_ptr))

            if request_ptr < 0x80000000:
                print("Invalid request pointer:", hex(request_ptr))
                continue

            
            request_buffer = tsi.read_bytes(request_ptr, 8 * 4, flush_cache=True)
            request_args = struct.unpack("<4Q", request_buffer)

            syscall_id = request_args[0]
            a0 = request_args[1]
            a1 = request_args[2]
            a2 = request_args[3]

            # print("syscall:", syscall_id, "a0:", hex(a0), "a1:", hex(a1), "a2:", hex(a2))

            if syscall_id == FESVR_SYSCALLS.write:
                fd = a0
                string_ptr = a1
                size = a2
                
                char_buffer = tsi.read_bytes(string_ptr, size, flush_cache=True)

                try:
                    char = char_buffer.decode("utf-8")
                    print(char, end="")
                except UnicodeDecodeError:
                    print(char_buffer, end="")

            elif syscall_id == FESVR_SYSCALLS.exit:
                print("DUT exit.")
                exit()
            
            else:
                print("Invalid syscall:", syscall_id)

            # signal the chip that the request has been processed
            tsi.write_longword(tohost, 0)
            tsi.write_longword(fromhost, 0x1, flush_cache=True)
                
