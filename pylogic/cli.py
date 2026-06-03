"""Command-line interface for pylogic waveform analysis.

Usage:
    pylogic run script.py                     # Run a Python analysis script
    pylogic edges capture.dsl -c CHANNEL      # Find rising edges
    pylogic pulses capture.dsl -c CHANNEL     # Find high pulses
"""
import argparse
import runpy
import sys

from .waveform import Waveform


def cmd_run(args):
    """Run a Python analysis script with pylogic imported."""
    runpy.run_path(args.script)


def cmd_edges(args):
    """Find all rising edges on a channel and optionally export."""
    wf = Waveform(args.file)
    edges = wf.channel(args.channel).rising_edges()

    label = args.label or f"{args.channel}_rising"
    edges = edges.cursor(label)

    print(f"Found {edges.count} rising edges on channel '{args.channel}'")

    if edges.count > 0 and edges.count <= 20:
        for i, t in enumerate(edges.times):
            print(f"  [{i}] t={t:.9f}s (sample {edges.indices[i]})")
    elif edges.count > 20:
        print(f"  (showing first 10 of {edges.count})")
        for i, t in enumerate(edges.times[:10]):
            print(f"  [{i}] t={t:.9f}s (sample {edges.indices[i]})")

    if args.output:
        wf.export(args.output).add_cursors(edges).write()
        print(f"Exported to {args.output}")


def cmd_pulses(args):
    """Find high pulses matching criteria and optionally export."""
    wf = Waveform(args.file)
    ch = wf.channel(args.channel)

    if args.wider_than is not None:
        cursors = ch.pulses_wider_than(args.wider_than)
        cond = f"wider than {args.wider_than}s"
    elif args.narrower_than is not None:
        cursors = ch.pulses_narrower_than(args.narrower_than)
        cond = f"narrower than {args.narrower_than}s"
    else:
        cursors = ch.pulse_widths()
        cond = ""

    label = args.label or f"{args.channel}_pulse"
    cursors = cursors.cursor(label)

    print(f"Found {cursors.count} high pulses on '{args.channel}'{(' ' + cond) if cond else ''}")

    if cursors.count > 0:
        stats = cursors.stats()
        print(f"  count={stats['count']} min={stats['min']:.9f}s max={stats['max']:.9f}s")
        print(f"  mean={stats['mean']:.9f}s median={stats['median']:.9f}s std={stats['std']:.9f}s")

    if args.output:
        wf.export(args.output).add_cursors(cursors).write()
        print(f"Exported to {args.output}")


def main():
    parser = argparse.ArgumentParser(
        prog="pylogic",
        description="Logic analyzer waveform analysis framework",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ---- run ----
    run_p = subparsers.add_parser("run", help="Run a Python analysis script")
    run_p.add_argument("script", help="Path to Python script")

    # ---- edges ----
    edges_p = subparsers.add_parser("edges", help="Find rising edges on a channel")
    edges_p.add_argument("file", help="Path to .dsl file")
    edges_p.add_argument("-c", "--channel", required=True, help="Channel name")
    edges_p.add_argument("-o", "--output", default=None, help="Output .dsl path")
    edges_p.add_argument("-l", "--label", default=None, help="Cursor label")

    # ---- pulses ----
    pulses_p = subparsers.add_parser("pulses", help="Find high pulses on a channel")
    pulses_p.add_argument("file", help="Path to .dsl file")
    pulses_p.add_argument("-c", "--channel", required=True, help="Channel name")
    group = pulses_p.add_mutually_exclusive_group()
    group.add_argument("--wider-than", type=float, default=None,
                       help="Minimum pulse width (seconds)")
    group.add_argument("--narrower-than", type=float, default=None,
                       help="Maximum pulse width (seconds)")
    pulses_p.add_argument("-o", "--output", default=None, help="Output .dsl path")
    pulses_p.add_argument("-l", "--label", default=None, help="Cursor label")

    args = parser.parse_args()

    if args.command == "run":
        cmd_run(args)
    elif args.command == "edges":
        cmd_edges(args)
    elif args.command == "pulses":
        cmd_pulses(args)


if __name__ == "__main__":
    main()
