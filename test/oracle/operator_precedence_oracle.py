#!/usr/bin/env python3
"""
Cross-check oracle for tree-sitter-nix operator precedence/associativity.

For every test input, compares tree-sitter and nix-instantiate on TWO
dimensions:
  1. accept/reject — do both parsers agree the input is valid Nix?
  2. grouping — for valid 3-operand expressions `a OP1 b OP2 c`, do
     both parsers produce the same operator grouping (LEFT or RIGHT)?

The grouping check is what PR #51 missed. Comparing accept/reject only
will pass on `a + b == c` even if the parse tree shape is wrong.

Usage:
  python3 oracle.py /path/to/repo
Exits 0 if all checks pass, 1 otherwise. Prints a TSV report to stdout.
"""

import json
import re
import shutil
import subprocess
import sys
import os
from pathlib import Path

REPO = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
# tree-sitter CLI: $TS_BIN overrides; otherwise fall back to whatever is
# on PATH.
TS = os.environ.get("TS_BIN") or shutil.which("tree-sitter") or "tree-sitter"

# Nix's operators by precedence tier, lowest to highest, with associativity.
# Keep `?` separate — it takes an attrpath, not an expression, on the right.
TIERS = [
    # (operators, associativity)
    (["->"], "right"),       # impl
    (["||"], "left"),        # or
    (["&&"], "left"),        # and
    (["==", "!="], "nonassoc"),
    (["<", ">", "<=", ">="], "nonassoc"),
    (["//"], "right"),       # update
    # not / negate are unary, not binary
    (["+", "-"], "left"),
    (["*", "/"], "left"),
    (["++"], "right"),       # concat
]
ALL_BIN_OPS = [op for ops, _ in TIERS for op in ops]


def nix_parse(expr: str) -> str | None:
    """Parse a Nix expression. Return the parse output or None on syntax error."""
    # Wrap in a function so identifiers are bound (avoids "undefined variable").
    wrapped = f"a: b: c: d: e: f: g: ({expr})"
    p = subprocess.run(
        # pipe-operators is needed for |> / <| to lex at all on Nix 2.24+.
        # Harmless for every other expression.
        ["nix-instantiate", "--parse",
         "--extra-experimental-features", "pipe-operators",
         "--expr", wrapped],
        capture_output=True, text=True,
    )
    if p.returncode != 0:
        if "syntax error" in p.stderr or "unexpected" in p.stderr:
            return None
        # Other errors (e.g. experimental feature) — treat as unparseable
        # but distinguishable from syntax error. For our purposes, skip.
        return None
    return p.stdout.strip()


def nix_grouping(a: str, op1: str, b: str, op2: str, c: str) -> str:
    """
    For a valid `a OP1 b OP2 c`, determine Nix's grouping by
    parenthesization equivalence.

    Returns 'LEFT', 'RIGHT', 'ERROR', or 'AMBIGUOUS'.
    """
    bare = nix_parse(f"{a} {op1} {b} {op2} {c}")
    if bare is None:
        return "ERROR"
    left = nix_parse(f"({a} {op1} {b}) {op2} {c}")
    right = nix_parse(f"{a} {op1} ({b} {op2} {c})")
    if bare == left and bare != right:
        return "LEFT"
    if bare == right and bare != left:
        return "RIGHT"
    if bare == left and bare == right:
        # Both parenthesizations produce the same parse — degenerate case
        # (e.g. all integers, evaluator-level constant fold). Treat as
        # AMBIGUOUS — the test should pick non-degenerate operands.
        return "AMBIGUOUS"
    return "AMBIGUOUS"


def ts_parse(expr: str) -> str | None:
    """Parse with tree-sitter. Return the S-expr or None on error."""
    p = subprocess.run(
        [TS, "parse", "/dev/stdin"],
        input=expr, capture_output=True, text=True, cwd=REPO,
    )
    out = p.stdout
    if "(ERROR" in out or "(MISSING" in out or "(UNEXPECTED" in out:
        return None
    return out


