"""Round-trip test: Python creates .dsl -> Rust parses -> verify."""
import io
import struct
import zipfile
import tempfile
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pylogic import DslReader


def create_minimal_dsl(samples_per_probe=256, probes=2, blocks=1):
    """Create a minimal .dsl file in memory and return bytes."""
    header_text = f"""total probes = {probes}
samplerate = 100 kHz
total samples = {samples_per_probe}
total blocks = {blocks}
probe0 = ch_a
probe1 = ch_b
"""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("header", header_text)

        for p in range(probes):
            for b in range(blocks):
                # Create predictable bit pattern: probe p, sample i
                # Use LFSR-like pattern for variety
                packed = bytearray()
                for byte_idx in range(samples_per_probe // 8):
                    byte_val = 0
                    for bit in range(8):
                        sample_idx = byte_idx * 8 + bit
                        # Simple pattern: (sample_idx + p) % 3 != 0 -> 1
                        if (sample_idx * 7 + p * 13) % 5 != 0:
                            byte_val |= (1 << bit)
                    packed.append(byte_val)

                name = f"L-{p}/{b}"
                zf.writestr(name, bytes(packed))

    return buf.getvalue()


def test_header_parsing():
    """Test that header metadata round-trips correctly."""
    dsl_bytes = create_minimal_dsl(samples_per_probe=256, probes=2)

    tmpfile = tempfile.NamedTemporaryFile(suffix='.dsl', delete=False)
    try:
        tmpfile.write(dsl_bytes)
        tmpfile.close()

        reader = DslReader.open(tmpfile.name)
        header = reader.get_header()

        assert header["total_probes"] == 2, f"total_probes: {header['total_probes']}"
        assert abs(header["samplerate"] - 100_000.0) < 1.0, f"samplerate: {header['samplerate']}"
        assert header["total_samples"] == 256, f"total_samples: {header['total_samples']}"
        assert header["total_blocks"] == 1, f"total_blocks: {header['total_blocks']}"
        assert list(header["probe_names"]) == ["ch_a", "ch_b"], f"probe_names: {header['probe_names']}"

        print("  PASS: header parsing")
    finally:
        os.unlink(tmpfile.name)


def test_channel_reading():
    """Test that channel data is read and unpacked correctly."""
    samples = 256
    dsl_bytes = create_minimal_dsl(samples_per_probe=samples, probes=2)

    tmpfile = tempfile.NamedTemporaryFile(suffix='.dsl', delete=False)
    try:
        tmpfile.write(dsl_bytes)
        tmpfile.close()

        reader = DslReader.open(tmpfile.name)

        for p in range(2):
            data = reader.read_channel(p)

            # data is a numpy array, verify length and types
            import numpy as np
            assert isinstance(data, np.ndarray), f"Expected numpy array, got {type(data)}"
            assert data.dtype == np.uint8, f"Expected uint8, got {data.dtype}"
            assert len(data) == samples, f"Expected {samples} samples, got {len(data)}"

            # All values should be 0 or 1
            assert np.all((data == 0) | (data == 1)), "Values not 0 or 1"

            # Verify specific samples against the pattern
            for i in range(samples):
                expected = 0 if (i * 7 + p * 13) % 5 == 0 else 1
                assert data[i] == expected, \
                    f"probe {p} sample {i}: expected {expected}, got {data[i]}"

        print("  PASS: channel reading")
    finally:
        os.unlink(tmpfile.name)


def test_channel_name_with_spaces():
    """Test header parsing with spaces in probe names."""
    header_text = """total probes = 3
samplerate = 25 MHz
total samples = 1000
total blocks = 5
probe0 = sync win
probe1 = sync pul
probe2 = tx
"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("header", header_text)
        # Add minimal block data
        for p in range(3):
            zf.writestr(f"L-{p}/0", b'\x00' * 125)

    tmpfile = tempfile.NamedTemporaryFile(suffix='.dsl', delete=False)
    try:
        tmpfile.write(buf.getvalue())
        tmpfile.close()

        reader = DslReader.open(tmpfile.name)
        header = reader.get_header()

        names = list(header["probe_names"])
        assert names[0] == "sync win", f"probe0: {names[0]}"
        assert names[1] == "sync pul", f"probe1: {names[1]}"
        assert names[2] == "tx", f"probe2: {names[2]}"

        print("  PASS: channel names with spaces")
    finally:
        os.unlink(tmpfile.name)


def test_error_on_missing_file():
    """Test that invalid file raises proper error."""
    try:
        DslReader.open("/nonexistent/path.dsl")
        assert False, "Should have raised"
    except OSError:
        print("  PASS: error on missing file")


if __name__ == "__main__":
    print("Running round-trip tests...")
    test_header_parsing()
    test_channel_reading()
    test_channel_name_with_spaces()
    test_error_on_missing_file()
    print("All tests passed!")
