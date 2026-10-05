`default_nettype none
`timescale 1ns / 1ps

/* This testbench just instantiates the module and makes some convenient wires
   that can be driven / tested by the cocotb test.py.
*/
module tb ();

  // Dump the signals to a VCD file. You can view it with gtkwave.
  initial begin
    $dumpfile("tb.vcd");
    $dumpvars(0, tb);
    #1;
  end

  // Wire up the inputs and outputs:
  reg clk;
  reg rst_n;
  reg ena;
  reg [7:0] ui_in;
  reg master_scl;
  reg master_sda_low;
  reg addr_select;
  reg write_en;
  reg [3:0] write_addr;
  wire [7:0] uo_out;
  wire [7:0] uio_out;
  wire [7:0] uio_oe;
  wire sda_pin;
  wire [7:0] uio_in;

  // Open-drain SDA: slave drive-low or master drive-low, otherwise pull up.
  assign sda_pin = (uio_oe[1] && !uio_out[1]) ? 1'b0 : (master_sda_low ? 1'b0 : 1'b1);
  assign uio_in  = {write_addr, write_en, addr_select, sda_pin, master_scl};

  initial begin
    master_scl     = 1'b1;
    master_sda_low = 1'b0;
    addr_select    = 1'b0;
    write_en       = 1'b0;
    write_addr     = 4'h0;
  end

  tt_um_venkataratnamb20_i2c user_project (

      // Include power ports for the Gate Level test:
`ifdef GL_TEST
      .VPWR(1'b1),
      .VGND(1'b0),
`endif

      .ui_in  (ui_in),    // Dedicated inputs
      .uo_out (uo_out),   // Dedicated outputs
      .uio_in (uio_in),   // IOs: Input path
      .uio_out(uio_out),  // IOs: Output path
      .uio_oe (uio_oe),   // IOs: Enable path (active high: 0=input, 1=output)
      .ena    (ena),      // enable - goes high when design is selected
      .clk    (clk),      // clock
      .rst_n  (rst_n)     // not reset
  );

endmodule