def ts_grouping(a: str, op1: str, b: str, op2: str, c: str) -> str:
    """
    Determine tree-sitter's grouping by inspecting the topmost
    binary_expression's left operand byte range.

    For input `a OP1 b OP2 c`:
      - If the topmost binary's left operand spans more than just `a`,
        it's the inner expression → LEFT grouping.
      - If the topmost binary's left operand is just `a`, the right
        operand is the inner expression → RIGHT grouping.
    """
    expr = f"{a} {op1} {b} {op2} {c}"
    out = ts_parse(expr)
    if out is None:
        return "ERROR"
    # Find the topmost binary_expression's left operand range.
    # The S-expr looks like:
    #   (source_code [0, 0] - [1, 0]
    #     expression: (binary_expression [0, 0] - [0, N]
    #       left: (... [0, 0] - [0, M]) ...
    # The first `left:` after the first `binary_expression` is what we want.
    m = re.search(
        r"binary_expression \[0, 0\] - \[0, \d+\]\s*\n\s*left: \([\w_]+ \[0, 0\] - \[0, (\d+)\]",
        out,
    )
    if not m:
        # Could be a unary_expression on top, or a single binary, etc.
        # Fall back: count binary_expression nodes. If exactly one, the
        # input wasn't actually a 2-op chain — shouldn't happen.
        return "AMBIGUOUS"
    left_end = int(m.group(1))
    a_len = len(a)
    if left_end == a_len:
        return "RIGHT"
    return "LEFT"


def gen_matrix() -> list[dict]:
    """Generate the cross-check test matrix."""
    cases = []
    a, b, c = "a", "b", "c"

    # All 2-operator combinations.
    for op1 in ALL_BIN_OPS:
        for op2 in ALL_BIN_OPS:
            cases.append({"kind": "binop2", "a": a, "op1": op1, "b": b, "op2": op2, "c": c})

    # Same-tier non-assoc chaining (these MUST error in Nix).
    for ops, assoc in TIERS:
        if assoc != "nonassoc":
            continue
        for op1 in ops:
            for op2 in ops:
                cases.append({"kind": "nonassoc-chain", "a": a, "op1": op1, "b": b, "op2": op2, "c": c})

    # Cross-tier non-assoc (eq vs cmp — these are different precedence and SHOULD parse).
    for op1 in ["==", "!="]:
        for op2 in ["<", ">", "<=", ">="]:
            cases.append({"kind": "cross-tier", "a": a, "op1": op1, "b": b, "op2": op2, "c": c})
            cases.append({"kind": "cross-tier", "a": a, "op1": op2, "b": b, "op2": op1, "c": c})

    # Unary interaction: `!a OP b` and `-a OP b`.
    for unop in ["!", "-"]:
        for op in ALL_BIN_OPS:
            cases.append({"kind": "unary", "unop": unop, "a": a, "op": op, "b": b})

    # Parenthesized chaining (these MUST be valid).
    for op in ["==", "!=", "<", ">", "<=", ">="]:
        cases.append({"kind": "paren-chain", "a": a, "op1": op, "b": b, "op2": op, "c": c})

    # Nested unary in chain: `!a == b == c` should error (chain bypassable through unary).
    for unop in ["!", "-"]:
        for op in ["==", "!=", "<", ">", "<=", ">="]:
            cases.append({"kind": "unary-nonassoc-bypass", "unop": unop, "a": a, "op1": op, "b": b, "op2": op, "c": c})

    # Raw accept/reject cases found by adversarial review (see below).
    cases.extend(gen_extra_matrix())
    return cases


