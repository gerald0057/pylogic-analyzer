# pylogic-analyzer

Modular logic analyzer waveform analysis framework with plugin-based architecture.

## Install

```bash
pip install numpy
```

## Usage

```bash
# High-time stats on a signal
python analyze.py isr.csv high-time-stats tx

# Windowed analysis
python analyze.py isr.csv --start-time 30 --end-time 35 high-time-stats rx

# Edge-to-edge timing
python analyze.py isr.csv edge-to-edge tx rising rx falling
python analyze.py isr.csv edge-to-edge "sync pul" both rx both
```

## Plugins

| Plugin | Description |
|---|---|
| `high-time-stats` | Pulse duration statistics (count, min, max, mean, median, std) |
| `edge-to-edge` | Delta-time between an edge on signal A and the next edge on signal B |

## Add a Plugin

Create a file in `logic_analyzer/plugins/`:

```python
from ..core.plugin_base import AnalysisPlugin, AnalysisResult

class MyPlugin(AnalysisPlugin):
    name = "my-plugin"
    description = "What it does."

    def configure_parser(self, parser):
        parser.add_argument("signal", help="Signal to analyze")

    def analyze(self, waveform, args) -> AnalysisResult:
        ...
```

No other files to touch — plugins are auto-discovered.
