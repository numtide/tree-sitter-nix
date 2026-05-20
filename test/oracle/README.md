# Operator precedence/associativity oracle

`operator_precedence_oracle.py` cross-checks tree-sitter-nix's operator
grammar against `nix-instantiate` (the C++ Nix reference parser) on a
synthetic matrix of operator combinations plus a real-world nixpkgs
corpus.

It compares two things per case:

1. **accept/reject** — do both parsers agree the input is valid Nix?
2. **grouping** — for valid `a OP1 b OP2 c` expressions, do both produce
   the same operator grouping (LEFT vs RIGHT)?

The grouping check is the important one: comparing only accept/reject
passes even when operator precedence is inverted (this is the bug that
slipped past the first attempt at non-associative operators, PR #51).

## Running

```sh
# Requires nix-instantiate on PATH and a tree-sitter CLI.
TS_BIN=$(command -v tree-sitter) \
  python3 test/oracle/operator_precedence_oracle.py .
```

Exit 0 = all checks pass. Exit 1 = failures, with a TSV report.

## Coverage

- Every binary operator pair (`a OP1 b OP2 c`).
- Same-tier non-associative chains (`a == b == c` must error).
- Cross-tier mixing (`a == b < c` must parse, right grouping).
- Unary interactions (`!a OP b`, `-a OP b`, stacking like `-!a`).
- `!`-headed RHS (`a + !b` — Nix has `!` below `+`).
- Chained has-attr (`a ? b ? c`).
- Parenthesized chains (`(a == b) == c`).
- Real nixpkgs lib files (must parse without error).

## Maintenance

When a grammar change touches operators, add the motivating cases to
`gen_extra_matrix()` BEFORE fixing the grammar, so the oracle locks in
the expected behaviour. The `NIXPKGS_PATH` env var overrides the
corpus location.
