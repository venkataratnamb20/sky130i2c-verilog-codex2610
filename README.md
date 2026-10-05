![](../../workflows/gds/badge.svg) ![](../../workflows/docs/badge.svg) ![](../../workflows/test/badge.svg) ![](../../workflows/fpga/badge.svg)

# I2C RAM slave

16-byte I2C target for Tiny Tapeout. A read at `0x42` or `0x43` returns RAM bytes 0 through 15. The address strap, pin map, and cocotb checks are described in [docs/info.md](docs/info.md).

SCL is `uio[0]` and SDA is open-drain on `uio[1]`. Both nets need external pull-ups. `uio[2]` selects `0x42` when low and `0x43` when high. RAM writes use `ui[7:0]`, `uio[7:4]`, and `uio[3]`, and are sampled on `clk`. The project clock in [info.yaml](info.yaml) is 50 MHz.

## Simulate

```sh
cd test
make
```

`make` runs the cocotb tests in `test/test.py` with Icarus Verilog. Pushing to this repository also runs the Tiny Tapeout test, GDS, docs, and FPGA GitHub Actions.

## Tiny Tapeout

This project uses the Tiny Tapeout Verilog template. The GDS flow is [OpenLane](https://www.zerotoasiccourse.com/terminology/openlane/) via the `tt08` GitHub actions. See the [Tiny Tapeout documentation](https://tinytapeout.com) and the [FAQ](https://tinytapeout.com/faq/) before submitting the design to a shuttle.
