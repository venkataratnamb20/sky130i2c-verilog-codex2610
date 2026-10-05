# SPDX-FileCopyrightText: © 2026 venkataratnamb20
# SPDX-License-Identifier: Apache-2.0
"""Pin-level cocotb checks for the 16-byte I2C RAM target.

The project clock is 20 ns (50 MHz). SCL is bit-banged on ``master_scl``.
SDA is an open-drain net in ``tb``: either side may pull it low. Expected
results come from the approved byte-stable contract, not from the RTL.
"""

import os

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, ReadOnly

CLK_PERIOD_NS = 20
HALF_1MHZ = 25
HALF_100KHZ = 250
ADDR_LOW = 0x42
ADDR_HIGH = 0x43


class ScoreboardError(AssertionError):
    """Raised when a pin-level observation disagrees with the contract."""


def _faulty_expected(expected, label):
    """Return a wrong expected value when the checker-fault switch is set.

    Args:
        expected: Value the contract requires.
        label: Observation name. Only the first data byte is corrupted.

    Returns:
        The expected value, or its bitwise inverse when
        ``INJECT_EXPECTATION_FAULT`` is ``1`` and ``label`` is ``byte0``.
    """
    if os.environ.get("INJECT_EXPECTATION_FAULT") == "1" and label == "byte0":
        return expected ^ 0xFF
    return expected


def _expect(actual, expected, label):
    """Compare one observation with the contract.

    Args:
        actual: Value sampled from the pins.
        expected: Value required by the contract.
        label: Short name included in the failure text.
    """
    expected = _faulty_expected(expected, label)
    if actual != expected:
        raise ScoreboardError(
            "%s: observed 0x%02x, contract 0x%02x" % (label, actual, expected)
        )


async def _sample(dut):
    """Sample slave SDA drive and the latched-byte output.

    Returns:
        Tuple of ``(bit, uo_out, oe)``. ``bit`` is 0 when the slave is
        pulling SDA low.
    """
    await ReadOnly()
    oe = int(dut.uio_oe.value)
    out = int(dut.uio_out.value)
    uo = int(dut.uo_out.value)
    if (out & 0x2) != 0:
        raise ScoreboardError("uio_out[1] must stay low, got 0x%02x" % out)
    if (oe & ~0x2) != 0:
        raise ScoreboardError("only SDA may be driven, oe=0x%02x" % oe)
    return (0 if (oe & 0x2) else 1), uo, oe


async def _write_bit(dut, half, bit):
    """Drive one master bit and check that the slave stays released.

    Args:
        dut: Cocotb DUT handle.
        half: SCL low and high time in project clocks.
        bit: Bit value, 0 or 1.
    """
    dut.master_scl.value = 0
    dut.master_sda_low.value = 0 if bit else 1
    await ClockCycles(dut.clk, half)
    dut.master_scl.value = 1
    await ClockCycles(dut.clk, 6)
    _bit, _uo, oe = await _sample(dut)
    if (oe & 0x2) != 0:
        raise ScoreboardError("slave drove SDA during a master bit")
    await ClockCycles(dut.clk, half - 6)


async def _read_bit(dut, half):
    """Release SDA, pulse SCL, and sample the slave bit.

    Args:
        dut: Cocotb DUT handle.
        half: SCL low and high time in project clocks.

    Returns:
        Tuple of ``(bit, uo_out)``.
    """
    dut.master_scl.value = 0
    dut.master_sda_low.value = 0
    await ClockCycles(dut.clk, half)
    dut.master_scl.value = 1
    await ClockCycles(dut.clk, 6)
    bit, uo, _oe = await _sample(dut)
    await ClockCycles(dut.clk, half - 6)
    return bit, uo


async def _send_byte(dut, half, value):
    """Send one byte, MSB first.

    Args:
        dut: Cocotb DUT handle.
        half: SCL phase length in project clocks.
        value: Byte to transmit.
    """
    for shift in range(7, -1, -1):
        await _write_bit(dut, half, (value >> shift) & 1)