def run_case(case: dict) -> dict:
    """Run a single cross-check case. Returns {pass, ...details}."""
    kind = case["kind"]

    if kind == "raw":
        return run_raw_case(case)

    if kind in ("binop2", "nonassoc-chain", "cross-tier"):
        a, op1, b, op2, c = case["a"], case["op1"], case["b"], case["op2"], case["c"]
        expr = f"{a} {op1} {b} {op2} {c}"
        nix_g = nix_grouping(a, op1, b, op2, c)
        ts_g = ts_grouping(a, op1, b, op2, c)
        ok = nix_g == ts_g or (nix_g == "AMBIGUOUS" and ts_g != "ERROR")
        return {"pass": ok, "kind": kind, "expr": expr, "nix": nix_g, "ts": ts_g}

    if kind == "unary":
        unop, a, op, b = case["unop"], case["a"], case["op"], case["b"]
        expr = f"{unop}{a} {op} {b}"
        # No grouping ambiguity for 2-operand unary; just accept/reject + which
        # operator binds tighter (the unary or the binop).
        nix_out = nix_parse(expr)
        ts_out = ts_parse(expr)
        nix_accepts = nix_out is not None
        ts_accepts = ts_out is not None
        if not (nix_accepts and ts_accepts):
            ok = nix_accepts == ts_accepts
            return {"pass": ok, "kind": kind, "expr": expr, "nix": "accept" if nix_accepts else "reject", "ts": "accept" if ts_accepts else "reject"}
        # Both accept. Check grouping: `!a == b` could be `(!a) == b` or `!(a == b)`.
        nix_unary_first = nix_parse(f"({unop}{a}) {op} {b}") == nix_out
        nix_binop_first = nix_parse(f"{unop}({a} {op} {b})") == nix_out
        nix_g = "UNARY-INNER" if nix_unary_first else ("BINOP-INNER" if nix_binop_first else "AMBIGUOUS")
        # For tree-sitter: if topmost is unary_expression → unary is OUTER → BINOP-INNER.
        # If topmost is binary_expression → binop is OUTER → UNARY-INNER.
        if "unary_expression" in ts_out.split("\n")[1]:
            ts_g = "BINOP-INNER"
        elif "binary_expression" in ts_out.split("\n")[1]:
            ts_g = "UNARY-INNER"
        else:
            ts_g = "AMBIGUOUS"
        ok = nix_g == ts_g or nix_g == "AMBIGUOUS"
        return {"pass": ok, "kind": kind, "expr": expr, "nix": nix_g, "ts": ts_g}

    if kind == "paren-chain":
        a, op1, b, op2, c = case["a"], case["op1"], case["b"], case["op2"], case["c"]
        expr = f"({a} {op1} {b}) {op2} {c}"
        nix_accepts = nix_parse(expr) is not None
        ts_accepts = ts_parse(expr) is not None
        ok = nix_accepts == ts_accepts
        return {"pass": ok, "kind": kind, "expr": expr, "nix": "accept" if nix_accepts else "reject", "ts": "accept" if ts_accepts else "reject"}

    if kind == "unary-nonassoc-bypass":
        unop, a, op1, b, op2, c = case["unop"], case["a"], case["op1"], case["b"], case["op2"], case["c"]
        expr = f"{unop}{a} {op1} {b} {op2} {c}"
        nix_accepts = nix_parse(expr) is not None
        ts_accepts = ts_parse(expr) is not None
        ok = nix_accepts == ts_accepts
        return {"pass": ok, "kind": kind, "expr": expr, "nix": "accept" if nix_accepts else "reject", "ts": "accept" if ts_accepts else "reject"}

    raise ValueError(f"unknown kind {kind}")


# ---------------------------------------------------------------------------
# Real-world corpus check: any .nix file that nix-instantiate accepts must
# also parse without ERROR in tree-sitter. Protects against the layered
# grammar restructure breaking valid Nix that the synthetic matrix doesn't
# happen to cover.
# ---------------------------------------------------------------------------

