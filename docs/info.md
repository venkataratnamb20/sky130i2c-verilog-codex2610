# I2C RAM slave

## How it works

The design is an I2C target with 16 bytes of RAM. The project clock is 50 MHz. SCL and SDA are sampled through matched synchronizers. There is no clock stretching.

The 7-bit address is `{6'b100001, address_select}`:

- `uio[2]` low: `0x42`
- `uio[2]` high: `0x43`

A matching read starts at byte 0 and sends each byte MSB first. The controller ACKs every byte it wants to continue. A NACK ends the transfer, and the next matching read starts at byte 0 again, including after a repeated START. If the controller ACKs byte 15 and keeps clocking, SDA is released, so those extra bytes read `0xFF`.

A matching write address is NACKed. Any other address leaves SDA released.

Each data byte is copied into a shift register before its first bit. A host write after that copy does not change the byte already on the wire. A later byte in the same read can observe a newer RAM value.

Host writes are synchronous to `clk`:

- `ui[7:0]` is the write data
- `uio[7:4]` is the write address
- `uio[3]` is the write enable

`uo[7:0]` shows the byte latched for the current read, or `0` when the bus is idle.

SDA is open-drain. `uio_out[1]` stays low and `uio_oe[1]` is high only while the target is pulling SDA low. External pull-up resistors are required on SCL and SDA.

## How to test

From `test/`:

```sh
make
```

The cocotb tests use a 20 ns project clock. They cover both address straps, rejected writes and unknown addresses, constant patterns, a full 16-byte read, early NACK, repeated START, overread, reset during a transfer, a byte that stays stable after it is latched, and one full read at 100 kHz SCL plus the other reads at 1 MHz SCL.

On a board, tie the address-select pin, add pull-ups, and issue a plain I2C read of 16 bytes from `0x42` or `0x43`. Do not send a register address first.

## External hardware

I2C controller and pull-up resistors on SCL (`uio[0]`) and SDA (`uio[1]`). The pull-up voltage must match the chip I/O supply. This simulation does not show that the packaged pads meet Fast-mode Plus electrical limits.
