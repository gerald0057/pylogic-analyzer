#!/usr/bin/env python3
import argparse
import sys
from logic_analyzer.core.loader import Waveform
from logic_analyzer.plugins import discover_plugins


def main():
    plugins = discover_plugins()
    plugin_map = {p.name: p for p in plugins}

    parser = argparse.ArgumentParser(description="Logic Analyzer Waveform Analysis")
    parser.add_argument("file", help="Path to waveform CSV file")
    parser.add_argument("--start-time", type=float, default=None, help="Start time for analysis window (seconds)")
    parser.add_argument("--end-time", type=float, default=None, help="End time for analysis window (seconds)")

    subparsers = parser.add_subparsers(dest="plugin", required=True, help="Analysis plugin to run")

    for plugin in plugins:
        sub = subparsers.add_parser(plugin.name, help=plugin.description)
        plugin.configure_parser(sub)

    args = parser.parse_args()

    waveform = Waveform.load(args.file)

    if args.start_time is not None or args.end_time is not None:
        waveform = waveform.slice(args.start_time, args.end_time)

    plugin = plugin_map[args.plugin]
    result = plugin.analyze(waveform, args)

    print(f"=== {result.description} ===")
    for key, value in result.data.items():
        print(f"  {key}: {value}")
    if result.warnings:
        print("Warnings:")
        for w in result.warnings:
            print(f"  - {w}")


if __name__ == "__main__":
    main()
