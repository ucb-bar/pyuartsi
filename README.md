![PyUARTSI](assets/banner.png)


## Installation

Install from PyPI

```bash
pip install pyuartsi
```

Install from repo

```bash
git clone https://github.com/ucb-bar/pyuartsi.git
cd ./pyuartsi/
pip install .
```


## Usage

```bash
usage: python -m pyuartsi [-h] --port PORT [--baudrate BAUDRATE] [--init_write INIT_WRITE] [--init_read INIT_READ]
                   [--elf ELF] [--load] [--selfcheck] [--hart0_msip] [--fesvr] [--cflush_addr CFLUSH_ADDR]
examples: python -m pyuartsi --port COM20 --elf <program.elf> --load --hart0_msip
          python -m pyuartsi --port /dev/ttyxx --init_read 0x02000000
          python -m pyuartsi --port /dev/ttyxx --init_write 0x80000000:0xdeadbeef --init_read 0x80000000
          python -m pyuartsi --port /dev/ttyxx --elf <program.elf> --load --hart0_msip --fesvr
          python -m pyuartsi --port /dev/ttyxx --baudrate 921600 --elf <program.elf> --load --selfcheck --hart0_msip --fesvr --cflush_addr 0x02010200

Python port of UART-based TSI

options:
  -h, --help            show this help message and exit
  --port PORT           Serial port to connect to
  --baudrate BAUDRATE   Baudrate to use
  --init_write INIT_WRITE
                        Write an initial value to an address
  --init_read INIT_READ
                        Read an initial value from an address
  --elf ELF             Specify ELF file to load
  --load                Load the ELF file to target
  --selfcheck           Run self-check to verify the loaded ELF program
  --hart0_msip          Hart0 MSIP register
  --fesvr               Run the FESVR interface
  --cflush_addr CFLUSH_ADDR
                        Cache control base address
```

## Errata

- The last `printf()` syscall on the DUT program will be printed twice for some reason.

- Always reset DUT before launching new program.

- The Proxy FESVR currently only supports `_write()` and `_exit()` syscall.


## See Also

C++ implementation [uart_tsi](https://github.com/ucb-bar/testchipip/tree/master/uart_tsi)

Rust implementation [TSI](https://github.com/ucb-bar/tsi)

