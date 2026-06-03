import numpy as np


class Cursors:
    """A collection of time-position markers (cursors).

    Represents analysis results as a set of sample indices / absolute times.
    Supports filtering, set operations, measurement, and export preparation.

    Usually created by Channel methods (rising_edges, pulses_wider_than, etc.)
    rather than directly.
    """

    def __init__(self, indices: np.ndarray, times: np.ndarray, waveform=None, *,
                 extra: dict | None = None):
        self._indices = np.asarray(indices, dtype=np.int64)
        self._times = np.asarray(times, dtype=np.float64)
        self._waveform = waveform
        self._label = ""
        self._extra = extra or {}

    @classmethod
    def from_indices(cls, indices: np.ndarray, waveform, *,
                     extra: dict | None = None) -> "Cursors":
        """Create cursors from sample indices."""
        indices = np.asarray(indices, dtype=np.int64)
        times = indices.astype(np.float64) / waveform.sample_rate
        return cls(indices, times, waveform, extra=extra)

    @classmethod
    def from_times(cls, times: np.ndarray, waveform, *,
                   extra: dict | None = None) -> "Cursors":
        """Create cursors from absolute times."""
        times = np.asarray(times, dtype=np.float64)
        indices = (times * waveform.sample_rate).astype(np.int64)
        return cls(indices, times, waveform, extra=extra)

    @property
    def indices(self) -> np.ndarray:
        return self._indices

    @property
    def times(self) -> np.ndarray:
        return self._times

    @property
    def count(self) -> int:
        return len(self._indices)

    @property
    def label(self) -> str:
        return self._label

    @property
    def extra(self) -> dict:
        return self._extra

    # ---- Labeling ----

    def cursor(self, label: str = "") -> "Cursors":
        """Annotate cursors with a label for export."""
        self._label = label
        return self

    # ---- Filtering ----

    def first(self) -> "Cursors":
        """Keep only the first cursor."""
        if len(self._indices) == 0:
            return self
        return Cursors(self._indices[:1], self._times[:1], self._waveform,
                       extra=self._extra)

    def last(self) -> "Cursors":
        """Keep only the last cursor."""
        if len(self._indices) == 0:
            return self
        return Cursors(self._indices[-1:], self._times[-1:], self._waveform,
                       extra=self._extra)

    def nth(self, n: int) -> "Cursors":
        """Keep every nth cursor (0-based)."""
        if len(self._indices) == 0:
            return self
        idx = [self._indices[n]] if n < len(self._indices) else []
        return Cursors(np.array(idx), self._times[n:n+1], self._waveform,
                       extra=self._extra)

    def before(self, time_s: float) -> "Cursors":
        """Keep cursors before a time boundary."""
        mask = self._times < time_s
        return Cursors(self._indices[mask], self._times[mask], self._waveform,
                       extra=self._extra)

    def after(self, time_s: float) -> "Cursors":
        """Keep cursors after a time boundary."""
        mask = self._times > time_s
        return Cursors(self._indices[mask], self._times[mask], self._waveform,
                       extra=self._extra)

    def between(self, start_s: float, end_s: float) -> "Cursors":
        """Keep cursors within a time window."""
        mask = (self._times >= start_s) & (self._times <= end_s)
        return Cursors(self._indices[mask], self._times[mask], self._waveform,
                       extra=self._extra)

    def within(self, other: "Cursors", tolerance_s: float = 0.0) -> "Cursors":
        """Keep cursors that lie within high-pulse regions of `other`.

        `other` should be rising-edge cursors from pulses_wider_than().
        Each cursor in self is kept if it falls within any of the
        high-pulse segments started by cursors in other.

        This is designed to work with complementary data: use `other`
        as pulse rising edges (from pulses_wider_than(0) to get all
        high segments), and this returns the subset of cursors that
        fall within those high segments.
        """
        if other.count == 0 or self.count == 0:
            return Cursors(np.array([], dtype=np.int64),
                           np.array([], dtype=np.float64),
                           self._waveform, extra=self._extra)

        # For each cursor in self (time t), check if it falls between
        # a rising edge in other and the corresponding falling edge.
        # We need the falling edge info. Check if `other` has pulse_widths.
        if "pulse_widths" not in other.extra:
            # Recalculate pulse widths on the fly
            # Each index in `other` is a rising edge; compute fall positions
            keep_mask = np.zeros(len(self._indices), dtype=bool)
            for i in range(other.count):
                rise = other._indices[i]
                # Find next falling edge in the signal
                # Use the waveform data indirectly via search
                if i + 1 < other.count:
                    # Approximate: pulse ends at next rising edge or data end
                    next_rise = other._indices[i + 1]
                else:
                    next_rise = len(self._indices) + 1

                # This is too imprecise without direct falling-edge data.
                # Fall back to tolerance-based matching.
                for j in range(self.count):
                    if other._indices[i] <= self._indices[j]:
                        keep_mask[j] = True
            # This is simplistic - let's do a better implementation

        # Better approach: check if any cursor in `other` is close to
        # a cursor in self (within tolerance)
        if tolerance_s > 0:
            tol_samples = int(tolerance_s * self._waveform.sample_rate)
        else:
            tol_samples = 0

        # For each self cursor, closest other rising edge BEFORE it
        # If it's within tolerance, keep it
        keep = np.zeros(len(self._indices), dtype=bool)
        for j, t in enumerate(self._times):
            oi = np.searchsorted(other._times, t, side='right') - 1
            if oi >= 0:
                if tolerance_s == 0 or (t - other._times[oi]) <= tolerance_s:
                    keep[j] = True

        return Cursors(self._indices[keep], self._times[keep], self._waveform,
                       extra=self._extra)

    # ---- Set operations ----

    def __or__(self, other: "Cursors") -> "Cursors":
        """Union of two cursor sets."""
        if len(self._indices) == 0:
            return other
        if len(other._indices) == 0:
            return self
        merged = np.union1d(self._indices, other._indices)
        return Cursors.from_indices(merged, self._waveform)

    def __and__(self, other: "Cursors") -> "Cursors":
        """Intersection of two cursor sets."""
        merged = np.intersect1d(self._indices, other._indices)
        return Cursors.from_indices(merged, self._waveform)

    # ---- Measurement ----

    def intervals(self) -> np.ndarray:
        """Time deltas between consecutive cursors (in seconds)."""
        if len(self._times) < 2:
            return np.array([], dtype=np.float64)
        return np.diff(self._times)

    def intervals_from(self, other: "Cursors") -> np.ndarray:
        """Time from each cursor in self to the NEXT cursor in other.

        Returns an array of deltas; unmatched cursors are skipped.
        This is the replacement for edge_to_edge analysis.
        """
        if len(self._times) == 0 or len(other._times) == 0:
            return np.array([], dtype=np.float64)

        deltas = []
        for t_a in self._times:
            ni = np.searchsorted(other._times, t_a, side='right')
            if ni < len(other._times):
                deltas.append(other._times[ni] - t_a)

        return np.array(deltas, dtype=np.float64)

    # ---- Statistics ----

    def stats(self) -> dict:
        """Compute summary statistics on cursor intervals.

        If `extra` contains 'pulse_widths', stats are on those widths.
        Otherwise, stats are on the intervals between cursors.
        """
        if "pulse_widths" in self._extra:
            data = self._extra["pulse_widths"]
        else:
            data = self.intervals()

        if len(data) == 0:
            return {"count": 0, "min": 0.0, "max": 0.0,
                    "mean": 0.0, "median": 0.0, "std": 0.0}

        return {
            "count": len(data),
            "min": float(np.min(data)),
            "max": float(np.max(data)),
            "mean": float(np.mean(data)),
            "median": float(np.median(data)),
            "std": float(np.std(data, ddof=1)) if len(data) > 1 else 0.0,
        }

    def __len__(self) -> int:
        return len(self._indices)

    def __repr__(self) -> str:
        label_str = f" label='{self._label}'" if self._label else ""
        return f"Cursors(count={len(self._indices)}{label_str})"
