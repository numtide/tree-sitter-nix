#!/usr/bin/env python3
"""
Regenerate sample.txt: a deterministic, stratified list of nixpkgs files
for the shape oracle. Strata: every lib/*.nix (the operator-heavy core),
every pkgs/top-level/** (the largest attribute sets), a fixed-seed sample
of nixos/modules/**, and a fixed-seed sample of the rest of pkgs/** to
fill up to --size. Output is sorted so the file diffs cleanly.

Environment:
  NIXPKGS   nixpkgs checkout to enumerate (or --root)

Usage: python3 test/oracle/shape/make-sample.py [--root DIR] [--size 3000]
           [--modules 800] [--seed 20260831] [-o sample.txt]
"""
import argparse
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def walk(root, sub):
    out = []
    for dirpath, dirnames, filenames in os.walk(os.path.join(root, sub)):
        dirnames.sort()
        for fn in filenames:
            if fn.endswith(".nix"):
                out.append(os.path.relpath(os.path.join(dirpath, fn), root))
    return sorted(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=os.environ.get("NIXPKGS"))
    ap.add_argument("--size", type=int, default=3000)
    ap.add_argument("--modules", type=int, default=800, help="how many nixos/modules files")
    ap.add_argument("--seed", type=int, default=20260831)
    ap.add_argument("-o", "--output", default=os.path.join(HERE, "sample.txt"))
    args = ap.parse_args()
    if not args.root:
        sys.exit("make-sample: set NIXPKGS or pass --root")

    lib = sorted(f for f in os.listdir(os.path.join(args.root, "lib")) if f.endswith(".nix"))
    lib = ["lib/" + f for f in lib]
    top = walk(args.root, "pkgs/top-level")
    modules = walk(args.root, "nixos/modules")
    pkgs = [f for f in walk(args.root, "pkgs") if not f.startswith("pkgs/top-level/")]
    rng = random.Random(args.seed)
    pick_mod = rng.sample(modules, min(args.modules, len(modules)))
    remaining = max(0, args.size - len(lib) - len(top) - len(pick_mod))
    pick_pkgs = rng.sample(pkgs, min(remaining, len(pkgs)))
    chosen = sorted(set(lib) | set(top) | set(pick_mod) | set(pick_pkgs))
    with open(args.output, "w") as fh:
        fh.write("# nixpkgs-relative paths for test/oracle/shape/compare.py; regenerate with make-sample.py\n")
        fh.write("".join(f + "\n" for f in chosen))
    print("wrote %s: %d files (lib=%d, pkgs/top-level=%d, nixos/modules=%d, pkgs=%d) from %s" % (
        args.output, len(chosen), len(lib), len(top), len(pick_mod), len(pick_pkgs), args.root))


if __name__ == "__main__":
    main()
