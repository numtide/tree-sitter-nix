#!/usr/bin/env python3
"""
Differential oracle: tree-sitter-nix vs `nix-instantiate --parse` on the
reference corpora pinned in corpora.lock (NixOS/nix lang tests, rnix-parser
parser tests, snix eval tests).

For every corpus file both parsers are asked "is this syntactically valid
Nix?". A *disagreement* is a file where the answers differ. The set of
disagreements is compared against a committed baseline; any disagreement
not in the baseline fails the run (exit 1), disagreements that vanished are
reported as improvements (exit 0, then refresh the baseline with
--update-baseline).

nix-instantiate rejects some files for non-syntactic reasons (undefined
variables, duplicate attributes, ...). Those are classified from stderr and
count as "accepted by the grammar", so only true syntax errors disagree
with a clean tree-sitter parse.

Environment:
  TS_BIN       tree-sitter CLI (default: `tree-sitter` on PATH)
  TS_NIX_LIB   compiled parser (.so/.dylib) to parse with. When unset the CLI
               runs from the repo root and compiles the grammar itself into
               $TREE_SITTER_LIBDIR (set that to a private dir in CI).
  NIX_BIN      nix-instantiate binary (default: `nix-instantiate` on PATH)
  CORPORA_DIR  where fetch-corpora.sh put the corpora
               (default: test/oracle/corpora); --corpora-dir overrides.
  NIX_SRC, RNIX_SRC, SNIX_SRC
               use an existing checkout for that corpus instead of
               $CORPORA_DIR/<name> (same overrides fetch-corpora.sh takes).

Usage:
  python3 test/oracle/differential.py [--jobs N] [--corpora-dir DIR]
      [--baseline FILE] [--out FILE] [--trees-dir DIR] [--update-baseline]
"""

import argparse
import concurrent.futures
import csv
import glob
import os
import re
import shutil
import subprocess
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
LOCK = os.path.join(HERE, "corpora.lock")
DEFAULT_BASELINE = os.path.join(HERE, "baselines", "differential-disagreements.tsv")
DEFAULT_OUT = os.path.join(HERE, "out", "differential.tsv")

TS_BIN = os.environ.get("TS_BIN") or shutil.which("tree-sitter") or "tree-sitter"
TS_NIX_LIB = os.environ.get("TS_NIX_LIB") or None
NIX_BIN = os.environ.get("NIX_BIN") or "nix-instantiate"

# corpus label -> (lock prefix, glob patterns relative to the upstream repo).
# nix's lang dir also holds helper files (lib.nix, imported-*.nix, ...) that
# are not test cases on their own; only the four test prefixes are compared.
CORPORA = {
    "nix-lang": ("NIX", ["tests/functional/lang/parse-okay-*.nix",
                         "tests/functional/lang/parse-fail-*.nix",
                         "tests/functional/lang/eval-okay-*.nix",
                         "tests/functional/lang/eval-fail-*.nix"]),
    "rnix-success": ("RNIX", ["test_data/parser/success/*.nix"]),
    "rnix-error": ("RNIX", ["test_data/parser/error/*.nix"]),
    "snix-nix_tests": ("SNIX", ["snix/eval/src/tests/nix_tests/*.nix"]),
    "snix-snix_tests": ("SNIX", ["snix/eval/src/tests/snix_tests/*.nix"]),
}

BASELINE_FIELDS = ["file", "corpus", "ts_ok", "nix_ok", "nix_class"]
RESULT_FIELDS = BASELINE_FIELDS + ["ts_error_nodes", "ts_missing_nodes", "nix_msg"]


def read_lock():
    vals = {}
    with open(LOCK) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            k, _, v = line.partition("=")
            vals[k.strip()] = v.strip().strip('"')
    return vals


def corpus_roots(corpora_dir):
    """lock prefix -> directory holding that upstream repo's subdirs."""
    lock = read_lock()
    roots = {}
    for prefix in ("NIX", "RNIX", "SNIX"):
        override = os.environ.get(prefix + "_SRC")
        roots[prefix] = override or os.path.join(corpora_dir, lock[prefix + "_NAME"])
    return roots, lock


def collect_files(corpora_dir):
    roots, lock = corpus_roots(corpora_dir)
    files = []  # (corpus, key, path)
    for corpus, (prefix, patterns) in CORPORA.items():
        root = roots[prefix]
        name = lock[prefix + "_NAME"]
        found = []
        for pat in patterns:
            found.extend(glob.glob(os.path.join(root, pat)))
        if not found:
            sys.exit("differential: no files for %s under %s "
                     "(run test/oracle/fetch-corpora.sh or set %s_SRC)" % (corpus, root, prefix))
        for path in sorted(found):
            key = name + "/" + os.path.relpath(path, root)
            files.append((corpus, key, path))
    return files


def ts_warm_up():
    # the CLI compiles the grammar into $TREE_SITTER_LIBDIR on first use;
    # do it once here so the parallel workers do not race on nix.so
    if not TS_NIX_LIB:
        subprocess.run([TS_BIN, "parse", "-q", os.path.join(REPO, "test", "highlight", "basic.nix")],
                       capture_output=True, cwd=REPO)


