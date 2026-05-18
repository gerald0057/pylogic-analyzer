import numpy as np
from ..core.plugin_base import AnalysisPlugin, AnalysisResult


class HighTimeStatsPlugin(AnalysisPlugin):
    @property
    def name(self):
        return "high-time-stats"

    @property
    def description(self):
        return "Compute statistics on high-pulse durations for a signal."

    def configure_parser(self, parser):
        parser.add_argument("signal", help="Signal name to analyze")

    def analyze(self, waveform, args):
        signal = waveform.get_signal(args.signal)
        times = waveform.times
        diff = np.diff(signal.astype(np.int8))
        rise_idx = np.where(diff == 1)[0] + 1
        fall_idx = np.where(diff == -1)[0] + 1
        warnings = []

        if signal[0] == 1:
            rise_idx = np.concatenate(([0], rise_idx))

        if len(rise_idx) == 0 and len(fall_idx) == 0:
            if np.all(signal == 0):
                return AnalysisResult(
                    plugin_name=self.name,
                    description=f"High-time stats for {args.signal}",
                    data={"count": 0, "min": 0.0, "max": 0.0, "mean": 0.0, "median": 0.0, "std": 0.0},
                )
            else:
                return AnalysisResult(
                    plugin_name=self.name,
                    description=f"High-time stats for {args.signal}",
                    data={"count": 1, "min": 0.0, "max": 0.0, "mean": 0.0, "median": 0.0, "std": 0.0},
                )

        durations = []
        for i, r in enumerate(rise_idx):
            ni = np.searchsorted(fall_idx, r)
            if ni >= len(fall_idx):
                start = times[r] if r > 0 else times[0]
                dur = times[-1] - start
                warnings.append(
                    f"Open high period starting at t={start:.6f}: "
                    f"no falling edge after rise. Using end of slice as fall."
                )
                durations.append(dur)
            else:
                f = fall_idx[ni]
                durations.append(times[f] - times[r])

        durations = np.array(durations)

        return AnalysisResult(
            plugin_name=self.name,
            description=f"High-time stats for {args.signal}",
            data={
                "count": int(len(durations)),
                "min": float(np.min(durations)),
                "max": float(np.max(durations)),
                "mean": float(np.mean(durations)),
                "median": float(np.median(durations)),
                "std": float(np.std(durations, ddof=1)) if len(durations) > 1 else 0.0,
            },
            warnings=warnings,
        )
