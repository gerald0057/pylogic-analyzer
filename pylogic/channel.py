import math

import numpy as np

from .cursors import Cursors


class Channel:
    """A single digital channel (or derived virtual channel).

    Wraps a numpy uint8 array where each element is 0 or 1.
    Supports edge detection, pulse analysis, pattern matching,
    and bitwise operators for creating virtual channels.

    All time-based methods convert seconds to sample counts using
    the parent waveform's sample rate.
    """

    def __init__(self, data: np.ndarray, waveform, *,
                 name: str = "", probe_index: int | None = None):
        self._data = data  # uint8, 0 or 1 per sample
        self._waveform = waveform
        self._name = name
        self._probe_index = probe_index

    @property
    def name(self) -> str:
        return self._name

    @property
    def data(self) -> np.ndarray:
        """Raw sample data (uint8 array, 0 or 1)."""
        return self._data

    @property
    def sample_rate(self) -> float:
        return self._waveform.sample_rate

    @property
    def times(self) -> np.ndarray:
        """Array of absolute times for each sample."""
        return np.arange(len(self._data), dtype=np.float64) / self.sample_rate

    def _time_to_samples(self, seconds: float) -> int:
        return max(1, math.ceil(seconds * self.sample_rate))

    # ---- Edge detection ----

    def rising_edges(self) -> Cursors:
        """Find all 0->1 transitions. Returns Cursors at the rising sample."""
        diff = np.diff(self._data.astype(np.int8))
        idx = np.where(diff == 1)[0] + 1
        return Cursors.from_indices(idx, self._waveform)

    def falling_edges(self) -> Cursors:
        """Find all 1->0 transitions. Returns Cursors at the falling sample."""
        diff = np.diff(self._data.astype(np.int8))
        idx = np.where(diff == -1)[0] + 1
        return Cursors.from_indices(idx, self._waveform)

    def edges(self) -> Cursors:
        """Find all transitions (rising or falling)."""
        diff = np.diff(self._data.astype(np.int8))
        idx = np.where(diff != 0)[0] + 1
        return Cursors.from_indices(idx, self._waveform)

    # ---- Pulse analysis ----

    def _high_pulse_rising_edges(self, min_width_samples: int) -> np.ndarray:
        """Find rising edges that start a high pulse of at least min_width_samples."""
        diff = np.diff(self._data.astype(np.int8))
        rise_idx = np.where(diff == 1)[0] + 1
        fall_idx = np.where(diff == -1)[0] + 1

        if len(rise_idx) == 0:
            return np.array([], dtype=np.int64)

        # Handle signal starting high
        if self._data[0] == 1:
            rise_idx = np.concatenate(([0], rise_idx))

        result = []
        for r in rise_idx:
            ni = np.searchsorted(fall_idx, r)
            if ni >= len(fall_idx):
                # Open high period: use end of data
                f = len(self._data)
            else:
                f = fall_idx[ni]
            if f - r >= min_width_samples:
                result.append(r)

        return np.array(result, dtype=np.int64)

    def pulses_wider_than(self, seconds: float) -> Cursors:
        """Cursors at rising edges of high pulses wider than `seconds`."""
        min_samples = self._time_to_samples(seconds)
        idx = self._high_pulse_rising_edges(min_samples)
        return Cursors.from_indices(idx, self._waveform)

    def pulses_narrower_than(self, seconds: float) -> Cursors:
        """Cursors at rising edges of high pulses narrower than `seconds`.

        Only considers complete pulses (has a falling edge).
        """
        min_samples = self._time_to_samples(seconds)
        diff = np.diff(self._data.astype(np.int8))
        rise_idx = np.where(diff == 1)[0] + 1
        fall_idx = np.where(diff == -1)[0] + 1

        if len(rise_idx) == 0:
            return Cursors.from_indices(np.array([], dtype=np.int64), self._waveform)

        if self._data[0] == 1:
            rise_idx = np.concatenate(([0], rise_idx))

        result = []
        for r in rise_idx:
            ni = np.searchsorted(fall_idx, r)
            if ni >= len(fall_idx):
                continue  # Skip open period
            f = fall_idx[ni]
            if f - r < min_samples:
                result.append(r)

        return Cursors.from_indices(np.array(result, dtype=np.int64), self._waveform)

    def pulse_widths(self) -> Cursors:
        """Cursors at rising edges with duration metadata."""
        diff = np.diff(self._data.astype(np.int8))
        rise_idx = np.where(diff == 1)[0] + 1
        fall_idx = np.where(diff == -1)[0] + 1

        if len(rise_idx) == 0:
            return Cursors.from_indices(np.array([], dtype=np.int64), self._waveform)

        if self._data[0] == 1:
            rise_idx = np.concatenate(([0], rise_idx))

        dt = 1.0 / self.sample_rate
        widths = []
        for r in rise_idx:
            ni = np.searchsorted(fall_idx, r)
            if ni >= len(fall_idx):
                widths.append((len(self._data) - r) * dt)
            else:
                widths.append((fall_idx[ni] - r) * dt)

        return Cursors.from_indices(rise_idx, self._waveform,
                                    extra={"pulse_widths": np.array(widths)})

    # ---- Pattern matching ----

    def pattern(self, bits: list[int]) -> Cursors:
        """Find occurrences of a specific bit pattern.

        Uses convolution to match the pattern against the signal.
        Returns cursors at the start of each match.
        """
        if not bits:
            return Cursors.from_indices(np.array([], dtype=np.int64), self._waveform)

        pattern = np.array(bits, dtype=np.int8)
        n = len(pattern)
        if n > len(self._data):
            return Cursors.from_indices(np.array([], dtype=np.int64), self._waveform)

        # Convert data to int8 for comparison
        data_int = self._data.astype(np.int8)

        # Sliding window: match positions where data[i:i+n] == pattern
        matches = []
        for i in range(len(data_int) - n + 1):
            if np.array_equal(data_int[i:i + n], pattern):
                matches.append(i)

        return Cursors.from_indices(np.array(matches, dtype=np.int64), self._waveform)

    def alternating_with(self, other: "Channel") -> Cursors:
        """Find segments where self and other are complementary (XOR=1).

        Returns cursors at the start of each XOR=1 segment.
        If XOR starts at 1, index 0 is included.
        """
        xor_data = self._data ^ other._data
        vch = Channel(xor_data, self._waveform, name=f"({self._name} ^ {other._name})")
        edges = vch.rising_edges()
        if xor_data[0] == 1:
            indices = np.concatenate(([0], edges.indices))
            return Cursors.from_indices(indices, self._waveform)
        return edges

    # ---- Bitwise operators (virtual channels) ----

    def _check_same_waveform(self, other: "Channel") -> None:
        if self._data.shape != other._data.shape:
            raise ValueError(
                f"Channel shape mismatch: {self._data.shape} vs {other._data.shape}"
            )

    def __and__(self, other: "Channel") -> "Channel":
        self._check_same_waveform(other)
        return Channel(self._data & other._data, self._waveform,
                       name=f"({self._name} & {other._name})")

    def __or__(self, other: "Channel") -> "Channel":
        self._check_same_waveform(other)
        return Channel(self._data | other._data, self._waveform,
                       name=f"({self._name} | {other._name})")

    def __xor__(self, other: "Channel") -> "Channel":
        self._check_same_waveform(other)
        return Channel(self._data ^ other._data, self._waveform,
                       name=f"({self._name} ^ {other._name})")

    def __invert__(self) -> "Channel":
        return Channel(1 - self._data, self._waveform,
                       name=f"~({self._name})")

    def __repr__(self) -> str:
        return f"Channel('{self._name}', samples={len(self._data)})"