def ts_parse(path, trees_dir, key):
    cmd = [TS_BIN, "parse"]
    if TS_NIX_LIB:
        cmd += ["--lib-path", TS_NIX_LIB, "--lang-name", "nix"]
    r = subprocess.run(cmd + [path], capture_output=True, text=True, errors="replace", cwd=REPO)
    tree = r.stdout
    if trees_dir:
        with open(os.path.join(trees_dir, key.replace("/", "__") + ".sexp"), "w") as fh:
            fh.write(tree)
    n_err = len(re.findall(r"\(ERROR\b", tree))
    n_miss = len(re.findall(r"\(MISSING\b", tree))
    ok = r.returncode == 0 and n_err == 0 and n_miss == 0
    return ok, n_err, n_miss


def classify_nix(stderr):
    """Map nix-instantiate stderr to a class; only 'syntax' means rejected by the grammar."""
    if re.search(r"syntax error|lexer error|unexpected", stderr):
        return "syntax"
    if re.search(r"trailing slash|null bytes|not allowed in", stderr):
        return "syntax"
    if "undefined variable" in stderr:
        return "undefined-variable"
    if re.search(r"already defined|duplicate formal|dynamic attributes|attribute", stderr):
        return "semantic-bind"
    if "experimental" in stderr:
        return "experimental-feature"
    return "other"


def nix_parse(path):
    r = subprocess.run([NIX_BIN, "--parse", "--extra-experimental-features", "pipe-operators", path],
                       capture_output=True, text=True, errors="replace")
    if r.returncode == 0:
        return True, "ok", ""
    cls = classify_nix(r.stderr)
    lines = [l for l in r.stderr.strip().splitlines() if l.strip()]
    errors = [l for l in lines if l.startswith("error:")]
    msg = (errors or lines or [""])[0].replace("\t", " ")[:200]
    return cls != "syntax", cls, msg


def run_one(item, trees_dir):
    corpus, key, path = item
    ts_ok, n_err, n_miss = ts_parse(path, trees_dir, key)
    nix_ok, cls, msg = nix_parse(path)
    return dict(file=key, corpus=corpus, ts_ok=int(ts_ok), nix_ok=int(nix_ok), nix_class=cls,
                ts_error_nodes=n_err, ts_missing_nodes=n_miss, nix_msg=msg)


def read_tsv(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def write_tsv(path, rows, fields):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, delimiter="\t", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in fields})


def dis_key(r):
    return (r["file"], str(r["ts_ok"]), str(r["nix_ok"]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpora-dir", default=os.environ.get("CORPORA_DIR") or os.path.join(HERE, "corpora"))
    ap.add_argument("--baseline", default=DEFAULT_BASELINE)
    ap.add_argument("--out", default=DEFAULT_OUT, help="full per-file results TSV")
    ap.add_argument("--trees-dir", default=None, help="also dump every S-expression tree here")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--update-baseline", action="store_true",
                    help="overwrite the baseline with the current disagreements")
    args = ap.parse_args()

    files = collect_files(args.corpora_dir)
    if args.trees_dir:
        os.makedirs(args.trees_dir, exist_ok=True)
    ts_warm_up()
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.jobs)) as ex:
        rows = list(ex.map(lambda it: run_one(it, args.trees_dir), files))
    write_tsv(args.out, rows, RESULT_FIELDS)

    print("total files %d  (tree-sitter: %s%s; nix: %s)" % (
        len(rows), TS_BIN, " + " + TS_NIX_LIB if TS_NIX_LIB else "", NIX_BIN))
    for corpus in CORPORA:
        rs = [r for r in rows if r["corpus"] == corpus]
        agree = sum(1 for r in rs if r["ts_ok"] == r["nix_ok"])
        print("%-16s n=%4d ts_ok=%4d nix_ok=%4d agree=%4d disagree=%d" % (
            corpus, len(rs), sum(r["ts_ok"] for r in rs), sum(r["nix_ok"] for r in rs), agree, len(rs) - agree))
    print("nix classes: " + ", ".join("%s=%d" % kv for kv in sorted(Counter(r["nix_class"] for r in rows).items())))

    current = sorted((r for r in rows if r["ts_ok"] != r["nix_ok"]), key=lambda r: r["file"])
    if args.update_baseline:
        write_tsv(args.baseline, current, BASELINE_FIELDS)
        print("baseline written: %s (%d disagreements)" % (args.baseline, len(current)))
        return 0

    baseline = read_tsv(args.baseline)
    known = {dis_key(r) for r in baseline}
    now = {dis_key(r): r for r in current}
    new = [now[k] for k in sorted(now) if k not in known]
    gone = [r for r in baseline if dis_key(r) not in now]

    print("\ndisagreements: %d current, %d in baseline (%s)" % (len(current), len(baseline), os.path.relpath(args.baseline, REPO)))
    for r in current:
        tag = "NEW " if dis_key(r) in {dis_key(x) for x in new} else "    "
        print("%s%-16s %-70s ts_ok=%s nix_ok=%s %-18s err=%s miss=%s %s" % (
            tag, r["corpus"], r["file"], r["ts_ok"], r["nix_ok"], r["nix_class"],
            r["ts_error_nodes"], r["ts_missing_nodes"], r["nix_msg"]))
    if gone:
        print("\nIMPROVEMENT: %d baseline disagreement(s) no longer reproduce (re-run with --update-baseline):" % len(gone))
        for r in gone:
            print("    %-16s %s" % (r["corpus"], r["file"]))
    if new:
        print("\nFAIL: %d new disagreement(s) not in the baseline" % len(new))
        return 1
    print("\nOK: no new disagreements")
    return 0


if __name__ == "__main__":
    sys.exit(main())
