#!/usr/bin/env python3
"""Compare a hyperfine run against the committed baseline, or rewrite the baseline.

check:  compare_bench.py --baseline test/bench/baseline.json --threshold 1.10 results/bench.json
        results[0] is the candidate parser. If the JSON holds two commands (bench.sh was
        given BASELINE_SO) the second one is the reference and the comparison is relative;
        otherwise the candidate is compared with baseline["bench"]["median_ms"], which is
        only meaningful on the machine class that produced the baseline.
        The gate is on medians (robust to a stray slow run on a shared runner):
        exit 1 when median_candidate / median_reference > threshold, or when
        bench-stat.txt reports failed parses.

write:  compare_bench.py --write-baseline test/bench/baseline.json --parser src/parser.c
            [--nixpkgs DIR] RESULTS_DIR
        Gathers RESULTS_DIR/bench.json, bench-stat.txt, memory.json and incremental/summary.json
        (whichever exist), the parser table sizes, a machine note and the nixpkgs revision the
        sample lists were measured against (NIXPKGS_REV, else `git -C DIR rev-parse HEAD`),
        and rewrites the baseline.

stdlib only; no repo paths are hardcoded.
"""

import argparse
import json
import os
import platform
import re
import statistics
import subprocess
import sys
from datetime import datetime, timezone


def load_results(path):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        sys.exit(f"compare_bench: {path} is missing or empty (did bench.sh fail?)")
    with open(path) as f:
        results = json.load(f)["results"]
    for r in results:
        # hyperfine JSON has no median; interleave.py's does
        r.setdefault("median", statistics.median(r["times"]))
    return results


def short_cmd(cmd):
    # keep only the .so name; the full command line is noise in a table
    m = re.search(r"--lib-path (\S+)", cmd)
    return os.path.basename(m.group(1)) if m else cmd


def fmt_ms(seconds):
    return f"{seconds * 1000:.1f}"


def parse_stat(path, required=False):
    """`tree-sitter parse --stat` totals: 'Total parses: N; successful parses: N; ... average speed: N bytes/ms'."""
    if not os.path.exists(path):
        if required:
            sys.exit(f"compare_bench: {path} is missing (did bench.sh fail?)")
        return {}
    text = open(path).read()
    if required and "Total" not in text:
        sys.exit(f"compare_bench: no 'Total' line in {path}; the failed-parses gate cannot run")
    out = {}
    m = re.search(r"failed parses:\s*(\d+)", text)
    if m:
        out["failed_parses"] = int(m.group(1))
    m = re.search(r"average speed:\s*(\d+)", text)
    if m:
        out["bytes_per_ms"] = int(m.group(1))
    return out


def check(args):
    results = load_results(args.results)
    cand = results[0]
    base = {}
    if os.path.exists(args.baseline):
        with open(args.baseline) as f:
            base = json.load(f)
    if len(results) >= 2:
        ref = results[1]
        ref_name = short_cmd(ref["command"])
        note = "reference = second parser, run alternately with the candidate"
    elif "bench" not in base:
        print(f"no baseline at {args.baseline} and no BASELINE_SO: nothing to compare against")
        print(f"candidate {short_cmd(cand['command'])}: median {fmt_ms(cand['median'])} ms, "
              f"mean {fmt_ms(cand['mean'])} ± {fmt_ms(cand['stddev'])} "
              f"(min {fmt_ms(cand['min'])}, max {fmt_ms(cand['max'])}, {len(cand['times'])} runs)")
        print("run `make bench-baseline` to record it")
        return 0
    else:
        b = base["bench"]
        ref = {
            "mean": b["mean_ms"] / 1000.0,
            "stddev": b.get("stddev_ms", 0.0) / 1000.0,
            "median": b.get("median_ms", b["mean_ms"]) / 1000.0,
            "min": b.get("min_ms", b["mean_ms"]) / 1000.0,
            "max": b.get("max_ms", b["mean_ms"]) / 1000.0,
            "times": [None] * b.get("runs", 0),
        }
        ref_name = f"baseline.json ({base.get('commit', '?')[:9]})"
        note = f"reference = committed baseline measured on {base.get('machine', {}).get('cpu', 'unknown cpu')}"
    ratio = cand["median"] / ref["median"]
    stat = parse_stat(os.path.join(os.path.dirname(args.results), "bench-stat.txt"), required=True)

    print("| parser | median ms | mean | stddev | min | max | runs | ratio (median) |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|")
    for name, r, rt in ((short_cmd(cand["command"]), cand, f"{ratio:.3f}"), (ref_name, ref, "1.000")):
        print(
            f"| {name} | {fmt_ms(r['median'])} | {fmt_ms(r['mean'])} | {fmt_ms(r['stddev'])} | "
            f"{fmt_ms(r['min'])} | {fmt_ms(r['max'])} | {len(r['times'])} | {rt} |"
        )
    print(f"\nparse --stat: {stat.get('bytes_per_ms', '?')} bytes/ms, failed parses: {stat.get('failed_parses', '?')}")
    print(f"\n{note}; threshold {args.threshold}")
    if stat.get("failed_parses"):
        print(f"FAIL: {stat['failed_parses']} files failed to parse")
        return 1
    if ratio > args.threshold:
        print(f"FAIL: candidate median is {ratio:.3f}x the reference (> {args.threshold})")
        return 1
    print("OK")
    return 0