async def _recv_byte(dut, half, during_first_low=None):
    """Receive one byte, MSB first.

    Args:
        dut: Cocotb DUT handle.
        half: SCL phase length in project clocks.
        during_first_low: Optional coroutine called while SCL is low on
            the first bit, after the slave has presented that bit.

    Returns:
        Tuple of ``(byte, uo_out sampled on the first bit)``.
    """
    value = 0
    first_uo = None
    for index in range(8):
        if index == 0 and during_first_low is not None:
            dut.master_scl.value = 0
            dut.master_sda_low.value = 0
            await ClockCycles(dut.clk, half)
            await during_first_low()
            dut.master_scl.value = 1
            await ClockCycles(dut.clk, 6)
            bit, first_uo, _oe = await _sample(dut)
            await ClockCycles(dut.clk, half - 6)
        else:
            bit, uo = await _read_bit(dut, half)
            if index == 0:
                first_uo = uo
        value = (value << 1) | bit
    return value, first_uo


async def _master_ack(dut, half, ack):
    """Drive the master ACK slot.

    Args:
        dut: Cocotb DUT handle.
        half: SCL phase length in project clocks.
        ack: True to ACK (SDA low), false to NACK.
    """
    await _write_bit(dut, half, 0 if ack else 1)


async def _start(dut):
    """Generate START from an idle high bus."""
    dut.master_scl.value = 1
    dut.master_sda_low.value = 0
    await ClockCycles(dut.clk, 20)
    dut.master_sda_low.value = 1
    await ClockCycles(dut.clk, 20)
    dut.master_scl.value = 0
    await ClockCycles(dut.clk, 20)


async def _repeated_start(dut):
    """Generate a repeated START while SCL is high and SDA is released."""
    dut.master_sda_low.value = 1
    await ClockCycles(dut.clk, 20)
    dut.master_scl.value = 0
    await ClockCycles(dut.clk, 20)


async def _stop(dut):
    """Generate STOP and wait until the target can see it."""
    dut.master_scl.value = 0
    dut.master_sda_low.value = 1
    await ClockCycles(dut.clk, 20)
    dut.master_scl.value = 1
    await ClockCycles(dut.clk, 20)
    dut.master_sda_low.value = 0
    await ClockCycles(dut.clk, 20)


async def _host_write(dut, addr, data):
    """Write one RAM byte on the project clock.

    Args:
        dut: Cocotb DUT handle.
        addr: RAM address, 0 through 15.
        data: Byte to store.
    """
    dut.ui_in.value = data
    dut.write_addr.value = addr
    dut.write_en.value = 1
    await ClockCycles(dut.clk, 2)
    dut.write_en.value = 0
    await ClockCycles(dut.clk, 1)


async def _fill(dut, values):
    """Write a 16-byte image.

    Args:
        dut: Cocotb DUT handle.
        values: Sequence of 16 byte values.
    """
    for addr, data in enumerate(values):
        await _host_write(dut, addr, data)


async def _boot(dut, strap):
    """Start the clock, reset, and choose the address strap.

    Args:
        dut: Cocotb DUT handle.
        strap: 0 for 7-bit address 0x42, 1 for 0x43.
    """
    clock = Clock(dut.clk, CLK_PERIOD_NS, units="ns")
    cocotb.start_soon(clock.start())
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.master_scl.value = 1
    dut.master_sda_low.value = 0
    dut.addr_select.value = strap
    dut.write_en.value = 0
    dut.write_addr.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 8)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 8)


async def _address(dut, half, addr, read):
    """Send a 7-bit address and return the target ACK bit.

    Args:
        dut: Cocotb DUT handle.
        half: SCL phase length in project clocks.
        addr: 7-bit target address.
        read: True for a read, false for a write.

    Returns:
        0 when the target ACKs, 1 when it leaves SDA released.
    """
    await _send_byte(dut, half, ((addr & 0x7F) << 1) | (1 if read else 0))
    ack, _uo = await _read_bit(dut, half)
    return ack


