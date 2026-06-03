"""End-to-end export test: create .dsl -> analyze -> export -> re-read."""
import io
import os
import sys
import tempfile
import zipfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pylogic import Waveform


def _make_bit_packed(samples):
    """Convert list of 0/1 values to bit-packed bytes."""
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
    """Create a minimal .dsl file."""
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


def test_export_with_cursors():
    """Full round-trip: load -> analyze -> export -> re-load -> verify."""
    # Signal with 2 rising edges: at index 3 and 10
    signal = [0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 1, 1, 1, 1, 1, 0]
    src_path = _create_dsl({"tx": signal}, sample_rate=100_000.0)

    try:
        # Step 1: Load and analyze
        wf = Waveform(src_path)
        edges = wf.channel("tx").rising_edges()
        assert edges.count == 2, f"Expected 2 edges, got {edges.count}"

        # Step 2: Export with cursor annotation
        out_path = tempfile.mktemp(suffix='.dsl')
        wf.export(out_path).add_cursors(edges.cursor("TX_E")).write()

        # Step 3: Verify the exported file is a valid ZIP
        with zipfile.ZipFile(out_path) as zf:
            names = zf.namelist()
            assert "header" in names, "Missing header in output"
            assert "L-0/0" in names, "Missing original data in output"
            assert "L-1/0" in names, "Missing cursor channel in output"

        # Step 4: Re-load exported file
        wf2 = Waveform(out_path)
        h = wf2._reader.get_header()
        assert h["total_probes"] == 2, f"Expected 2 probes, got {h['total_probes']}"
        assert list(h["probe_names"])[:2] == ["tx", "TX_E"], \
            f"probe_names: {h['probe_names']}"

        # Step 5: Verify original data is intact
        tx_data = wf2.channel("tx").data
        assert list(tx_data) == signal, f"Original data corrupted: {list(tx_data)}"

        # Step 6: Verify cursor channel has 1s at edge positions
        cursor_data = wf2.channel("TX_E").data
        # cursor positions: index 3 and 10 (widened to 3-5 and 10-12)
        assert cursor_data[3] == 1, f"No cursor at index 3: {cursor_data}"
        assert cursor_data[10] == 1, f"No cursor at index 10: {cursor_data}"

        # Non-edge positions should be 0
        assert cursor_data[0] == 0

        print("  PASS: export with cursors")
    finally:
        os.unlink(src_path)
        if 'out_path' in dir() and os.path.exists(out_path):
            os.unlink(out_path)


def test_export_no_cursors():
    """Test export without any cursor annotations (pass-through)."""
    signal = [0, 1, 0, 1, 0]
    src_path = _create_dsl({"tx": signal})

    try:
        wf = Waveform(src_path)
        out_path = tempfile.mktemp(suffix='.dsl')
        wf.export(out_path).write()

        # Verify output is valid and preserves data
        wf2 = Waveform(out_path)
        assert list(wf2.channel("tx").data) == signal
        print("  PASS: export no cursors")
    finally:
        os.unlink(src_path)
        if 'out_path' in dir() and os.path.exists(out_path):
            os.unlink(out_path)


def test_export_multiple_cursors():
    """Test exporting multiple cursor channels."""
    signal = [0, 0, 1, 1, 0, 0, 1, 1]
    src_path = _create_dsl({"ch0": signal}, sample_rate=100_000.0)

    try:
        wf = Waveform(src_path)
        rises = wf.channel("ch0").rising_edges().cursor("RISE")
        falls = wf.channel("ch0").falling_edges().cursor("FALL")

        out_path = tempfile.mktemp(suffix='.dsl')
        wf.export(out_path) \
            .add_cursors(rises) \
            .add_cursors(falls) \
            .write()

        wf2 = Waveform(out_path)
        h = wf2._reader.get_header()
        assert h["total_probes"] == 3  # original + RISE + FALL
        assert list(h["probe_names"])[:3] == ["ch0", "RISE", "FALL"]
        print("  PASS: export multiple cursors")
    finally:
        os.unlink(src_path)
        if 'out_path' in dir() and os.path.exists(out_path):
            os.unlink(out_path)


if __name__ == "__main__":
    print("Running export tests...")
    test_export_with_cursors()
    test_export_no_cursors()
    test_export_multiple_cursors()
    print("All export tests passed!")
