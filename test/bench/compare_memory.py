#!/usr/bin/env python3
"""Summarise memory.sh outputs into RESULTS_DIR/memory.json and gate bytes/node.

usage: compare_memory.py --baseline test/bench/baseline.json --threshold 1.05 RESULTS_DIR

Reads memory-summary.txt (harness totals), memory-rss.tsv (parser reuse run) and, when
present, memory-rawwalk.txt (hidden internal nodes). Exits 1 when
bytes_per_node > baseline["memory"]["bytes_per_node"] * threshold or the harness saw
ERROR/MISSING nodes where the baseline had none. stdlib only.
"""

import argparse
import json
import os
import re
import sys


def read_summary(path):
    out = {}
    for line in open(path):
        if line.startswith("#"):
            k, v = line[1:].rstrip("\n").split("\t", 1)
            out[k] = float(v) if "." in v else int(v)
        elif line.startswith("list:"):
            out["list"] = line[5:].strip()
    return out


def read_rss(path):
    rows = [l.rstrip("\n").split("\t") for l in open(path) if l.strip()]
    header, body = rows[0], rows[1:]
    out = {}
    for r in body:
        if r[0] == "after_parser_delete":
            out["rss_kb_after_parser_delete"] = int(r[1])
            out["live_bytes_after_parser_delete"] = int(r[2])
        elif r[0] == "peak_rss_kb":
            out["peak_rss_kb"] = int(r[1])
        else:
            rec = dict(zip(header, r))
            out["rss_kb_end"] = int(rec["rss_kb"])
            out["n_alloc"] = int(rec["n_alloc"])
            out["total_alloc_bytes"] = int(rec["total_alloc"])
    return out


def read_rawwalk(path):
    text = open(path).read()
    out = {}
    for key in ("inline_leaf", "heap_leaf", "heap_internal", "visible_internal", "hidden_internal", "heap_bytes"):
        m = re.search(rf"\b{key}=(\d+)", text)
        if m:
            out[key] = int(m.group(1))
    hidden = {}
    for m in re.finditer(r"^hidden\t(\S+)\t(\d+)$", text, re.M):
        hidden[m.group(1)] = int(m.group(2))
    out["hidden_by_symbol"] = dict(sorted(hidden.items(), key=lambda kv: -kv[1])[:10])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--threshold", type=float, default=1.05)
    ap.add_argument("results_dir")
    args = ap.parse_args()
    rd = args.results_dir

    s = read_summary(os.path.join(rd, "memory-summary.txt"))
    mem = {
        "list": s.get("list", ""),
        "files": s["files"],
        "src_bytes": s["src_bytes"],
        "tree_bytes": s["tree_bytes"],
        "nodes": s["nodes"],
        "named": s["named"],
        "anon": s["anon"],
        "error": s["error"],
        "missing": s["missing"],
        "bytes_per_node": round(s["tree_bytes"] / s["nodes"], 2),
        "tree_bytes_per_src_byte": round(s["tree_bytes"] / s["src_bytes"], 3),
        "parse_ms": s["parse_ms"],
        "bytes_per_ms": s["bytes_per_ms"],
    }
    mem.update(read_rss(os.path.join(rd, "memory-rss.tsv")))
    raw = os.path.join(rd, "memory-rawwalk.txt")
    if os.path.exists(raw):
        mem.update(read_rawwalk(raw))
    with open(os.path.join(rd, "memory.json"), "w") as f:
        json.dump(mem, f, indent=2)
        f.write("\n")

    base = {}
    if os.path.exists(args.baseline):
        with open(args.baseline) as f:
            base = json.load(f).get("memory", {})

    def row(k, fmt="{}"):
        b = base.get(k)
        return f"| {k} | {fmt.format(mem[k]) if k in mem else 'n/a'} | {fmt.format(b) if b is not None else 'n/a'} |"

    print("| metric | now | baseline |")
    print("|---|---:|---:|")
    for k in ("files", "nodes", "tree_bytes", "bytes_per_node", "tree_bytes_per_src_byte", "hidden_internal",
              "visible_internal", "error", "missing", "peak_rss_kb", "rss_kb_after_parser_delete", "n_alloc",
              "parse_ms", "bytes_per_ms"):
        print(row(k))
    if mem.get("hidden_by_symbol"):
        top = ", ".join(f"{k}={v}" for k, v in mem["hidden_by_symbol"].items())
        print(f"\ntop hidden symbols: {top}")

    rc = 0
    if "bytes_per_node" in base:
        ratio = mem["bytes_per_node"] / base["bytes_per_node"]
        print(f"\nbytes/node ratio vs baseline: {ratio:.3f} (threshold {args.threshold})")
        if ratio > args.threshold:
            print("FAIL: bytes/node regressed")
            rc = 1
    else:
        print("\nno memory baseline yet: run `make bench-baseline` after `make bench memory`")
    if (mem["error"] or mem["missing"]) and not (base.get("error") or base.get("missing")):
        print(f"FAIL: {mem['error']} ERROR / {mem['missing']} MISSING nodes, baseline had none")
        rc = 1
    if mem.get("live_bytes_after_parser_delete", 0) > 0:
        print(f"FAIL: {mem['live_bytes_after_parser_delete']} bytes still allocated after ts_parser_delete (leak)")
        rc = 1
    print("OK" if rc == 0 else "")
    return rc


if __name__ == "__main__":
    sys.exit(main())
