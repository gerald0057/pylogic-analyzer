"""Integration test for the Python DSL layer.

Creates a synthetic .dsl file with known signal patterns,
then tests the full DSL API: Channel, Cursors, bitwise ops, measurements.
"""
import io
import os
import struct
import sys
import tempfile
import zipfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pylogic import Waveform, Channel, Cursors


def _make_bit_packed(samples):
    """Convert a list of 0/1 samples to bit-packed bytes."""
    pad = (8 - len(samples) % 8) % 8
    padded = list(samples) + [0] * pad
    packed = bytearray()
    for i in range(0, len(padded), 8):
        b = 0
        for j in range(8):
            b |= (padded[i + j] << j)
        packed.append(b)
    return bytes(packed)


def _create_dsl(probe_data, sample_rate=100_000.0):
    """Create a .dsl file with given probe data.

    probe_data: dict[name -> list of 0/1 samples]
    """
    probes = list(probe_data.keys())
    n_probes = len(probes)
    n_samples = max(len(v) for v in probe_data.values())

    header = f"[version]\nversion = 3\n[header]\ndriver = DSLogic\ndevice mode = 0\ncapturefile = data\ntotal samples = {n_samples}\ntotal probes = {n_probes}\nsamplerate = {sample_rate} Hz\ntotal blocks = 1\ntrigger time = 0\ntrigger pos = 0\n"
    for i, name in enumerate(probes):
        header += f"probe{i} = {name}\n"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("header", header)
        for i, name in enumerate(probes):
            data = probe_data[name]
            if len(data) < n_samples:
                data = list(data) + [0] * (n_samples - len(data))
            packed = _make_bit_packed(data)
            zf.writestr(f"L-{i}/0", packed)

    tmpfile = tempfile.NamedTemporaryFile(suffix='.dsl', delete=False)
    tmpfile.write(buf.getvalue())
    tmpfile.close()
    return tmpfile.name


def test_rising_edges():
    """Test edge detection on a known pattern."""
    # Signal: 0 0 0 1 1 1 1 0 0 0 1 1 1 1 1 0
    signal = [0,0,0,1,1,1,1,0,0,0,1,1,1,1,1,0]
    path = _create_dsl({"tx": signal}, sample_rate=10.0)  # 10 Hz for easy time calc

    try:
        wf = Waveform(path)
        edges = wf.channel("tx").rising_edges()

        assert edges.count == 2, f"Expected 2 rising edges, got {edges.count}"
        assert edges.indices[0] == 3, f"First edge at 3, got {edges.indices[0]}"
        assert edges.indices[1] == 10, f"Second edge at 10, got {edges.indices[1]}"
        print("  PASS: rising_edges")
    finally:
        os.unlink(path)


def test_falling_edges():
    """Test falling edge detection."""
    signal = [0,0,0,1,1,1,1,0,0,0,1,1,1,1,1,0]
    path = _create_dsl({"tx": signal})

    try:
        wf = Waveform(path)
        edges = wf.channel("tx").falling_edges()

        assert edges.count == 2
        assert edges.indices[0] == 7, f"First fall at 7, got {edges.indices[0]}"
        assert edges.indices[1] == 15, f"Second fall at 15, got {edges.indices[1]}"
        print("  PASS: falling_edges")
    finally:
        os.unlink(path)


def test_pulses_wider_than():
    """Test pulse width thresholding."""
    # 10 Hz sample rate
    # Pulse 1: samples 3-7 = 4 samples = 0.4s
    # Pulse 2: samples 10-15 = 5 samples = 0.5s
    signal = [0,0,0,1,1,1,1,0,0,0,1,1,1,1,1,0]
    path = _create_dsl({"tx": signal}, sample_rate=10.0)

    try:
        wf = Waveform(path)
        # Threshold 0.3s = 3 samples
        wide = wf.channel("tx").pulses_wider_than(0.3)
        assert wide.count == 2, f"Expected 2 pulses >= 0.3s, got {wide.count}"

        # Threshold 0.45s = 4.5 samples
        very_wide = wf.channel("tx").pulses_wider_than(0.45)
        assert very_wide.count == 1, f"Expected 1 pulse >= 0.45s, got {very_wide.count}"
        print("  PASS: pulses_wider_than")
    finally:
        os.unlink(path)