# Real-world corpus root. $NIXPKGS_PATH overrides; otherwise try to
# resolve <nixpkgs> via nix-instantiate. Corpus files that don't exist
# are skipped, so a missing nixpkgs just means the synthetic matrix runs
# alone (the local repo files below are always checked).
def _default_nixpkgs() -> str:
    try:
        p = subprocess.run(
            ["nix-instantiate", "--eval", "--expr", "builtins.toString <nixpkgs>"],
            capture_output=True, text=True,
        )
        if p.returncode == 0:
            return p.stdout.strip().strip('"')
    except FileNotFoundError:
        pass
    return ""


NIXPKGS = os.environ.get("NIXPKGS_PATH") or _default_nixpkgs()
# Operator-heavy nixpkgs files that exercise the precedence ladder hard.
CORPUS = [
    f"{NIXPKGS}/lib/lists.nix",
    f"{NIXPKGS}/lib/strings.nix",
    f"{NIXPKGS}/lib/types.nix",
    f"{NIXPKGS}/lib/attrsets.nix",
    f"{NIXPKGS}/lib/options.nix",
    f"{NIXPKGS}/lib/trivial.nix",
    f"{NIXPKGS}/lib/modules.nix",
    f"{NIXPKGS}/lib/fixed-points.nix",
    f"{NIXPKGS}/lib/sources.nix",
    f"{NIXPKGS}/lib/versions.nix",
    f"{NIXPKGS}/lib/asserts.nix",
    f"{NIXPKGS}/lib/customisation.nix",
    # Local repo files — must always parse.
    str(REPO / "flake.nix"),
    str(REPO / "default.nix"),
    str(REPO / "shell.nix"),
]


def corpus_check() -> list[dict]:
    """Verify real-world Nix files parse without errors. Returns failures."""
    failures = []
    for path in CORPUS:
        if not os.path.exists(path):
            continue
        # Reference: does nix-instantiate accept it?
        nix_p = subprocess.run(
            ["nix-instantiate", "--parse", path],
            capture_output=True, text=True,
        )
        nix_ok = nix_p.returncode == 0
        # Tree-sitter: parse and check for ERROR/MISSING.
        ts_p = subprocess.run(
            [TS, "parse", path],
            capture_output=True, text=True, cwd=REPO,
        )
        ts_out = ts_p.stdout
        ts_ok = "(ERROR" not in ts_out and "(MISSING" not in ts_out and "(UNEXPECTED" not in ts_out
        if nix_ok and not ts_ok:
            # Find the error position for debugging.
            err_match = re.search(r"\(ERROR \[(\d+), (\d+)\]", ts_out)
            err_pos = f"line {int(err_match.group(1))+1}, col {err_match.group(2)}" if err_match else "unknown"
            failures.append({
                "file": path,
                "error_pos": err_pos,
            })
    return failures


def main():
    cases = gen_matrix()
    failures = []
    by_kind = {}
    for case in cases:
        r = run_case(case)
        by_kind.setdefault(r["kind"], {"pass": 0, "fail": 0})
        if r["pass"]:
            by_kind[r["kind"]]["pass"] += 1
        else:
            by_kind[r["kind"]]["fail"] += 1
            failures.append(r)

    corpus_failures = corpus_check()

    print(f"# Oracle report: {len(cases)} synthetic cases ({len(failures)} failures), "
          f"{len(CORPUS)} corpus files ({len(corpus_failures)} failures)\n")
    print("## Synthetic matrix\n")
    print("kind\tpass\tfail")
    for kind, stats in sorted(by_kind.items()):
        print(f"{kind}\t{stats['pass']}\t{stats['fail']}")
    if failures:
        print(f"\n### Synthetic failures ({len(failures)}):\n")
        print("expr\tnix\tts")
        for f in failures:
            print(f"{f['expr']}\t{f['nix']}\t{f['ts']}")

    print(f"\n## Real-world corpus ({len(CORPUS)} files)\n")
    if corpus_failures:
        print("file\terror_pos")
        for f in corpus_failures:
            print(f"{f['file']}\t{f['error_pos']}")
    else:
        print("All files parse without errors.")

    sys.exit(1 if (failures or corpus_failures) else 0)



