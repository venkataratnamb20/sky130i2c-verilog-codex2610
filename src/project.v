/*
 * Copyright (c) 2026 venkataratnamb20
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

module tt_um_venkataratnamb20_i2c (
    input  wire [7:0] ui_in,    // Dedicated inputs
    output wire [7:0] uo_out,   // Dedicated outputs
    input  wire [7:0] uio_in,   // IOs: Input path
    output wire [7:0] uio_out,  // IOs: Output path
    output wire [7:0] uio_oe,   // IOs: Enable path (active high: 0=input, 1=output)
    input  wire       ena,      // always 1 when the design is powered, so you can ignore it
    input  wire       clk,      // clock
    input  wire       rst_n     // reset_n - low to reset
);

  wire sda_drive;

  i2c_slave_ram core (
      .clk        (clk),
      .rst_n      (rst_n),
      .write_data (ui_in),
      .write_addr (uio_in[7:4]),
      .write_en   (uio_in[3]),
      .addr_select(uio_in[2]),
      .scl        (uio_in[0]),
      .sda_in     (uio_in[1]),
      .latched_byte(uo_out),
      .sda_drive  (sda_drive)
  );

  // SDA is open-drain: drive low or release. SCL is input only.
  assign uio_out = 8'h00;
  assign uio_oe  = {6'b000000, sda_drive, 1'b0};

  wire _unused = &{ena, 1'b0};

endmodule

`default_nettype wire
