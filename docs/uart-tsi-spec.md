# UART TSI Protocol Specification

This document specifies the UART Tethered Serial Interface (UART TSI). A host
computer uses UART TSI to read and write the memory of a RISC-V SoC through
one serial line. The target runs no firmware for the link. A hardware decoder
converts each command into bus transactions.

This document describes the behavior of existing implementations. It does not
define new behavior. The sources are the testchipip RTL and C++ host, the
FESVR library, and the PyUARTSI source, as checked on 2026-10-01.

| Property          | Value                      |
| ----------------- | -------------------------- |
| Line format       | UART, 8N1, no flow control |
| Default baud rate | 115200                     |
| Link word         | 32 bits                    |
| Header            | 20 bytes                   |
| Address           | 64 bits                    |
| Commands          | 2: `READ`, `WRITE`         |

## Contents

1. [Conventions](#1-conventions)
2. [Overview](#2-overview)
3. [System structure](#3-system-structure)
4. [Physical layer](#4-physical-layer)
5. [Command format](#5-command-format)
6. [Byte order](#6-byte-order)
7. [Transactions](#7-transactions)
8. [Decoder state machine](#8-decoder-state-machine)
9. [Address conventions](#9-address-conventions)
10. [FESVR proxy](#10-fesvr-proxy)
11. [Bring-up sequence](#11-bring-up-sequence)
12. [Constraints](#12-constraints)
13. [Host differences](#13-host-differences)
14. [References](#14-references)

## 1. Conventions

This document uses the key words MUST, MUST NOT, SHOULD, and MAY as
[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) defines them.

All multi-byte fields are unsigned and little-endian. Hexadecimal numbers use
`_` to group digits: `0x8000_0000` is `0x80000000`. Sizes use B for bytes.
1 KiB is 1024 B, and 1 kB is 1000 B.

| Term            | Meaning                                                                        |
| --------------- | ------------------------------------------------------------------------------ |
| Host            | The computer that runs the host program, for example PyUARTSI.                 |
| Reference hosts | The testchipip C++ host and PyUARTSI.                                          |
| Target          | The SoC that contains the TSI decoder.                                         |
| Decoder         | The `TSIToTileLink` module in the target.                                      |
| Word            | 4 bytes (32 bits). The decoder receives and sends one word at a time.          |
| Command         | One header, followed by its payload (write) or its reply (read).               |
| Chunk           | The data of one command. Hosts split large transfers into chunks.              |
| Beat            | One data transfer on the TileLink bus. Its size is the bus data width.         |
| Hart            | A RISC-V hardware thread.                                                      |
| FESVR           | Front-end server. Host software that serves system calls for a target program. |
| HTIF            | Host-target interface. The `tohost` and `fromhost` mailbox that FESVR uses.    |

## 2. Overview

UART TSI connects one host to one target. The host is the only initiator. The
target sends bytes only as the reply to a read command.

| Role   | Implementation                      | Responsibility                                                |
| ------ | ----------------------------------- | ------------------------------------------------------------- |
| Host   | PyUARTSI, testchipip C++ `uart_tsi` | Sends every command. Holds the ELF file. Serves system calls. |
| Target | testchipip `TSIToTileLink`          | Decodes commands. Drives the TileLink bus. Sends read data.   |

The protocol has two commands:

| `cmd` | Name    | Payload from host     | Reply from target                 |
| ----- | ------- | --------------------- | --------------------------------- |
| `0`   | `READ`  | None                  | `4 × (len + 1)` bytes. No status. |
| `1`   | `WRITE` | `4 × (len + 1)` bytes | None.                             |

The host builds all other operations from these two commands. Program load,
hart start, and console output are memory accesses to agreed addresses.
[Section 9](#9-address-conventions) lists these addresses.

## 3. System structure

The target has three modules in series between the UART pins and the bus. The testchipip trait `CanHavePeripheryUARTTSI` adds them to the SoC.

```
+--------------------+
| Host program       |  PyUARTSI, or the testchipip C++ host
+---------+----------+
          |  USB
+---------+----------+
| USB-UART bridge    |
+---------+----------+
          |  TXD, RXD (UART 8N1)
==========|=====================================  target SoC boundary
          |
+---------+----------+
| UARTToSerial       |  UART receiver and transmitter, one byte queue each
+---------+----------+
          |  8-bit bytes
+---------+----------+
| SerialWidthAdapter |  4 bytes <-> 1 word
+---------+----------+
          |  32-bit words
+---------+----------+
| TSIToTileLink      |  the decoder, a TileLink client
+---------+----------+
          |  TileLink, front bus (FBUS) by default
          v
   target memory map: DRAM, CLINT, L2 cache flush register, ...
```

`SerialWidthAdapter` is the only module that handles bytes. The decoder
receives and sends 32-bit words. The word width is fixed at 32 bits
(`TSI.WIDTH`) to match FESVR.

The target exports two debug signals:

- `dropped`: the receive queue overflowed.
- `tsi2tl_state`: the current state of the decoder.

## 4. Physical layer

The link is an asynchronous serial line with no parity and no flow control.

| Parameter             | Value    | Notes                                                              |
| --------------------- | -------- | ------------------------------------------------------------------ |
| Data bits             | 8        | Least significant bit first.                                       |
| Parity                | None     | No layer has error detection.                                      |
| Stop bits             | 1        | The target transmitter sets `nstop = 0`, which selects 1 stop bit. |
| Hardware flow control | None     | RTS/CTS off.                                                       |
| Software flow control | None     | XON/XOFF off.                                                      |
| Signals               | TXD, RXD | One wire for each direction.                                       |

One frame carries one byte in 10 bit times: 1 start bit, 8 data bits, and
1 stop bit. The byte rate is `baud / 10`. The line is full duplex, but the
protocol sends in one direction at a time.

### 4.1 Baud rate

The target sets its bit period at elaboration:

```
div = freqHz / initBaudRate
```

`freqHz` is the clock frequency of the bus that holds the decoder.
`initBaudRate` comes from `UARTParams`. Both reference hosts default to
115200 baud.

The host baud rate MUST equal the rate in the target RTL. A different rate
corrupts data, and no layer reports an error.

### 4.2 Throughput

The table shows the time for one write command with 1 KiB of payload. The
command is 1044 B on the line: a 20 B header and a 1024 B payload. The values
assume no idle time between frames.

| Baud rate | Byte rate | Time for 1 KiB write | Payload rate |
| --------- | --------- | -------------------- | ------------ |
| 115200    | 11.5 kB/s | 90.6 ms              | 11.3 kB/s    |
| 921600    | 92.2 kB/s | 11.3 ms              | 90.4 kB/s    |
| 2000000   | 200 kB/s  | 5.2 ms               | 196 kB/s     |
| 4000000   | 400 kB/s  | 2.6 ms               | 392 kB/s     |

For a 1024-byte chunk, the header is 1.9 % of the line traffic. A read-back
check sends each chunk a second time, so it halves the load rate.

## 5. Command format

Every command starts with the same 20-byte header.

```
Offset  0       4                       12                      20
        +-------+-----------------------+-----------------------+- - - - - - - -
        |  cmd  |         addr          |          len          |  payload
        |  u32  |          u64          |          u64          |  4 × (len + 1) B
        +-------+-----------------------+-----------------------+- - - - - - - -
        |<----------------- header, 20 bytes ------------------>|
```

| Offset | Field  | Type  | Definition                                           |
| ------ | ------ | ----- | ---------------------------------------------------- |
| `0x00` | `cmd`  | `u32` | `0` = `READ`, `1` = `WRITE`.                         |
| `0x04` | `addr` | `u64` | Byte address in the target. MUST be a multiple of 4. |
| `0x0C` | `len`  | `u64` | Number of words minus one: `ceil(size / 4) - 1`.     |

These rules apply to the fields:

- `len` counts words, not bytes. A one-word command has `len = 0`.
- The payload or reply is always `4 × (len + 1)` bytes. The format cannot
  express a command with zero bytes.
- If `cmd` is not `0` or `1`, the decoder asserts in simulation. In hardware,
  the behavior is undefined.
- The decoder ignores `addr[1:0]` when it places write data. An unaligned
  read can give a TileLink request that is not legal.

### 5.1 Partial words

The link carries whole words only. If a transfer is not a multiple of 4
bytes, the host fills the last word:

- The testchipip C++ host reads each partial word, merges the new bytes, and
  writes the word back. Memory outside the transfer does not change.
- PyUARTSI pads the last word with `0xFF` bytes. The target writes these pad
  bytes to memory.
- On a read, the target returns whole words. The host discards the extra
  bytes.

**Caution:** Write whole words when the bytes after the data must not change.
PyUARTSI writes up to 3 pad bytes of `0xFF` after the data.

### 5.2 Example

This command writes `0xDEADBEEF` to `0x8000_0000`. The command is 24 bytes:

```
Offset  Bytes                     Field
0x00    01 00 00 00               cmd     = 1 (WRITE)
0x04    00 00 00 80 00 00 00 00   addr    = 0x0000_0000_8000_0000
0x0C    00 00 00 00 00 00 00 00   len     = 0 (one word)
0x14    EF BE AD DE               payload = 0xDEADBEEF
```

The only non-zero byte of `addr` is at offset `0x07`, because the field is
little-endian.

## 6. Byte order

Little-endian order applies at two levels:

1. A 64-bit field goes as two words: bits `[31:0]` first, then bits `[63:32]`.
2. A word goes as four bytes: bits `[7:0]` first, bits `[31:24]` last.

Thus the header is five words:

| Word | Content       | Bytes |
| ---- | ------------- | ----- |
| 0    | `cmd`         | 0–3   |
| 1    | `addr[31:0]`  | 4–7   |
| 2    | `addr[63:32]` | 8–11  |
| 3    | `len[31:0]`   | 12–15 |
| 4    | `len[63:32]`  | 16–19 |

The result is the byte sequence of a packed little-endian structure.
PyUARTSI builds the header with `struct.pack("<IQQ", cmd, addr, len)`.

## 7. Transactions

A write gets no reply. A read gets data with no framing.

```
WRITE (cmd = 1)                         READ (cmd = 0)

Host                     Target         Host                     Target
 |                         |             |                         |
 |  header, 20 B           |             |  header, 20 B           |
 |------------------------>|             |------------------------>|
 |                         |             |                         |
 |  payload,               |             |  reply data,            |
 |  4 × (len + 1) B        |             |  4 × (len + 1) B        |
 |------------------------>|             |<------------------------|
 |                         |             |                         |
 |  no reply               |             |  no header, no status   |
 |                         |             |                         |
```

The reply to a read has no header and no status. The value of `len` is the
only delimiter. If one byte is lost, the host and the target stay out of step
until a target reset.

A host MUST obey these rules:

1. The host MUST send the complete payload of a write before it sends the
   next header.
2. The host MUST receive all `4 × (len + 1)` reply bytes of a read before it
   sends the next header. During a read, the decoder accepts no input, so
   bytes from the host fill the receive queue.
3. The host SHOULD split large transfers into chunks of 1024 bytes or fewer.
   Both reference hosts load programs in 1024-byte chunks.
4. On a design that needs a cache flush, the host SHOULD flush the covering
   cache lines before it reads memory. See
   [section 9.1](#91-cache-flush).

## 8. Decoder state machine

The decoder has nine states. The header states are common to both commands.
The decoder selects the write or read branch after it receives `len`.

```
              +-------+     +--------+     +-------+
  reset ----->| s_cmd |---->| s_addr |---->| s_len |
              +-------+     +--------+     +-------+
                  ^                            |
                  |              cmd = 1       |  cmd = 0
                  |           +----------------+---------------+
                  |           v                                v
                  |    +--------------+                 +-------------+
                  |    | s_write_body |<---+            | s_read_req  |<----+
                  |    +--------------+    |            +-------------+     |
                  |           v            |                   v            |
                  |    +--------------+    |            +-------------+     |
                  |    | s_write_data |    |            | s_read_data |     |
                  |    +--------------+    |            +-------------+     |
                  |           v            |                   v            |
                  |    +--------------+    |            +-------------+     |
                  |    | s_write_ack  |----+            | s_read_body |-----+
                  |    +--------------+ more words      +-------------+  more words
                  |           |                                |
                  |           | last word                      | last word
                  |           |                                |
                  +-----------+--------------------------------+
```

Each loop in the diagram runs once per bus beat, not once per word.

| State          | Waits for           | Action                                                                                                                        |
| -------------- | ------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `s_cmd`        | 1 word              | Stores `cmd`. Clears `addr` and `len`.                                                                                        |
| `s_addr`       | 2 words             | Assembles `addr`, low word first.                                                                                             |
| `s_len`        | 2 words             | Assembles `len`, low word first. Selects the branch from `cmd`.                                                               |
| `s_write_body` | Input words         | Stores words in the beat buffer and sets their byte mask. Stops at the end of the beat or at the last word.                   |
| `s_write_data` | TileLink A ready    | Sends a masked TileLink `Put` for the beat.                                                                                   |
| `s_write_ack`  | TileLink D response | If words remain, moves to the next beat and goes to `s_write_body`. Otherwise goes to `s_cmd`.                                |
| `s_read_req`   | TileLink A ready    | Sends a TileLink `Get` for the rest of the current beat, or less if `len` ends first.                                         |
| `s_read_data`  | TileLink D response | Stores the beat data.                                                                                                         |
| `s_read_body`  | Output ready        | Sends one word per cycle. At the end of the beat, goes to `s_read_req` if words remain. After the last word, goes to `s_cmd`. |

The decoder accepts input words only in `s_cmd`, `s_addr`, `s_len`, and
`s_write_body`. The decoder has no reset command. If a command is incomplete,
only a target reset returns the decoder to `s_cmd`.

## 9. Address conventions

UART TSI has no control commands. The host controls the target through
writes to the addresses below. These are the defaults of the reference hosts.
A specific SoC can use other addresses.

| Address       | Width  | Name           | Use                                                              |
| ------------- | ------ | -------------- | ---------------------------------------------------------------- |
| `0x0000_1000` | 64 bit | Boot address   | Write the start address of the program before hart 0 starts.     |
| `0x0200_0000` | 32 bit | Hart 0 MSIP    | Write `1` to raise the software interrupt that starts hart 0.    |
| `0x0201_0200` | 64 bit | L2 cache flush | Write a line address to flush that 64-byte line. SiFive L2 only. |
| `0x8000_0000` | —      | DRAM base      | Default load address and default HTIF base.                      |

### 9.1 Cache flush

Some designs need a cache flush before the host reads memory that a hart
wrote. On designs with a SiFive L2 cache, the flush register is at
`0x0201_0200`. To read a range with a flush:

1. Round the start address of the range down to a multiple of 64.
2. Write the line address as a 64-bit value to the flush register.
3. Add 64 to the line address.
4. If the line address is less than the end of the range, go to step 2.
5. Read the range.

**Caution:** Set a flush address only on a design that has the flush
register. On a design without an L2 cache, a write to `0x0201_0200` stops the
TSI link.

## 10. FESVR proxy

UART TSI has no console channel. A target program makes system calls through
two 64-bit mailbox words in target memory, `tohost` and `fromhost`. The host
reads and writes the mailbox with ordinary TSI commands.

### 10.1 Mailbox location

PyUARTSI finds the mailbox in this order:

1. If the ELF symbol table has both `tohost` and `fromhost`, use the symbol
   addresses.
2. If the ELF file has a `.htif` section, `tohost` is the section address.
   `fromhost` is `tohost + 8`.
3. Otherwise, `tohost` is `0x8000_0000` and `fromhost` is `0x8000_0008`.

Baremetal-IDE programs put `fromhost` before `tohost`. Thus a host MUST NOT
assume a fixed order of the two words.

### 10.2 Request block

A value of `0x8000_0000` or more in `tohost` is the address of a 32-byte
request block:

| Offset | Field          | Type  |
| ------ | -------------- | ----- |
| `0x00` | System call ID | `u64` |
| `0x08` | `arg0`         | `u64` |
| `0x10` | `arg1`         | `u64` |
| `0x18` | `arg2`         | `u64` |

### 10.3 Host loop

The host serves requests in this loop:

1. Read `tohost` as a 64-bit value, with a cache flush.
2. If the value is less than `0x8000_0000`, do the action that
   [section 10.4](#104-reserved-values) gives.
3. Read the 32-byte request block at the address in `tohost`, with a cache
   flush.
4. Do the system call. See [section 10.5](#105-system-calls).
5. Acknowledge: write `0` to `tohost`. Then write `1` to `fromhost`, with a
   cache flush.
6. Go to step 1.

The host MUST NOT clear `tohost` when it starts. A running program can
already have a request in `tohost`.

Each poll of `tohost` is one read command: a 20-byte header and an 8-byte
reply. When the cache flush is on, each poll also sends one flush write.

### 10.4 Reserved values

Values below `0x8000_0000` in `tohost` are not addresses:

| Value in `tohost`                   | Meaning            | Host action                       |
| ----------------------------------- | ------------------ | --------------------------------- |
| `0`                                 | No request         | Read `tohost` again.              |
| `3`                                 | Allocation request | Acknowledge. Read `tohost` again. |
| `1`, `0x10000`, `0x13030`           | Forced exit        | Stop with exit status 1.          |
| Any other value below `0x8000_0000` | Invalid pointer    | Stop with a protocol error.       |

### 10.5 System calls

PyUARTSI supports these system calls:

| System call ID | Name            | Arguments            | Host action                                                                                           |
| -------------- | --------------- | -------------------- | ----------------------------------------------------------------------------------------------------- |
| `64`           | `write`         | `fd`, `buf`, `count` | Read `count` bytes at `buf`. Write them to stdout if `fd = 1`, or to stderr if `fd = 2`. Acknowledge. |
| `93`           | `exit`          | `status`             | Acknowledge. Stop with exit status `status`.                                                          |
| `1`            | `exit` (legacy) | `status`             | Same as `93`.                                                                                         |

Any other system call ID, or a `write` to another `fd`, is a protocol error.

## 11. Bring-up sequence

Use this sequence to load and start a program:

1. Reset the target. The decoder keeps a partly decoded header after the host
   exits.
2. Open the serial port at the baud rate of the target.
3. Make sure that no bytes arrive on the line. A received byte means that the
   target is in a command, or that other traffic uses the port.
4. Write each `SHT_PROGBITS` section of the ELF file that has a non-zero
   address. Use chunks of 1024 bytes or fewer.
5. To detect corrupted writes, read back each chunk and compare it with the
   ELF data.
6. Write the start address of the program as a 64-bit value to `0x0000_1000`.
7. Write `1` to the hart 0 MSIP register at `0x0200_0000`. Hart 0 starts to
   execute the program.
8. Serve FESVR requests until the program exits. The host returns the exit
   status of the program.

This PyUARTSI command does steps 2 and 4 to 8:

```console
pyuartsi --port /dev/ttyUSB0 --elf program.elf --load --self-check --hart0-msip --fesvr
```

In step 6, `--hart0-msip` writes `0x8000_0000`, not the ELF entry address.
For step 3, see [section 13](#13-host-differences).

## 12. Constraints

An implementation must handle these properties of UART TSI:

| Condition                 | Effect                                                                                                    | Mitigation                                       |
| ------------------------- | --------------------------------------------------------------------------------------------------------- | ------------------------------------------------ |
| No integrity check        | The target accepts a corrupted byte as data.                                                              | Read back and compare.                           |
| No write response         | A failed write is silent.                                                                                 | Read back and compare.                           |
| No flow control           | If the bus stalls, the receive queue overflows. The target sets `dropped`, and the link goes out of step. | Monitor `dropped`. Use a lower baud rate.        |
| Baud rate fixed in RTL    | A host rate that does not match corrupts data, without an error.                                          | Use the rate in the target RTL.                  |
| No resynchronization      | One lost byte misaligns every field after it.                                                             | Reset the target and restart the host.           |
| Decoder keeps its state   | The decoder state stays after the host exits.                                                             | Reset the target before each run.                |
| Write to a missing device | On a design without an L2 cache, a write to `0x0201_0200` stops the link.                                 | Set a flush address only if the register exists. |

UART TSI is for FPGA prototypes and FPGA test harnesses. The testchipip source
states that it is not for ASIC implementations.

## 13. Host differences

The two reference hosts differ in these behaviors:

| Behavior              | testchipip C++ host                                    | PyUARTSI                                                                                    |
| --------------------- | ------------------------------------------------------ | ------------------------------------------------------------------------------------------- |
| Port check at open    | Waits 1 s. Stops if a byte arrives.                    | Discards the input and output buffers. No check.                                            |
| Partial words         | Reads, merges, and writes back each partial word.      | Pads the last word with `0xFF`. Sends `addr` unchanged.                                     |
| Cache flush           | Before every read and write, if `+cflush_addr` is set. | Before FESVR accesses and API calls with `flush_cache=True`, if the flush address is not 0. |
| Default flush address | 0 (off)                                                | 0 (off)                                                                                     |
| Chunk size            | 1024 B for all transfers                               | 1024 B for ELF loads (`chunk_size`). Other calls send one command per call.                 |
| Load verification     | `+selfcheck`                                           | `--self-check`                                                                              |
| System calls          | The FESVR system-call proxy                            | `write`, `exit`, and legacy `exit`                                                          |

## 14. References

| Component     | Language | Source                                                                                                                      |
| ------------- | -------- | --------------------------------------------------------------------------------------------------------------------------- |
| Target RTL    | Chisel   | [ucb-bar/testchipip](https://github.com/ucb-bar/testchipip): `src/main/scala/tsi/`, `uart/`, `serdes/`                      |
| C++ host      | C++      | [testchipip/uart_tsi](https://github.com/ucb-bar/testchipip/tree/master/uart_tsi)                                           |
| FESVR library | C++      | [riscv-isa-sim/fesvr](https://github.com/riscv-software-src/riscv-isa-sim/tree/master/fesvr): `tsi.h`, `tsi.cc`, `memif.cc` |
| Python host   | Python   | [ucb-bar/pyuartsi](https://github.com/ucb-bar/pyuartsi)                                                                     |
| Rust host     | Rust     | [ucb-bar/tsi](https://github.com/ucb-bar/tsi)                                                                               |