# ---------------------------------------------------------------------------
# Additional cases discovered by adversarial review of PR #58.
# ---------------------------------------------------------------------------

def gen_extra_matrix() -> list[dict]:
    """Cases the original matrix didn't cover. Found by skeptics. Included by gen_matrix()."""
    cases = []
    # Chained has-attr: `a ? b ? c` is valid Nix (RHS is attrpath).
    cases.append({"kind": "raw", "expr": "a ? b ? c", "expect_ok": True})
    cases.append({"kind": "raw", "expr": "a ? b ? c.d", "expect_ok": True})
    cases.append({"kind": "raw", "expr": "(a ? b) ? c", "expect_ok": True})
    # Unary stacking: `-!a` is valid Nix.
    cases.append({"kind": "raw", "expr": "-!a", "expect_ok": True})
    cases.append({"kind": "raw", "expr": "!-!a", "expect_ok": True})
    cases.append({"kind": "raw", "expr": "- -!a", "expect_ok": True})
    cases.append({"kind": "raw", "expr": "a + -!b", "expect_ok": True})
    cases.append({"kind": "raw", "expr": "-!a + b", "expect_ok": True})
    cases.append({"kind": "raw", "expr": "!!a", "expect_ok": True})
    cases.append({"kind": "raw", "expr": "- -a", "expect_ok": True})
    cases.append({"kind": "raw", "expr": "!-a", "expect_ok": True})
    # Three-op cases.
    cases.append({"kind": "raw", "expr": "a + b * c == d", "expect_ok": True})
    cases.append({"kind": "raw", "expr": "a == b -> c == d", "expect_ok": True})
    cases.append({"kind": "raw", "expr": "a // b == c // d", "expect_ok": True})
    cases.append({"kind": "raw", "expr": "a ++ b == c", "expect_ok": True})
    # `!`-headed RHS of binary operators — Nix accepts (e.g. `a + !b`).
    for op in ["+", "-", "*", "/", "++"]:
        cases.append({"kind": "raw", "expr": f"a {op} !b", "expect_ok": True})
        cases.append({"kind": "raw", "expr": f"a {op} !b {op} c", "expect_ok": True})
        cases.append({"kind": "raw", "expr": f"a {op} !b * c", "expect_ok": True})
    cases.append({"kind": "raw", "expr": "a + -!b * c", "expect_ok": True})
    cases.append({"kind": "raw", "expr": "a / !-b", "expect_ok": True})
    # Pipe operators (Nix 2.24+). |> and <| are mutually exclusive in BOTH
    # directions — chaining one with itself is fine, mixing is a syntax error.
    cases.append({"kind": "raw", "expr": "a |> b", "expect_ok": True})
    cases.append({"kind": "raw", "expr": "a <| b", "expect_ok": True})
    cases.append({"kind": "raw", "expr": "a |> b |> c", "expect_ok": True})
    cases.append({"kind": "raw", "expr": "a <| b <| c", "expect_ok": True})
    cases.append({"kind": "raw", "expr": "a |> b <| c", "expect_ok": False})
    cases.append({"kind": "raw", "expr": "a <| b |> c", "expect_ok": False})
    return cases


def run_raw_case(case: dict) -> dict:
    """Run a raw accept/reject case."""
    expr = case["expr"]
    nix_ok = nix_parse(expr) is not None
    ts_ok = ts_parse(expr) is not None
    expected = case.get("expect_ok")
    if expected is not None and nix_ok != expected:
        return {"pass": False, "kind": "raw", "expr": expr, "nix": str(nix_ok), "ts": str(ts_ok), "note": f"oracle expectation wrong (expected nix to {'accept' if expected else 'reject'} but got {nix_ok})"}
    ok = nix_ok == ts_ok
    return {"pass": ok, "kind": "raw", "expr": expr, "nix": "accept" if nix_ok else "reject", "ts": "accept" if ts_ok else "reject"}


if __name__ == "__main__":
    main()