async def _read_block(dut, half, addr, count, extra=0, during_first_low=None):
    """Read ``count`` bytes, then ``extra`` overread bytes.

    The last byte of the whole transfer is NACKed. Earlier bytes are ACKed.

    Args:
        dut: Cocotb DUT handle.
        half: SCL phase length in project clocks.
        addr: 7-bit target address.
        count: Number of RAM bytes to read.
        extra: Additional bytes expected to be released as 0xFF.
        during_first_low: Optional hook passed to the first data byte.

    Returns:
        Tuple of ``(data bytes, uo_out on the first data bit)``.
    """
    await _start(dut)
    ack = await _address(dut, half, addr, True)
    _expect(ack, 0, "address-ack")
    data = []
    first_uo = None
    total = count + extra
    for index in range(total):
        hook = during_first_low if index == 0 else None
        value, uo = await _recv_byte(dut, half, hook)
        if index == 0:
            first_uo = uo
        data.append(value)
        await _master_ack(dut, half, index != total - 1)
    await _stop(dut)
    return data, first_uo


@cocotb.test(timeout_time=100, timeout_unit="ms")
async def test_both_straps_and_full_read(dut):
    """Read a distinct 16-byte image from 0x42 and from 0x43."""
    image = [(0x10 + index) & 0xFF for index in range(16)]
    await _boot(dut, 0)
    await _fill(dut, image)
    data, first_uo = await _read_block(dut, HALF_1MHZ, ADDR_LOW, 16)
    _expect(first_uo, image[0], "uo-byte0")
    for index, value in enumerate(data):
        _expect(value, image[index], "byte%d" % index)
    await ReadOnly()
    idle_uo = int(dut.uo_out.value)
    await ClockCycles(dut.clk, 1)
    _expect(idle_uo, 0, "uo-idle")

    ack = await _start_and_address(dut, ADDR_HIGH)
    _expect(ack, 1, "unselected-ack")
    await _stop(dut)

    dut.addr_select.value = 1
    await ClockCycles(dut.clk, 8)
    data, _uo = await _read_block(dut, HALF_1MHZ, ADDR_HIGH, 16)
    for index, value in enumerate(data):
        _expect(value, image[index], "high-byte%d" % index)
    await _start(dut)
    ack = await _address(dut, HALF_1MHZ, ADDR_LOW, True)
    _expect(ack, 1, "old-strap-ack")
    await _stop(dut)


async def _start_and_address(dut, addr):
    """START and send a read address.

    Args:
        dut: Cocotb DUT handle.
        addr: 7-bit address.

    Returns:
        The ACK bit.
    """
    await _start(dut)
    return await _address(dut, HALF_1MHZ, addr, True)


@cocotb.test(timeout_time=50, timeout_unit="ms")
async def test_reject_write_and_wrong_address(dut):
    """NACK a matching write and a non-matching read, then read byte 0."""
    await _boot(dut, 0)
    await _host_write(dut, 0, 0x5A)
    await _start(dut)
    ack = await _address(dut, HALF_1MHZ, ADDR_LOW, False)
    _expect(ack, 1, "write-ack")
    await _stop(dut)
    await _start(dut)
    ack = await _address(dut, HALF_1MHZ, 0x10, True)
    _expect(ack, 1, "wrong-ack")
    await _stop(dut)
    data, _uo = await _read_block(dut, HALF_1MHZ, ADDR_LOW, 1)
    _expect(data[0], 0x5A, "byte0")


@cocotb.test(timeout_time=100, timeout_unit="ms")
async def test_constant_patterns(dut):
    """Read solid 0x00, 0xFF, 0xAA, and 0x55 images."""
    await _boot(dut, 0)
    for pattern in (0x00, 0xFF, 0xAA, 0x55):
        await _fill(dut, [pattern] * 16)
        data, _uo = await _read_block(dut, HALF_1MHZ, ADDR_LOW, 16)
        for index, value in enumerate(data):
            _expect(value, pattern, "pattern-%02x-%d" % (pattern, index))


@cocotb.test(timeout_time=50, timeout_unit="ms")
async def test_early_nack_restarts_at_zero(dut):
    """NACK after byte 0 and after byte 7; the next read starts at byte 0."""
    image = list(range(16))
    await _boot(dut, 0)
    await _fill(dut, image)
    for count in (1, 8):
        data, _uo = await _read_block(dut, HALF_1MHZ, ADDR_LOW, count)
        for index, value in enumerate(data):
            _expect(value, image[index], "early-%d-%d" % (count, index))
        again, _uo = await _read_block(dut, HALF_1MHZ, ADDR_LOW, 1)
        _expect(again[0], image[0], "restart-byte0")


