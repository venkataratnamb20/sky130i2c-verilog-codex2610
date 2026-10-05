/*
 * Copyright (c) 2026 venkataratnamb20
 * SPDX-License-Identifier: Apache-2.0
 *
 * 16-byte I2C target. The 7-bit address is {6'b100001, addr_select}.
 * Reads start at byte 0. Writes are NACKed. After byte 15, further
 * clocks release SDA. Each data byte is copied into a shift register
 * before its first bit.
 */

`default_nettype none

module i2c_slave_ram (
    input  wire       clk,
    input  wire       rst_n,
    input  wire [7:0] write_data,
    input  wire [3:0] write_addr,
    input  wire       write_en,
    input  wire       addr_select,
    input  wire       scl,
    input  wire       sda_in,
    output wire [7:0] latched_byte,
    output wire       sda_drive
);

  localparam [3:0] ST_IDLE       = 4'd0;
  localparam [3:0] ST_ADDR       = 4'd1;
  localparam [3:0] ST_ADDR_ACK   = 4'd2;
  localparam [3:0] ST_ACK_HI     = 4'd3;
  localparam [3:0] ST_DATA_SETUP = 4'd4;
  localparam [3:0] ST_DATA       = 4'd5;
  localparam [3:0] ST_DATA_REL   = 4'd6;
  localparam [3:0] ST_DATA_ACK   = 4'd7;

  // Matched 2-flop synchronizers and a 2-sample stability filter.
  reg [1:0] scl_sync;
  reg [1:0] sda_sync;
  reg       scl_meta_d;
  reg       sda_meta_d;
  reg       scl_clean;
  reg       sda_clean;
  reg       scl_clean_d;
  reg       sda_clean_d;
  reg [1:0] addr_sync;

  wire scl_meta = scl_sync[1];
  wire sda_meta = sda_sync[1];
  wire scl_rise = scl_clean & ~scl_clean_d;
  wire scl_fall = ~scl_clean & scl_clean_d;
  wire start_cond = scl_clean & ~sda_clean & sda_clean_d;
  wire stop_cond = scl_clean & sda_clean & ~sda_clean_d;

  always @(posedge clk) begin
    if (!rst_n) begin
      scl_sync    <= 2'b11;
      sda_sync    <= 2'b11;
      scl_meta_d  <= 1'b1;
      sda_meta_d  <= 1'b1;
      scl_clean   <= 1'b1;
      sda_clean   <= 1'b1;
      scl_clean_d <= 1'b1;
      sda_clean_d <= 1'b1;
      addr_sync   <= 2'b00;
    end else begin
      scl_sync    <= {scl_sync[0], scl};
      sda_sync    <= {sda_sync[0], sda_in};
      addr_sync   <= {addr_sync[0], addr_select};
      scl_meta_d  <= scl_meta;
      sda_meta_d  <= sda_meta;
      scl_clean_d <= scl_clean;
      sda_clean_d <= sda_clean;
      if (scl_meta == scl_meta_d) begin
        scl_clean <= scl_meta;
      end
      if (sda_meta == sda_meta_d) begin
        sda_clean <= sda_meta;
      end
    end
  end

  reg [7:0] ram[0:15];
  integer ram_index;

  always @(posedge clk) begin
    if (!rst_n) begin
      for (ram_index = 0; ram_index < 16; ram_index = ram_index + 1) begin
        ram[ram_index] <= 8'h00;
      end
    end else if (write_en) begin
      ram[write_addr] <= write_data;
    end
  end

  reg [3:0] state;
  reg [2:0] bit_idx;
  reg [3:0] byte_idx;
  reg [7:0] shifter;
  reg [7:0] latched;
  reg       show_byte;
  reg       drive;
  reg       addr_cap;
  reg       read_match;
  reg       overread;

  wire [7:0] addr_window = {shifter[6:0], sda_clean};
  wire [7:0] read_byte = {6'b100001, addr_cap, 1'b1};
  wire [7:0] next_data = (overread || (byte_idx == 4'd15)) ? 8'hFF : ram[byte_idx + 4'd1];

  assign latched_byte = show_byte ? latched : 8'h00;
  assign sda_drive    = drive;

  always @(posedge clk) begin
    if (!rst_n) begin
      state      <= ST_IDLE;
      bit_idx    <= 3'd0;
      byte_idx   <= 4'd0;
      shifter    <= 8'h00;
      latched    <= 8'h00;
      show_byte  <= 1'b0;
      drive      <= 1'b0;
      addr_cap   <= 1'b0;
      read_match <= 1'b0;
      overread   <= 1'b0;
    end else if (start_cond) begin
      state      <= ST_ADDR;
      bit_idx    <= 3'd0;
      shifter    <= 8'h00;
      show_byte  <= 1'b0;
      latched    <= 8'h00;
      drive      <= 1'b0;
      addr_cap   <= addr_sync[1];
      read_match <= 1'b0;
      overread   <= 1'b0;
      byte_idx   <= 4'd0;
    end else if (stop_cond) begin
      state     <= ST_IDLE;
      drive     <= 1'b0;
      show_byte <= 1'b0;
      latched   <= 8'h00;
    end else begin
      case (state)
        ST_ADDR: begin
          if (scl_rise) begin
            if (bit_idx == 3'd7) begin
              read_match <= (addr_window == read_byte);
              state      <= ST_ADDR_ACK;
            end else begin
              shifter <= {shifter[6:0], sda_clean};
              bit_idx <= bit_idx + 3'd1;
            end
          end
        end
        ST_ADDR_ACK: begin
          if (scl_fall) begin
            if (read_match) begin
              drive <= 1'b1;
              state <= ST_ACK_HI;
            end else begin
              drive <= 1'b0;
              state <= ST_IDLE;
            end
          end
        end
        ST_ACK_HI: begin
          if (scl_rise) begin
            latched   <= ram[0];
            show_byte <= 1'b1;
            byte_idx  <= 4'd0;
            bit_idx   <= 3'd0;
            overread  <= 1'b0;
            state     <= ST_DATA_SETUP;
          end
        end
        ST_DATA_SETUP: begin
          if (scl_fall) begin
            drive   <= ~latched[7];
            bit_idx <= 3'd0;
            state   <= ST_DATA;
          end
        end
        ST_DATA: begin
          if (scl_rise && (bit_idx == 3'd7)) begin
            state <= ST_DATA_REL;
          end else if (scl_fall && (bit_idx != 3'd7)) begin
            bit_idx <= bit_idx + 3'd1;
            drive   <= ~latched[3'd7 - (bit_idx + 3'd1)];
          end
        end
        ST_DATA_REL: begin
          if (scl_fall) begin
            drive <= 1'b0;
            state <= ST_DATA_ACK;
          end
        end
        ST_DATA_ACK: begin
          if (scl_rise) begin
            if (sda_clean) begin
              drive     <= 1'b0;
              show_byte <= 1'b0;
              latched   <= 8'h00;
              state     <= ST_IDLE;
            end else begin
              latched   <= next_data;
              show_byte <= 1'b1;
              bit_idx   <= 3'd0;
              if (overread || (byte_idx == 4'd15)) begin
                overread <= 1'b1;
                byte_idx <= 4'd15;
              end else begin
                byte_idx <= byte_idx + 4'd1;
              end
              state <= ST_DATA_SETUP;
            end
          end
        end
        default: begin
          drive     <= 1'b0;
          show_byte <= 1'b0;
          state     <= ST_IDLE;
        end
      endcase
    end
  end

endmodule

`default_nettype wire
