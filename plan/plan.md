# Logic Analyzer Waveform Analysis Framework

## Context

The file `isr.csv` (~50MB, 1.4M rows) is a waveform export from a logic analyzer (libsigrok4DSL). It records 12 digital channels in edge-triggered format — only timestamps where at least one signal changes. The user needs a modular, extensible Python analysis framework with plugin-based architecture.

## CSV Format

- Comment lines (4): start with `;`, contain metadata (sample rate 25 MHz, etc.)
- Header: `Time(s), 0, 1, 2, 3, tx, sync win, sync pul, rx, 8, 9, 10, 11`
- Data: time (seconds, high precision), 12 digital channels (0 or 1)
- Critical: channels "sync win" and "sync pul" have spaces in names; edge-triggered (values hold between rows)

## File Structure

```
Mouse_Demo/
├── analyze.py              # CLI entry point (single script, user-facing)
├── logic_analyzer/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── loader.py       # Waveform data container + CSV loading
│   │   └── plugin_base.py  # AnalysisPlugin ABC + AnalysisResult dataclass
│   └── plugins/
│       ├── __init__.py     # Plugin auto-discovery
│       ├── high_time_stats.py
│       └── edge_to_edge.py
```

## Data Loading (`core/loader.py`)

- `Waveform` class holds `times` (float64), `signals` (uint8 matrix), `column_names`
- `Waveform.load(filepath)`: counts comment lines, uses `np.loadtxt` with `skiprows`, splits time/signals
- `Waveform.get_signal(name)`: returns signal column by name
- `Waveform.slice(start_time, end_time)`: binary search via `np.searchsorted`, returns subset with `clipped=True` flag
- Memory: ~145MB peak for full load, acceptable for 50MB source

## Plugin System (`core/plugin_base.py`)

- `AnalysisResult`: dataclass with `plugin_name`, `description`, `data` dict, `warnings` list
- `AnalysisPlugin`: ABC with `name`, `description`, `configure_parser(parser)`, `analyze(waveform, args) -> AnalysisResult`
- Discovery (`plugins/__init__.py`): `pkgutil.iter_modules` scans files, instantiates plugin classes
- Each plugin = one file, no registration boilerplate

## Plugin: high_time_stats

- Input: signal name, optional start/end time
- Algorithm: detect rising edges (0→1) and falling edges (1→0) via diff
- Pair edges to form complete high periods, compute duration = `times[fall] - times[rise]`
- Edge cases: starts high (prepend rise at 0), ends high (open period → warn), always low (count=0)
- Output: count, min, max, mean, median, std of high durations

## Plugin: edge_to_edge

- Input: signal_a, edge_a (rising/falling/both), signal_b, edge_b (rising/falling/both)
- Algorithm: extract edge times for each signal, then `np.searchsorted(edges_b, edges_a)` to find next B edge for each A edge
- Output: count, min, max, mean, median, std of delta times
- Edge cases: no edges on A, no B edges after A, unmatched A edges (warned)

## CLI (`analyze.py`)

```bash
python analyze.py isr.csv high-time-stats tx
python analyze.py isr.csv --start-time 30 --end-time 35 high-time-stats rx
python analyze.py isr.csv edge-to-edge tx rising rx falling
python analyze.py isr.csv edge-to-edge "sync pul" rising rx both
```

Global args: `file`, `--start-time`, `--end-time`. Subcommands: one per plugin, each adds its own args.

## Adding a New Plugin

1. Create `logic_analyzer/plugins/my_plugin.py`
2. Define a class inheriting `AnalysisPlugin`
3. Implement `name`, `description`, `configure_parser()`, `analyze()`
4. No other files to touch — auto-discovered

## Verification

1. `python analyze.py isr.csv high-time-stats tx` — verify stats show
2. `python analyze.py isr.csv --start-time 30 --end-time 35 high-time-stats tx` — verify windowed
3. `python analyze.py isr.csv edge-to-edge tx rising rx falling` — verify delta stats
4. `python analyze.py isr.csv edge-to-edge "sync pul" both rx both` — verify spaces in names work
5. Test edge cases: signal always low, no edges after, etc.
