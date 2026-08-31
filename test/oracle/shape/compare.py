#!/usr/bin/env python3
"""
AST shape oracle: for every file in a list, print the AST with
`nix-instantiate --parse` and reconstruct the same text from the
tree-sitter-nix parse tree (ts2nix.py); the two must match byte-for-byte.
A mismatch means tree-sitter produced a tree whose *shape* differs from
Nix's (wrong precedence, wrong string stripping, wrong path
canonicalisation, ...) even though the file parsed without ERROR nodes.

Status per file: match | mismatch | conv-error (ts2nix could not convert:
ERROR nodes or an unsupported construct) | conv-exception (ts2nix bug) |
nix-error (nix-instantiate itself rejects the file, nothing to compare) |
missing (file not found under the root). Exit 1 on any mismatch,
conv-error or conv-exception; nix-error is reported only. A few missing
files are a warning (nixpkgs revision drift), more than 10% of the list
missing fails the run (wrong root or a sparse checkout without the
sampled trees); --fail-on-missing makes any missing file fatal.

Environment:
  NIXPKGS      root that relative paths in the list resolve against
               (fallbacks: $NIXPKGS_PATH, then <nixpkgs> from the Nix search
               path; --root overrides)
  TS_BIN, TS_NIX_LIB, NIX_BIN  as in ts2nix.py / differential.py

Usage:
  python3 test/oracle/shape/compare.py [--root DIR] [--jobs N] [--out PREFIX]
      [--fail-on-missing] LIST   (LIST = file of paths, one per line; `-` = stdin)
"""
import argparse
import os
import subprocess
import sys
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, HERE)
import ts2nix  # noqa: E402

NIX_BIN = os.environ.get("NIX_BIN") or "nix-instantiate"
DEFAULT_OUT = os.path.join(REPO, "test", "oracle", "out", "shape")
FATAL = ("mismatch", "conv-error", "conv-exception")


def default_root():
    env = os.environ.get("NIXPKGS") or os.environ.get("NIXPKGS_PATH")
    if env:
        return env
    try:
        p = subprocess.run([NIX_BIN, "--eval", "--expr", "builtins.toString <nixpkgs>"],
                           capture_output=True, text=True)
        if p.returncode == 0:
            return p.stdout.strip().strip('"')
    except FileNotFoundError:
        pass
    return ""


def one(args):
    f, root = args
    path = f if os.path.isabs(f) else os.path.join(root, f)
    if not os.path.isfile(path):
        return (f, "missing", path, None, None)
    r = subprocess.run([NIX_BIN, "--extra-experimental-features", "pipe-operators", "--parse", path],
                       capture_output=True)
    if r.returncode != 0:
        err = r.stderr.decode("utf-8", "replace").strip().splitlines()
        return (f, "nix-error", (err[0] if err else "")[:200], None, None)
    nixout = r.stdout.decode("utf-8", "surrogateescape").rstrip("\n")
    try:
        ts = ts2nix.convert(path)
    except ts2nix.ConvError as e:
        return (f, "conv-error", str(e)[:200], nixout, None)
    except Exception as e:  # a converter bug, not a grammar finding
        return (f, "conv-exception", repr(e)[:200], nixout, None)
    if ts == nixout:
        return (f, "match", "", None, None)
    i = 0
    n = min(len(ts), len(nixout))
    while i < n and ts[i] == nixout[i]:
        i += 1
    ctx = "nix: ...%s... | ts: ...%s..." % (
        nixout[max(0, i - 40):i + 60].replace("\n", "\\n"), ts[max(0, i - 40):i + 60].replace("\n", "\\n"))
    return (f, "mismatch", ctx[:400], nixout, ts)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("list", help="file with one path per line, or - for stdin")
    ap.add_argument("--root", default=None, help="root for relative paths (default: $NIXPKGS or <nixpkgs>)")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--out", default=DEFAULT_OUT,
                    help="output prefix: PREFIX.tsv and PREFIX.mismatches/ (default: test/oracle/out/shape)")
    ap.add_argument("--fail-on-missing", action="store_true")
    args = ap.parse_args()

    root = args.root or default_root()
    fh = sys.stdin if args.list == "-" else open(args.list)
    files = [l.strip() for l in fh if l.strip() and not l.startswith("#")]
    if any(not os.path.isabs(f) for f in files):
        if not root:
            sys.exit("compare: relative paths in the list but no root (set NIXPKGS or pass --root)")
        if not os.path.isdir(root):
            sys.exit("compare: root does not exist: %s" % root)

    mm_dir = args.out + ".mismatches"
    os.makedirs(mm_dir, exist_ok=True)
    counts = {}
    problems = []
    ts2nix.warm_up()
    with Pool(max(1, args.jobs)) as p, open(args.out + ".tsv", "w") as o:
        for f, st, det, nixout, ts in p.imap_unordered(one, [(f, root) for f in files], chunksize=4):
            counts[st] = counts.get(st, 0) + 1
            o.write("%s\t%s\t%s\n" % (f, st, det))
            if st != "match":
                problems.append((f, st, det))
            if st == "mismatch":
                base = os.path.join(mm_dir, f.replace("/", "__"))
                open(base + ".nix-parse.txt", "w", encoding="utf-8", errors="surrogateescape").write(nixout + "\n")
                open(base + ".ts2nix.txt", "w", encoding="utf-8", errors="surrogateescape").write(ts + "\n")

    print("shape oracle: %d files under %s" % (len(files), root or "(absolute paths)"))
    for st in ("match", "mismatch", "conv-error", "conv-exception", "nix-error", "missing"):
        if st in counts:
            print("  %-15s %d" % (st, counts[st]))
    print("  results: %s.tsv  mismatch dumps: %s/" % (args.out, mm_dir))
    fatal = [p for p in problems if p[1] in FATAL or (args.fail_on_missing and p[1] == "missing")]
    for f, st, det in sorted(problems, key=lambda x: (x[1], x[0])):
        print("  %-15s %s\t%s" % (st, f, det))
    missing = counts.get("missing", 0)
    if missing:
        print("WARNING: %d file(s) missing under the root (nixpkgs revision drift? "
              "regenerate sample.txt with make-sample.py)" % missing)
    if missing > len(files) // 10:
        print("FAIL: %d of %d files missing; the root does not hold the sampled trees" % (missing, len(files)))
        return 1
    if fatal:
        print("FAIL: %d file(s) with a shape problem" % len(fatal))
        return 1
    if not counts.get("match"):
        # Nothing compared at all: the root is wrong, not the grammar right.
        print("FAIL: no file could be compared")
        return 1
    print("OK: every comparable file matches nix-instantiate --parse")
    return 0


if __name__ == "__main__":
    sys.exit(main())
