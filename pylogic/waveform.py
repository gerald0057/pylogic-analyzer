import numpy as np

from ._native import DslReader
from .channel import Channel
from .errors import ChannelNotFoundError


class Waveform:
    """A loaded .dsl logic analyzer capture file.

    Entry point for all analysis. Wraps the Rust DslReader and
    provides lazy-loaded channel access.

    Usage:
        wf = Waveform("capture.dsl")
        tx = wf.channel("tx")
        edges = tx.rising_edges()
    """

    def __init__(self, path: str):
        self._path = path
        self._reader = DslReader.open(path)
        h = self._reader.get_header()

        self._sample_rate: float = float(h["samplerate"])
        self._total_samples: int = int(h["total_samples"])
        self._probe_names: list[str] = list(h["probe_names"])
        self._probe_cache: dict[int, np.ndarray] = {}
        self._channel_cache: dict[str, Channel] = {}

    @property
    def path(self) -> str:
        return self._path

    @property
    def sample_rate(self) -> float:
        """Sample rate in Hz."""
        return self._sample_rate

    @property
    def total_samples(self) -> int:
        """Total number of samples."""
        return self._total_samples

    @property
    def duration(self) -> float:
        """Capture duration in seconds."""
        return self._total_samples / self._sample_rate

    @property
    def probe_names(self) -> list[str]:
        """List of probe names."""
        return self._probe_names

    def _resolve_probe(self, name: str) -> int:
        """Resolve a channel name to a probe number.

        Raises ChannelNotFoundError if not found.
        """
        # Try exact match first
        for i, n in enumerate(self._probe_names):
            if n == name:
                return i
        raise ChannelNotFoundError(
            f"Channel '{name}' not found. Available: {self._probe_names}"
        )

    def _load_probe(self, probe: int) -> np.ndarray:
        """Load probe data (lazy, cached)."""
        if probe not in self._probe_cache:
            self._probe_cache[probe] = self._reader.read_channel(probe)
        return self._probe_cache[probe]

    def channel(self, name: str) -> Channel:
        """Get a channel by name. Data is loaded lazily.

        Returns a Channel object for method chaining.
        """
        if name in self._channel_cache:
            return self._channel_cache[name]

        idx = self._resolve_probe(name)
        data = self._load_probe(idx)
        ch = Channel(data, self, name=name)
        self._channel_cache[name] = ch
        return ch

    def channel_at(self, idx: int) -> Channel:
        """Get a channel by probe index (0-based)."""
        data = self._load_probe(idx)
        name = self._probe_names[idx] if idx < len(self._probe_names) else str(idx)
        return Channel(data, self, name=name, probe_index=idx)

    def export(self, output_path: str):
        """Start building a .dsl export with cursor annotations.

        Usage:
            wf.export("output.dsl").add_cursors(edges).write()
        """
        from .export import DslExport
        return DslExport(self, output_path)

    def __repr__(self) -> str:
        return (f"Waveform('{self._path}', "
                f"probes={len(self._probe_names)}, "
                f"samples={self._total_samples}, "
                f"rate={self._sample_rate:.0f}Hz)")