def test_bitwise_operators():
    """Test channel & | ^ ~ operators for virtual channels."""
    ch0 = [1, 1, 0, 0, 1, 1, 0, 0]
    ch1 = [1, 0, 1, 0, 1, 0, 1, 0]
    path = _create_dsl({"a": ch0, "b": ch1})

    try:
        wf = Waveform(path)
        a = wf.channel("a")
        b = wf.channel("b")

        and_data = (a & b).data
        assert list(and_data) == [1, 0, 0, 0, 1, 0, 0, 0], f"AND: {list(and_data)}"

        or_data = (a | b).data
        assert list(or_data) == [1, 1, 1, 0, 1, 1, 1, 0], f"OR: {list(or_data)}"

        xor_data = (a ^ b).data
        assert list(xor_data) == [0, 1, 1, 0, 0, 1, 1, 0], f"XOR: {list(xor_data)}"

        not_data = (~a).data
        assert list(not_data) == [0, 0, 1, 1, 0, 0, 1, 1], f"NOT: {list(not_data)}"

        print("  PASS: bitwise operators")
    finally:
        os.unlink(path)


def test_alternating_with():
    """Test alternating pattern detection via XOR."""
    ch0 = [1, 0, 1, 0, 1, 0, 1, 0]  # alternating
    ch1 = [0, 1, 0, 1, 0, 1, 0, 1]  # complementary
    path = _create_dsl({"a": ch0, "b": ch1})

    try:
        wf = Waveform(path)
        alt = wf.channel("a").alternating_with(wf.channel("b"))
        # XOR is all 1s, so rising edges at the first edge of XOR
        # Since XOR starts at 1, rising edge at 0
        assert alt.count > 0, f"Expected alternation detected, got {alt.count}"
        print("  PASS: alternating_with")
    finally:
        os.unlink(path)


def test_intervals_from():
    """Test measurement between two cursor sets (replaces edge_to_edge)."""
    # Signal A: rising at 0.3s, 0.5s
    # Signal B: rising at 0.4s, 0.6s
    # Expected deltas: 0.1s, 0.1s
    n = 100
    rate = 100.0
    a_sig = [0] * n
    b_sig = [0] * n
    a_sig[30] = 1  # 0.3s
    a_sig[50] = 1  # 0.5s
    b_sig[40] = 1  # 0.4s
    b_sig[60] = 1  # 0.6s
    # Fill remaining to 1 so edges work right
    for i in range(30, 100):
        a_sig[i] = 1
    for i in range(40, 100):
        b_sig[i] = 1

    # Actually let me use cleaner patterns with single edges
    a_sig = [0] * 100
    b_sig = [0] * 100
    a_sig[30] = 1  # 0.3s: rising at 30
    b_sig[40] = 1  # 0.4s: rising at 40

    path = _create_dsl({"A": a_sig, "B": b_sig}, sample_rate=100.0)
    try:
        wf = Waveform(path)
        a_edges = wf.channel("A").rising_edges()
        b_edges = wf.channel("B").rising_edges()

        deltas = a_edges.intervals_from(b_edges)
        assert len(deltas) == 1, f"Expected 1 delta, got {len(deltas)}"
        assert abs(deltas[0] - 0.1) < 0.001, f"Expected 0.1s, got {deltas[0]}"
        print("  PASS: intervals_from")
    finally:
        os.unlink(path)


def test_stats():
    """Test statistics computation."""
    signal = [0,1,1,1,0,0,1,1,0]
    path = _create_dsl({"tx": signal}, sample_rate=10.0)

    try:
        wf = Waveform(path)
        cursors = wf.channel("tx").pulse_widths()
        stats = cursors.stats()

        assert stats["count"] == 2
        assert stats["min"] is not None
        print("  PASS: stats")
    finally:
        os.unlink(path)


def test_channel_not_found():
    """Test error on unknown channel name."""
    path = _create_dsl({"a": [0, 1, 0]})
    try:
        wf = Waveform(path)
        try:
            wf.channel("nonexistent")
            assert False, "Should have raised"
        except Exception as e:
            assert "nonexistent" in str(e)
        print("  PASS: channel not found")
    finally:
        os.unlink(path)


if __name__ == "__main__":
    print("Running DSL integration tests...")
    test_rising_edges()
    test_falling_edges()
    test_pulses_wider_than()
    test_bitwise_operators()
    test_alternating_with()
    test_intervals_from()
    test_stats()
    test_channel_not_found()
    print("All DSL tests passed!")