def git(*argv):
    try:
        return subprocess.check_output(["git", *argv], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def machine_note():
    cpu = ""
    try:
        for line in open("/proc/cpuinfo"):
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    return {
        "cpu": cpu or platform.processor() or "unknown",
        "cores": os.cpu_count(),
        "os": f"{platform.system()} {platform.release()}",
        "hostname": platform.node(),
    }


def table_sizes(parser_c):
    out = {}
    for line in open(parser_c):
        m = re.match(r"#define (STATE_COUNT|SYMBOL_COUNT|TOKEN_COUNT|LANGUAGE_VERSION) (\d+)", line)
        if m:
            out[m.group(1).lower()] = int(m.group(2))
        if line.startswith("#define") and len(out) == 4:
            break
    return out


def write_baseline(args):
    rd = args.results_dir
    bench_json = os.path.join(rd, "bench.json")
    if not os.path.exists(bench_json):
        print(f"missing {bench_json}: run `make bench` first", file=sys.stderr)
        return 2
    cand = load_results(bench_json)[0]
    base = {}
    if os.path.exists(args.write_baseline):
        with open(args.write_baseline) as f:
            base = json.load(f)
    base["commit"] = git("rev-parse", "HEAD") or base.get("commit", "")
    base["date"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    base["machine"] = machine_note()
    base["tree_sitter_cli"] = os.environ.get("TS_VERSION", base.get("tree_sitter_cli", ""))
    # the sample lists are only valid at one nixpkgs revision; CI checks it out
    base["nixpkgs_rev"] = (os.environ.get("NIXPKGS_REV")
                           or (git("-C", args.nixpkgs, "rev-parse", "HEAD") if args.nixpkgs else "")
                           or base.get("nixpkgs_rev", ""))
    if not base["nixpkgs_rev"]:
        print("warning: nixpkgs revision unknown (set NIXPKGS_REV or --nixpkgs <git checkout>)", file=sys.stderr)
    base["bench"] = {
        "sample": "test/bench/sample2000.txt",
        "runs": len(cand["times"]),
        "median_ms": round(cand["median"] * 1000, 2),
        "mean_ms": round(cand["mean"] * 1000, 2),
        "stddev_ms": round(cand["stddev"] * 1000, 2),
        "min_ms": round(cand["min"] * 1000, 2),
        "max_ms": round(cand["max"] * 1000, 2),
        **parse_stat(os.path.join(rd, "bench-stat.txt")),
    }
    mem_json = os.path.join(rd, "memory.json")
    if os.path.exists(mem_json):
        with open(mem_json) as f:
            base["memory"] = json.load(f)
    incr_json = os.path.join(rd, "incremental", "summary.json")
    if os.path.exists(incr_json):
        with open(incr_json) as f:
            base["incremental"] = json.load(f)
    if args.parser:
        base.update(table_sizes(args.parser))
    with open(args.write_baseline, "w") as f:
        json.dump(base, f, indent=2)
        f.write("\n")
    print(f"wrote {args.write_baseline}")
    print(json.dumps(base, indent=2))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--baseline", help="baseline.json to compare against")
    ap.add_argument("--threshold", type=float, default=1.10)
    ap.add_argument("--write-baseline", metavar="FILE", help="rewrite FILE from RESULTS_DIR instead of checking")
    ap.add_argument("--parser", help="src/parser.c, for STATE_COUNT etc. (write mode)")
    ap.add_argument("--nixpkgs", help="nixpkgs checkout the sample lists were measured against (write mode)")
    ap.add_argument("target", help="hyperfine JSON (check) or results directory (write)")
    args = ap.parse_args()
    if args.write_baseline:
        args.results_dir = args.target
        return write_baseline(args)
    if not args.baseline:
        ap.error("--baseline is required in check mode")
    args.results = args.target
    return check(args)


if __name__ == "__main__":
    sys.exit(main())
