import numpy as np
from ..core.plugin_base import AnalysisPlugin, AnalysisResult


class EdgeToEdgePlugin(AnalysisPlugin):
    @property
    def name(self):
        return "edge-to-edge"

    @property
    def description(self):
        return "Measure time from an edge on signal A to the next edge on signal B."

    def configure_parser(self, parser):
        parser.add_argument("signal_a", help="First signal name")
        parser.add_argument("edge_a", choices=["rising", "falling", "both"], help="Edge type for signal A")
        parser.add_argument("signal_b", help="Second signal name")
        parser.add_argument("edge_b", choices=["rising", "falling", "both"], help="Edge type for signal B")

    def _extract_edges(self, signal, times, edge_type):
        diff = np.diff(signal.astype(np.int8))
        if edge_type == "rising":
            return times[np.where(diff == 1)[0] + 1]
        elif edge_type == "falling":
            return times[np.where(diff == -1)[0] + 1]
        else:
            return times[np.where(diff != 0)[0] + 1]

    def analyze(self, waveform, args):
        signal_a = waveform.get_signal(args.signal_a)
        signal_b = waveform.get_signal(args.signal_b)
        times = waveform.times

        edges_a = self._extract_edges(signal_a, times, args.edge_a)
        edges_b = self._extract_edges(signal_b, times, args.edge_b)

        warnings = []

        if len(edges_a) == 0:
            return AnalysisResult(
                plugin_name=self.name,
                description=f"Edge-to-edge: {args.signal_a}[{args.edge_a}] -> {args.signal_b}[{args.edge_b}]",
                data={"count": 0, "min": 0.0, "max": 0.0, "mean": 0.0, "median": 0.0, "std": 0.0},
                warnings=["No edges found on signal A"],
            )

        deltas = []
        for t_a in edges_a:
            ni = np.searchsorted(edges_b, t_a, side='right')
            if ni >= len(edges_b):
                warnings.append(
                    f"No {args.edge_b} edge on {args.signal_b} after "
                    f"{args.edge_a} edge on {args.signal_a} at t={t_a:.6f}"
                )
                continue
            deltas.append(edges_b[ni] - t_a)

        if len(deltas) == 0:
            return AnalysisResult(
                plugin_name=self.name,
                description=f"Edge-to-edge: {args.signal_a}[{args.edge_a}] -> {args.signal_b}[{args.edge_b}]",
                data={"count": 0, "min": 0.0, "max": 0.0, "mean": 0.0, "median": 0.0, "std": 0.0},
                warnings=warnings,
            )

        deltas = np.array(deltas)

        return AnalysisResult(
            plugin_name=self.name,
            description=f"Edge-to-edge: {args.signal_a}[{args.edge_a}] -> {args.signal_b}[{args.edge_b}]",
            data={
                "count": int(len(deltas)),
                "min": float(np.min(deltas)),
                "max": float(np.max(deltas)),
                "mean": float(np.mean(deltas)),
                "median": float(np.median(deltas)),
                "std": float(np.std(deltas, ddof=1)) if len(deltas) > 1 else 0.0,
            },
            warnings=warnings,
        )