@cocotb.test(timeout_time=50, timeout_unit="ms")
async def test_repeated_start_restarts_at_zero(dut):
    """A repeated START after a one-byte NACK reads byte 0 again."""
    await _boot(dut, 0)
    await _fill(dut, [0xA0 + index for index in range(16)])
    await _start(dut)
    ack = await _address(dut, HALF_1MHZ, ADDR_LOW, True)
    _expect(ack, 0, "address-ack")
    first, _uo = await _recv_byte(dut, HALF_1MHZ)
    _expect(first, 0xA0, "byte0")
    await _master_ack(dut, HALF_1MHZ, False)
    await _repeated_start(dut)
    ack = await _address(dut, HALF_1MHZ, ADDR_LOW, True)
    _expect(ack, 0, "restart-ack")
    second, _uo = await _recv_byte(dut, HALF_1MHZ)
    _expect(second, 0xA0, "byte0-again")
    await _master_ack(dut, HALF_1MHZ, False)
    await _stop(dut)


@cocotb.test(timeout_time=50, timeout_unit="ms")
async def test_overread_returns_ff(dut):
    """ACK past byte 15 and expect the next byte to read 0xFF."""
    image = [0xC0 + index for index in range(16)]
    await _boot(dut, 0)
    await _fill(dut, image)
    data, _uo = await _read_block(dut, HALF_1MHZ, ADDR_LOW, 16, extra=1)
    for index in range(16):
        _expect(data[index], image[index], "byte%d" % index)
    _expect(data[16], 0xFF, "overread")


@cocotb.test(timeout_time=50, timeout_unit="ms")
async def test_reset_during_transfer(dut):
    """Reset mid-byte releases SDA, then a new read starts at byte 0."""
    await _boot(dut, 0)
    await _fill(dut, [0x3C] + [0x00] * 15)
    await _start(dut)
    ack = await _address(dut, HALF_1MHZ, ADDR_LOW, True)
    _expect(ack, 0, "address-ack")
    dut.master_scl.value = 0
    dut.master_sda_low.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 4)
    await ReadOnly()
    oe_in_reset = int(dut.uio_oe.value) & 0x2
    uo_in_reset = int(dut.uo_out.value)
    await ClockCycles(dut.clk, 1)
    _expect(oe_in_reset, 0, "oe-in-reset")
    _expect(uo_in_reset, 0, "uo-in-reset")
    dut.rst_n.value = 1
    dut.master_scl.value = 1
    dut.master_sda_low.value = 0
    await ClockCycles(dut.clk, 20)
    await _fill(dut, [0x3C] + [0x00] * 15)
    data, _uo = await _read_block(dut, HALF_1MHZ, ADDR_LOW, 1)
    _expect(data[0], 0x3C, "byte0")


@cocotb.test(timeout_time=50, timeout_unit="ms")
async def test_latched_byte_ignores_later_write(dut):
    """A write after the byte is latched does not change that transfer."""
    await _boot(dut, 0)
    await _fill(dut, [0xA5, 0x11] + [0x00] * 14)

    async def overwrite():
        await _host_write(dut, 0, 0x5A)

    data, first_uo = await _read_block(
        dut, HALF_1MHZ, ADDR_LOW, 2, during_first_low=overwrite
    )
    _expect(data[0], 0xA5, "byte0")
    _expect(data[1], 0x11, "byte1")
    _expect(first_uo, 0xA5, "uo-byte0")
    again, _uo = await _read_block(dut, HALF_1MHZ, ADDR_LOW, 1)
    _expect(again[0], 0x5A, "byte0-next")


@cocotb.test(timeout_time=200, timeout_unit="ms")
async def test_full_read_at_100khz(dut):
    """Read all 16 bytes with a 100 kHz SCL and a 20 ns project clock."""
    image = [0x80 + index for index in range(16)]
    await _boot(dut, 0)
    await _fill(dut, image)
    data, _uo = await _read_block(dut, HALF_100KHZ, ADDR_LOW, 16)
    for index, value in enumerate(data):
        _expect(value, image[index], "slow-byte%d" % index)
