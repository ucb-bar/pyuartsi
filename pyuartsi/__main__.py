import struct
import time
from ctypes import *  # noqa: F401, F403

from .uart_tsi import UARTTSI, FESVR_SYSCALLS


def main():
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
    parser.add_argument("--hart1_msip", help="Hart1 MSIP register", action="store_true")
    # parser.add_argument("--hart2_msip", help="Hart1 MSIP register", action="store_true")
    parser.add_argument("--fesvr", help="Run the FESVR interface", action="store_true")
    parser.add_argument("--cflush_addr", help="Cache control base address", type=str, default=0x02010200)
    parser.add_argument("--use_symbols", help="Use symbol addresses for tohost and fromhost instead of .htif section", action="store_true")

    # change message shown on --help
    parser.usage = """python -m pyuartsi [-h] --port PORT [--baudrate BAUDRATE] [--init_write INIT_WRITE] [--init_read INIT_READ]
                   [--elf ELF] [--load] [--selfcheck] [--hart0_msip] [--fesvr] [--cflush_addr CFLUSH_ADDR] [--use_symbols]
examples: python -m pyuartsi --port COM20 --elf <program.elf> --load --hart0_msip
          python -m pyuartsi --port /dev/ttyxx --init_read 0x02000000
          python -m pyuartsi --port /dev/ttyxx --init_write 0x80000000=0xdeadbeef --init_read 0x80000000
          python -m pyuartsi --port /dev/ttyxx --elf <program.elf> --load --hart0_msip --fesvr
          python -m pyuartsi --port /dev/ttyxx --baudrate 921600 --elf <program.elf> --load --selfcheck --hart0_msip --fesvr --cflush_addr 0x02010200
"""  # noqa: E501

    args = parser.parse_args()
    
    print(f"BAUDRATE: {args.baudrate}")
    print("Starting pyuartsi!")

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
    
    if args.hart1_msip:
        tsi.write_longword(0x1000, 0x80000000)

        CLINT_BASE = 0x2000004
        tsi.write_word(CLINT_BASE, 0x1)
        print("Wrote to hart1 MSIP register")
    
    # if args.hart2_msip:
    #     tsi.write_longword(0x1000, 0x80000000)

    #     CLINT_BASE = 0x2000008
    #     tsi.write_word(CLINT_BASE, 0x01)
    #     print("Wrote to hart2 MSIP register")
    
    if args.init_read:
        addr = int(args.init_read, 16)
        value = tsi.read_word(addr)
        print(f"R: {addr:#x} => {value:#x}")

    if args.fesvr:
        print("Proxy FESVR started.")
        start_t = time.time()
        if args.use_symbols:
            tohost, fromhost = tsi.get_symbol_addresses(args.elf, "tohost", "fromhost")
            print(f"Found tohost at {tohost:#x}, fromhost at {fromhost:#x}")
        else:
            htif_base = tsi.get_htif_base(args.elf)
            # htif_base = 0x70000000
            # htif_base = 0x80009808

            print(f"Found HTIF section at {htif_base:#x}")

            tohost = htif_base + 0
            fromhost = htif_base + 8

        # clear tohost memory before starting
        tsi.write_longword(tohost, 0, flush_cache=True)
        print("Write 0 to tohost")

        while True:
            t = time.time() - start_t

            request_ptr = tsi.read_longword(tohost, flush_cache=True)
            # print("Read tohost:", hex(request_ptr))
            # tsi.write_longword(tohost, 0, flush_cache=True)
            if request_ptr != 0:
                # print("{0:2f}".format(t), "\treq ptr:", hex(request_ptr))
                pass

            if request_ptr == 0:
                #print("No request yet, continuing...")
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
                    # print("syscall for FESVR_SYSCALLS: ", end="")
                    print(char, end="")
                except UnicodeDecodeError:
                    print(char_buffer, end="")

            elif syscall_id == FESVR_SYSCALLS.exit:
                print("DUT exit.")
                exit()

            else:
                print("Invalid syscall:", syscall_id)
                print(f"Args: a0={a0:#x}, a1={a1:#x}, a2={a2:#x}")

            # signal the chip that the request has been processed
            # First, check tohost is still the request_ptr (should be, since we just read it)
            current_tohost = tsi.read_longword(tohost, flush_cache=True)
            if current_tohost != request_ptr:
                print(f"Warning: tohost changed from {request_ptr:#x} to {current_tohost:#x}")
            
            # Then clear tohost
            tsi.write_longword(tohost, 0)
            # Write fromhost first to acknowledge
            tsi.write_longword(fromhost, 0x1, flush_cache=True)
  
            
            # # Validate writes
            # read_back_tohost = tsi.read_longword(tohost, flush_cache=True)
            # read_back_fromhost = tsi.read_longword(fromhost, flush_cache=True)
            # if read_back_tohost != 0:
            #     print(f"Error: Failed to write tohost=0, read back {read_back_tohost:#x}")
            # if read_back_fromhost != 1:
            #     print(f"Error: Failed to write fromhost=1, read back {read_back_fromhost:#x}")


if __name__ == "__main__":
    main()
