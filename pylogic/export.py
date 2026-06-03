"""DSL export with cursor annotation channels.

Encodes cursor positions as bit-packed virtual probe channels
and writes them into a new .dsl file alongside the original data.
"""
import numpy as np

from ._native import DslWriter


class DslExport:
    """Builder for exporting waveform + cursor annotations as .dsl.

    Usage:
        wf = Waveform("capture.dsl")
        edges = wf.channel("tx").rising_edges().cursor("TX_E")

        wf.export("output.dsl")
            .add_cursors(edges)
            .write()

    Each cursor set becomes a virtual probe in the output .dsl
    with a 1 at cursor positions and 0 elsewhere. These appear
    as visible annotation channels when opened in DSView.
    """

    def __init__(self, waveform, output_path: str):
        self._waveform = waveform
        self._output_path = output_path
        self._channels: list[tuple[np.ndarray, str]] = []

    def add_cursors(self, cursors, *, label: str | None = None) -> "DslExport":
        """Add a cursor set as an annotation channel.

        Args:
            cursors: A Cursors object with sample indices.
            label: Channel name for the output .dsl.
                   Falls back to cursors.label if set.
        """
        name = label or cursors.label or f"_cursor_{len(self._channels)}"

        # Encode as a signal: 1 at cursor positions, 0 elsewhere
        n_samples = self._waveform.total_samples
        signal = np.zeros(n_samples, dtype=np.uint8)

        indices = cursors.indices
        valid = indices[(indices >= 0) & (indices < n_samples)]
        signal[valid] = 1

        # Optionally widen the pulse for visibility (3-sample wide)
        # Shift right by 1 and 2, OR together
        signal_widened = signal.copy()
        if len(valid) > 0:
            shifted1 = np.zeros_like(signal)
            shifted2 = np.zeros_like(signal)
            shifted1[1:] = signal[:-1]
            shifted2[2:] = signal[:-2]
            signal_widened = signal | shifted1 | shifted2

        self._channels.append((signal_widened, name))
        return self

    def write(self) -> None:
        """Write the output .dsl file.

        Copies all original data and adds cursor annotation channels.
        """
        if not self._channels:
            # No cursors to add, but still write a valid .dsl
            DslWriter.write(self._waveform.path, self._output_path, [])
            return

        # Prepare extra_channels as list of (name, numpy_array) tuples
        # Pad signal length to multiple of 8 for bit-packing
        extra = []
        for signal, name in self._channels:
            # Ensure signal length is multiple of 8
            pad_len = (8 - len(signal) % 8) % 8
            if pad_len > 0:
                padded = np.pad(signal, (0, pad_len), 'constant', constant_values=0)
            else:
                padded = signal
            extra.append((name, padded))

        DslWriter.write(self._waveform.path, self._output_path, extra)
