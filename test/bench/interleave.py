#!/usr/bin/env python3
"""Time two or more commands by running them alternately (A B A B ...).

usage: interleave.py [--warmup N] [--runs N] [--export-json FILE]
                     [--export-markdown FILE] CMD [CMD ...]

Each CMD is one shell-style string, split with shlex and executed without a
shell. Every round runs each command once, reversing the order on odd rounds so
neither always goes first; a load change on the machine therefore hits every
command equally, which is what makes the ratio between them meaningful
(hyperfine runs all of A, then all of B). A non-zero exit of any run aborts with
that run's stderr. The JSON has hyperfine's layout ({"results": [{"command",
"mean", "stddev", "median", "min", "max", "times", "exit_codes"}]}) so the
comparison script does not care which driver produced it.

stdlib only; no repo paths are hardcoded.
"""

import argparse
import json
import shlex
import statistics
import subprocess
import sys
import time


def run_once(argv):
    t0 = time.perf_counter()
    r = subprocess.run(argv, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    dt = time.perf_counter() - t0
    if r.returncode != 0:
        sys.stderr.write(r.stderr.decode("utf-8", "replace"))
        sys.exit("interleave: '%s' exited %d" % (" ".join(argv), r.returncode))
    return dt


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--warmup", type=int, default=2)
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--export-json")
    ap.add_argument("--export-markdown")
    ap.add_argument("commands", nargs="+", metavar="CMD")
    args = ap.parse_args()
    if args.runs < 1:
        ap.error("--runs must be >= 1")
    argvs = [shlex.split(c) for c in args.commands]
    order = list(range(len(argvs)))

    for _ in range(args.warmup):
        for i in order:
            run_once(argvs[i])
    times = [[] for _ in argvs]
    for rnd in range(args.runs):
        for i in (order if rnd % 2 == 0 else order[::-1]):
            times[i].append(run_once(argvs[i]))

    results = []
    for cmd, ts in zip(args.commands, times):
        results.append({
            "command": cmd,
            "mean": statistics.fmean(ts),
            "stddev": statistics.stdev(ts) if len(ts) > 1 else 0.0,
            "median": statistics.median(ts),
            "min": min(ts),
            "max": max(ts),
            "times": ts,
            "exit_codes": [0] * len(ts),
        })
    md = ["| command | mean ms | stddev | median | min | max | runs |", "|---|---:|---:|---:|---:|---:|---:|"]
    for r in results:
        md.append("| `%s` | %.1f | %.1f | %.1f | %.1f | %.1f | %d |" % (
            r["command"], r["mean"] * 1000, r["stddev"] * 1000, r["median"] * 1000,
            r["min"] * 1000, r["max"] * 1000, len(r["times"])))
    print("\n".join(md))
    if args.export_json:
        with open(args.export_json, "w") as f:
            json.dump({"results": results}, f, indent=2)
            f.write("\n")
    if args.export_markdown:
        with open(args.export_markdown, "w") as f:
            f.write("\n".join(md) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
